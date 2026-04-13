from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds HIPAA-aligned security headers to every response.
    """

    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Cache-Control": "no-store",           # Never cache PHI responses
        "Pragma": "no-cache",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        ),
    }

    async def dispatch(self, request: Request, call_next) -> Response:
        # HTTPS redirect in production
        if settings.enforce_https and request.url.scheme == "http":
            https_url = str(request.url).replace("http://", "https://", 1)
            return RedirectResponse(https_url, status_code=301)

        response = await call_next(request)

        for header, value in self.SECURITY_HEADERS.items():
            response.headers[header] = value

        # HSTS — only in production over HTTPS
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs all requests for audit purposes.
    Masks sensitive paths to avoid logging credentials.
    """

    MASKED_PATHS = {"/api/v1/auth/token", "/api/v1/auth/refresh"}

    async def dispatch(self, request: Request, call_next) -> Response:
        import time
        import logging
        logger = logging.getLogger("codifyai.access")

        start = time.time()
        response = await call_next(request)
        duration = round((time.time() - start) * 1000, 2)

        path = request.url.path
        masked = path in self.MASKED_PATHS

        logger.info(
            "%s %s %d %.2fms ip=%s",
            request.method,
            "[MASKED]" if masked else path,
            response.status_code,
            duration,
            request.client.host if request.client else "unknown",
        )

        return response
