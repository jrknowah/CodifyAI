from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import AuditLog, AuditAction
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
    """
    log = AuditLog(
        user_id=user_id,
        action=action,
        resource_id=str(resource_id) if resource_id else None,
        ip_address=_get_client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:500],
        detail=detail,
        success=success,
    )
    db.add(log)
    # Flush immediately — audit logs should not be lost on rollback
    await db.flush()


def _get_client_ip(request: Request) -> str:
    """Extract real IP, respecting proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def get_audit_logs(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditLog]:
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.user_id == user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
