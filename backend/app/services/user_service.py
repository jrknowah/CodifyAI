from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import AuditAction, Facility, User, UserRole, utcnow
from app.schemas.schemas import UserCreate
from app.core.security import hash_password, verify_password, DUMMY_PASSWORD_HASH
from app.services.audit_service import write_audit_log
from fastapi import HTTPException, Request, status
from uuid import UUID
from datetime import timedelta

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

# One message for every login failure (unknown email, wrong password, locked,
# disabled) so responses can't be used to discover which accounts exist.
LOGIN_FAILED_DETAIL = "Incorrect email or password."


def login_failed() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=LOGIN_FAILED_DETAIL)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    data: UserCreate,
    role: UserRole = UserRole.coder,
    facility_id: UUID | None = None,
) -> User:
    existing = await get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )
    if facility_id is not None and await db.get(Facility, facility_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown facility.")
    user = User(
        email=data.email.lower(),
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=role,
        facility_id=facility_id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def record_failed_attempt(db: AsyncSession, request: Request, user: User, reason: str) -> None:
    """Count a failed password or MFA code; lock the account at the threshold.
    The audit write commits, so the counter survives the 401 that follows."""
    user.failed_login_attempts += 1
    locked_now = user.failed_login_attempts >= MAX_FAILED_ATTEMPTS
    if locked_now:
        user.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
        user.failed_login_attempts = 0
    await write_audit_log(
        db, AuditAction.login_failed, request, user_id=user.id,
        detail={"reason": reason}, success=False,
    )
    if locked_now:
        await write_audit_log(
            db, AuditAction.account_locked, request, user_id=user.id,
            detail={"minutes": LOCKOUT_MINUTES}, success=True,
        )


async def authenticate_user(db: AsyncSession, request: Request, email: str, password: str) -> User:
    """Password step of login. Raises the same 401 for every failure."""
    user = await get_user_by_email(db, email)

    if not user:
        verify_password(password, DUMMY_PASSWORD_HASH)  # equalize timing
        await write_audit_log(
            db, AuditAction.login_failed, request,
            detail={"reason": "unknown_email", "email": email[:320]}, success=False,
        )
        raise login_failed()

    if user.is_locked():
        verify_password(password, DUMMY_PASSWORD_HASH)
        await write_audit_log(
            db, AuditAction.login_failed, request, user_id=user.id,
            detail={"reason": "locked"}, success=False,
        )
        raise login_failed()

    if not verify_password(password, user.hashed_password):
        await record_failed_attempt(db, request, user, "bad_password")
        raise login_failed()

    if not user.is_active:
        await write_audit_log(
            db, AuditAction.login_failed, request, user_id=user.id,
            detail={"reason": "inactive"}, success=False,
        )
        raise login_failed()

    return user


async def complete_login(db: AsyncSession, user: User) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = utcnow()
    await db.flush()


async def change_password(db: AsyncSession, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    user.hashed_password = hash_password(new)
    user.token_version += 1  # sign out every other session
    await db.flush()
