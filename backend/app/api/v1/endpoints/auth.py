from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import (
    create_mfa_token, decode_access_token, decode_mfa_token, decode_refresh_token,
    decrypt_secret, encrypt_secret, generate_totp_secret, totp_provisioning_uri,
    verify_password, verify_totp, JWTError,
)
from app.schemas.schemas import (
    LoginResponse, UserOut, PasswordChange, MessageResponse,
    MfaVerifyRequest, MfaSetupResponse, MfaCodeRequest, MfaDisableRequest,
)
from app.services.user_service import (
    authenticate_user, change_password, complete_login, get_user_by_id,
    login_failed, record_failed_attempt,
)
from app.services.audit_service import write_audit_log
from app.services.token_service import (
    REFRESH_COOKIE, check_origin, clear_refresh_cookie, get_revocation, is_suspicious_reuse,
    is_token_revoked, issue_session, revoke_token,
)
from app.models.models import AuditAction, User
from app.api.v1.deps import get_current_user, get_current_active_user, mfa_enrollment_required

router = APIRouter(prefix="/auth", tags=["auth"])

# Logout must work even with an expired/missing access token.
optional_bearer = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

INVALID_SESSION = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session.")

# Accounts are created by administrators (POST /api/v1/admin/users).
# There is deliberately no public self-registration endpoint.


@router.post("/token", response_model=LoginResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, request, form_data.username, form_data.password)

    if user.mfa_enabled:
        # Password is right; the session is only issued after /auth/mfa/verify.
        return LoginResponse(mfa_required=True, mfa_token=create_mfa_token(str(user.id), user.token_version))

    await complete_login(db, user)
    session = issue_session(response, user)
    await write_audit_log(db, AuditAction.login, request, user_id=user.id, detail={"mfa": False})
    return session


@router.post("/mfa/verify", response_model=LoginResponse)
@limiter.limit("10/minute")
async def mfa_verify(
    request: Request,
    response: Response,
    body: MfaVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Second login step: exchange the mfa_token + a TOTP code for a session."""
    try:
        payload = decode_mfa_token(body.mfa_token)
        user = await get_user_by_id(db, UUID(payload["sub"]))
    except (JWTError, KeyError, ValueError):
        raise login_failed()
    if (
        not user or not user.is_active or user.is_locked() or not user.mfa_enabled
        or payload.get("ver") != user.token_version
        or await is_token_revoked(db, payload["jti"])
    ):
        raise login_failed()

    step = verify_totp(decrypt_secret(user.mfa_secret_encrypted), body.code, user.mfa_last_used_step)
    if step is None:
        await record_failed_attempt(db, request, user, "bad_mfa_code")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code.")

    user.mfa_last_used_step = step
    await revoke_token(db, payload, user.id)  # mfa_token is single-use
    await complete_login(db, user)
    session = issue_session(response, user)
    await write_audit_log(db, AuditAction.login, request, user_id=user.id, detail={"mfa": True})
    return session


@router.post("/refresh", response_model=LoginResponse)
@limiter.limit("20/minute")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Rotate the refresh cookie and return a new access token."""
    check_origin(request)
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise INVALID_SESSION
    try:
        payload = decode_refresh_token(token)
        user = await get_user_by_id(db, UUID(payload["sub"]))
    except (JWTError, KeyError, ValueError):
        clear_refresh_cookie(response)
        raise INVALID_SESSION

    revocation = await get_revocation(db, payload["jti"])
    if revocation:
        if user and is_suspicious_reuse(revocation):
            # A rotated-out refresh token was presented again well after rotation:
            # it was likely stolen. Kill every session the user has.
            user.token_version += 1
            await write_audit_log(
                db, AuditAction.refresh_token_reuse, request, user_id=user.id, success=False,
            )
        raise INVALID_SESSION

    if not user or not user.is_active or payload.get("ver") != user.token_version:
        raise INVALID_SESSION

    await revoke_token(db, payload, user.id)
    return issue_session(response, user, auth_time=payload["auth_time"])


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    token: str | None = Depends(optional_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the access token and refresh cookie (whichever are still valid)."""
    check_origin(request)
    user_id = None
    if token:
        try:
            payload = decode_access_token(token)
            user_id = UUID(payload["sub"])
            await revoke_token(db, payload, user_id)
        except (JWTError, KeyError, ValueError):
            pass
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if refresh_token:
        try:
            payload = decode_refresh_token(refresh_token)
            user_id = user_id or UUID(payload["sub"])
            await revoke_token(db, payload, UUID(payload["sub"]))
        except (JWTError, KeyError, ValueError):
            pass
    clear_refresh_cookie(response)
    if user_id:
        await write_audit_log(db, AuditAction.logout, request, user_id=user_id)
    return MessageResponse(message="Logged out successfully.")


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    out = UserOut.model_validate(current_user)
    out.mfa_enrollment_required = mfa_enrollment_required(current_user)
    return out


@router.post("/change-password", response_model=LoginResponse)
@limiter.limit("5/minute")
async def change_pwd(
    request: Request,
    response: Response,
    data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Changes the password, signs out every other session, and returns a fresh
    session for this one."""
    await change_password(db, current_user, data.current_password, data.new_password)
    session = issue_session(response, current_user)
    await write_audit_log(db, AuditAction.password_changed, request, user_id=current_user.id)
    return session


# ── MFA enrollment ────────────────────────────────────────────────────────────

@router.post("/mfa/setup", response_model=MfaSetupResponse)
@limiter.limit("5/minute")
async def mfa_setup(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new (not yet active) TOTP secret for the authenticator app."""
    if current_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA is already enabled.")
    secret = generate_totp_secret()
    current_user.mfa_secret_encrypted = encrypt_secret(secret)
    current_user.mfa_last_used_step = None
    await db.flush()
    return MfaSetupResponse(secret=secret, otpauth_uri=totp_provisioning_uri(secret, current_user.email))


@router.post("/mfa/enable", response_model=MessageResponse)
@limiter.limit("10/minute")
async def mfa_enable(
    request: Request,
    body: MfaCodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA is already enabled.")
    if not current_user.mfa_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start MFA setup first.")
    step = verify_totp(decrypt_secret(current_user.mfa_secret_encrypted), body.code, None)
    if step is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")
    current_user.mfa_enabled = True
    current_user.mfa_last_used_step = step
    await write_audit_log(db, AuditAction.mfa_enabled, request, user_id=current_user.id)
    return MessageResponse(message="Two-factor authentication enabled.")


@router.post("/mfa/disable", response_model=MessageResponse)
@limiter.limit("5/minute")
async def mfa_disable(
    request: Request,
    body: MfaDisableRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if settings.require_mfa:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA is required by policy.")
    if not current_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is not enabled.")
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password or code is incorrect.")
    step = verify_totp(
        decrypt_secret(current_user.mfa_secret_encrypted), body.code, current_user.mfa_last_used_step,
    )
    if step is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password or code is incorrect.")
    current_user.mfa_enabled = False
    current_user.mfa_secret_encrypted = None
    current_user.mfa_last_used_step = None
    await write_audit_log(db, AuditAction.mfa_disabled, request, user_id=current_user.id)
    return MessageResponse(message="Two-factor authentication disabled.")
