from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import AuditLog, AuditAction
from app.core.net import get_client_ip
from fastapi import Request
from typing import Optional
from uuid import UUID


async def write_audit_log(
    db: AsyncSession,
    action: AuditAction,
    request: Request,
    user_id: Optional[UUID] = None,
    resource_id: Optional[str] = None,
    detail: Optional[dict] = None,
    success: bool = True,
) -> None:
    """
    Append an immutable audit log entry.
    Call this for every security-sensitive action.

    Commits immediately: request sessions roll back when an HTTPException is
    raised, and failure events (bad logins, AI errors) are exactly the ones that
    must not be lost. Anything else pending in the session is committed with it.
    """
    log = AuditLog(
        user_id=user_id,
        action=action,
        resource_id=str(resource_id) if resource_id else None,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:500],
        detail=detail,
        success=success,
    )
    db.add(log)
    await db.commit()


async def list_audit_logs(
    db: AsyncSession,
    user_id: Optional[UUID] = None,
    action: Optional[AuditAction] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditLog]:
    query = select(AuditLog)
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    if action is not None:
        query = query.where(AuditLog.action == action)
    result = await db.execute(
        query.order_by(AuditLog.created_at.desc()).limit(min(limit, 200)).offset(offset)
    )
    return list(result.scalars().all())
