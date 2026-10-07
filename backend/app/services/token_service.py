from datetime import timedelta
from uuid import UUID
from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, token_expiry
from app.models.models import RevokedToken, User, utcnow
from app.schemas.schemas import LoginResponse

REFRESH_COOKIE = "codifyai_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


# A refresh token presented again within this window of being rotated is treated
# as a benign race (two tabs refreshing at once), not as theft.
REUSE_GRACE = timedelta(seconds=60)


async def get_revocation(db: AsyncSession, jti: str) -> RevokedToken | None:
    result = await db.execute(select(RevokedToken).where(RevokedToken.jti == jti))
    return result.scalar_one_or_none()


async def is_token_revoked(db: AsyncSession, jti: str) -> bool:
    return await get_revocation(db, jti) is not None


def is_suspicious_reuse(revocation: RevokedToken) -> bool:
    return utcnow() - revocation.revoked_at > REUSE_GRACE


async def revoke_token(db: AsyncSession, payload: dict, user_id: UUID | None = None) -> None:
    """Add a decoded token's jti to the denylist (idempotent) and prune expired rows."""
    if not await is_token_revoked(db, payload["jti"]):
        db.add(RevokedToken(jti=payload["jti"], user_id=user_id, expires_at=token_expiry(payload)))
    await db.execute(delete(RevokedToken).where(RevokedToken.expires_at < utcnow()))
    await db.flush()


def issue_session(response: Response, user: User, auth_time: int | None = None) -> LoginResponse:
    """Create an access token (returned in the body, kept in memory by the SPA) and a
    refresh token (httpOnly cookie, never readable by JavaScript)."""
    access = create_access_token(str(user.id), user.token_version, {"role": user.role.value})
    refresh = create_refresh_token(str(user.id), user.token_version, auth_time)
    response.set_cookie(
        REFRESH_COOKIE, refresh,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
        # No max_age: a browser-session cookie. The JWT inside still expires.
    )
    return LoginResponse(access_token=access, expires_in=settings.access_token_expire_minutes * 60)


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_COOKIE_PATH,
        httponly=True, secure=settings.secure_cookies, samesite="strict",
    )


def check_origin(request: Request) -> None:
    """Defense in depth for cookie-authenticated endpoints (on top of SameSite=Strict):
    reject requests a browser sent from an origin we don't serve."""
    origin = request.headers.get("origin")
    if origin and origin not in settings.origins_list:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin not allowed.")
