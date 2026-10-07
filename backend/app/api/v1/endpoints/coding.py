from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.config import settings
from app.core.rate_limit import limiter
from app.schemas.schemas import CodingRequest, CodingResponse, EncounterSummary
from app.services.coding_service import analyze_and_persist, get_user_encounters
from app.services.audit_service import write_audit_log
from app.api.v1.deps import get_current_active_user, require_coder
from app.models.models import AuditAction, User

router = APIRouter(prefix="/coding", tags=["coding"])


@router.post("/analyze", response_model=CodingResponse)
@limiter.limit(f"{settings.rate_limit_analyze_per_minute}/minute")
async def analyze(
    request: Request,
    body: CodingRequest,
    current_user: User = Depends(require_coder),
    db: AsyncSession = Depends(get_db),
):
    return await analyze_and_persist(
        db=db,
        request=request,
        clinical_note=body.clinical_note,
        facility_type=body.facility_type,
        user_id=current_user.id,
        facility_id=current_user.facility_id,
    )


@router.get("/history", response_model=list[EncounterSummary])
async def history(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    encounters = await get_user_encounters(db, current_user.id, limit, offset)
    await write_audit_log(
        db, AuditAction.view_history, request, user_id=current_user.id,
        detail={"limit": limit, "offset": offset, "returned": len(encounters)},
    )
    return encounters
