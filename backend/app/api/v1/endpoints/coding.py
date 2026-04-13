from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.db.session import get_db
from app.schemas.schemas import CodingRequest, CodingResponse, EncounterSummary
from app.services.coding_service import analyze_and_persist, get_user_encounters
from app.api.v1.deps import get_current_active_user
from app.models.models import User

router = APIRouter(prefix="/coding", tags=["coding"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/analyze", response_model=CodingResponse)
@limiter.limit("10/minute")
async def analyze(
    request: Request,
    body: CodingRequest,
    current_user: User = Depends(get_current_active_user),
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
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    encounters = await get_user_encounters(db, current_user.id, limit, offset)
    return encounters
