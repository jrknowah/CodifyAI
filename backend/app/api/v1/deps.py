from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.config import settings
from app.core.security import decode_access_token, JWTError
from app.services.user_service import get_user_by_id
from app.services.token_service import is_token_revoked
from app.models.models import User, UserRole
from uuid import UUID

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Any signed-in user, including one who still has to enroll in MFA.
    Only the auth endpoints (me, logout, MFA enrollment) should use this directly."""
    try:
        payload = decode_access_token(token)
        user_id = UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise CREDENTIALS_ERROR

    if await is_token_revoked(db, payload["jti"]):
        raise CREDENTIALS_ERROR

    user = await get_user_by_id(db, user_id)
    # Same error for a missing, disabled or rotated-out user: the token is simply no good.
    if not user or not user.is_active or payload.get("ver") != user.token_version:
        raise CREDENTIALS_ERROR
    return user


def mfa_enrollment_required(user: User) -> bool:
    return settings.require_mfa and not user.mfa_enabled


async def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    if mfa_enrollment_required(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA enrollment required.")
    return user


def require_roles(*roles: UserRole):
    async def checker(user: User = Depends(get_current_active_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
        return user
    return checker


require_admin = require_roles(UserRole.admin)
require_coder = require_roles(UserRole.admin, UserRole.coder)
