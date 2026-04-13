from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.db.session import get_db
from app.schemas.schemas import (
    TokenResponse, UserCreate, UserOut, RefreshRequest,
    PasswordChange, MessageResponse
)
from app.services.user_service import authenticate_user, create_user, change_password
from app.services.audit_service import write_audit_log
from app.core.security import (
    create_access_token, create_refresh_token,
    decode_refresh_token, blacklist_token
)
from app.core.config import settings
from app.models.models import AuditAction
from app.api.v1.deps import get_current_active_user, oauth2_scheme
from app.models.models import User
from jose import JWTError

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/token", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, form_data.username, form_data.password)

    access_token = create_access_token(str(user.id), {"role": user.role.value})
    refresh_token = create_refresh_token(str(user.id))

    await write_audit_log(
        db, AuditAction.login, request,
        user_id=user.id,
        detail={"email": user.email},
        success=True,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")
async def refresh(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = decode_refresh_token(body.refresh_token)
        from uuid import UUID
        from app.services.user_service import get_user_by_id
        user = await get_user_by_id(db, UUID(payload["sub"]))
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    except (JWTError, Exception):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token.")

    access_token = create_access_token(str(user.id), {"role": user.role.value})
    refresh_token = create_refresh_token(str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    blacklist_token(token)
    await write_audit_log(
        db, AuditAction.logout, request,
        user_id=current_user.id,
        success=True,
    )
    return MessageResponse(message="Logged out successfully.")


@router.post("/register", response_model=UserOut, status_code=201)
@limiter.limit("5/minute")
async def register(
    request: Request,
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    user = await create_user(db, data)
    await write_audit_log(
        db, AuditAction.user_created, request,
        user_id=user.id,
        detail={"email": user.email},
        success=True,
    )
    return user


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_active_user)):
    return current_user


@router.post("/change-password", response_model=MessageResponse)
async def change_pwd(
    request: Request,
    data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await change_password(db, current_user, data.current_password, data.new_password)
    await write_audit_log(
        db, AuditAction.password_changed, request,
        user_id=current_user.id,
        success=True,
    )
    return MessageResponse(message="Password updated successfully.")
