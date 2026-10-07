from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.api.v1.deps import require_admin
from app.models.models import AuditAction, Facility, User, UserRole
from app.schemas.schemas import (
    AdminUserCreate, AdminUserOut, AdminUserUpdate, AuditLogOut, MessageResponse, UserCreate,
)
from app.services.audit_service import list_audit_logs, write_audit_log
from app.services.user_service import create_user, get_user_by_id

router = APIRouter(prefix="/admin", tags=["admin"])


async def _get_user_or_404(db: AsyncSession, user_id: UUID) -> User:
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset))
    return list(result.scalars().all())


@router.post("/users", response_model=AdminUserOut, status_code=201)
async def admin_create_user(
    request: Request,
    data: AdminUserCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await create_user(
        db,
        UserCreate(email=data.email, password=data.password, full_name=data.full_name),
        role=UserRole(data.role),
        facility_id=data.facility_id,
    )
    await write_audit_log(
        db, AuditAction.user_created, request, user_id=admin.id, resource_id=str(user.id),
        detail={"email": user.email, "role": user.role.value},
    )
    return user


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def admin_update_user(
    request: Request,
    user_id: UUID,
    data: AdminUserUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, user_id)
    changes = data.model_dump(exclude_unset=True)
    # null clears facility_id; for every other field it means "leave unchanged"
    changes = {k: v for k, v in changes.items() if v is not None or k == "facility_id"}

    if user.id == admin.id and (changes.get("is_active") is False or changes.get("role", "admin") != "admin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can't deactivate or demote your own account.",
        )
    if changes.get("facility_id") is not None and await db.get(Facility, changes["facility_id"]) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown facility.")

    if "full_name" in changes:
        user.full_name = changes["full_name"]
    if "facility_id" in changes:
        user.facility_id = changes["facility_id"]
    if "role" in changes:
        user.role = UserRole(changes["role"])
    if "is_active" in changes:
        user.is_active = changes["is_active"]
    if "role" in changes or changes.get("is_active") is False:
        user.token_version += 1  # permissions changed: force re-login

    await write_audit_log(
        db, AuditAction.user_updated, request, user_id=admin.id, resource_id=str(user.id),
        detail={k: str(v) for k, v in changes.items()},
    )
    return user


@router.post("/users/{user_id}/unlock", response_model=MessageResponse)
async def admin_unlock_user(
    request: Request,
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, user_id)
    user.failed_login_attempts = 0
    user.locked_until = None
    await write_audit_log(db, AuditAction.user_unlocked, request, user_id=admin.id, resource_id=str(user.id))
    return MessageResponse(message="Account unlocked.")


@router.post("/users/{user_id}/reset-mfa", response_model=MessageResponse)
async def admin_reset_mfa(
    request: Request,
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """For a user who lost their authenticator. They re-enroll on next login."""
    user = await _get_user_or_404(db, user_id)
    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    user.mfa_last_used_step = None
    user.token_version += 1
    await write_audit_log(db, AuditAction.mfa_reset, request, user_id=admin.id, resource_id=str(user.id))
    return MessageResponse(message="MFA reset. The user must enroll again.")


@router.post("/users/{user_id}/revoke-sessions", response_model=MessageResponse)
async def admin_revoke_sessions(
    request: Request,
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_or_404(db, user_id)
    user.token_version += 1
    await write_audit_log(
        db, AuditAction.user_updated, request, user_id=admin.id, resource_id=str(user.id),
        detail={"sessions": "revoked"},
    )
    return MessageResponse(message="All sessions for this user were signed out.")


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def admin_audit_logs(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    user_id: UUID | None = None,
    action: AuditAction | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    logs = await list_audit_logs(db, user_id=user_id, action=action, limit=limit, offset=offset)
    await write_audit_log(
        db, AuditAction.view_audit_log, request, user_id=admin.id,
        detail={"filter_user_id": str(user_id) if user_id else None,
                "filter_action": action.value if action else None, "offset": offset},
    )
    return logs
