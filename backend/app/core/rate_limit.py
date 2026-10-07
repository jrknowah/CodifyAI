from slowapi import Limiter
from app.core.config import settings
from app.core.net import get_client_ip

# One limiter for the whole app, keyed on the proxy-aware client IP.
limiter = Limiter(
    key_func=get_client_ip,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
    storage_uri=settings.rate_limit_storage_uri,
    enabled=settings.rate_limit_enabled,
)
