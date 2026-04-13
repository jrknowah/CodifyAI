import anthropic
import json
import hashlib
from app.core.config import settings
from app.schemas.schemas import CodeResult, CodingResponse
from app.models.models import Encounter, FacilityType
from app.services.audit_service import write_audit_log, AuditAction
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, Request
from uuid import UUID
from datetime import datetime, timezone
import uuid

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = """You are CodifyAI, an expert medical coder specializing in post-acute care,
skilled nursing facilities (SNF), recuperative care, and long-term care facilities.

Analyze the clinical note and return ONLY a valid JSON object — no markdown, no preamble.

Required structure:
{
  "codes": [
    {
      "code": "exact ICD-10-CM/CPT-4/HCPCS Level II code",
      "type": "ICD-10" | "CPT" | "HCPCS",
      "description": "full official code description",
      "confidence": 0.0-1.0,
      "reason": "one sentence citing specific note content supporting this code"
    }
  ],
  "summary": "2-3 sentences: primary diagnosis, comorbidities captured, care setting coding context"
}

Coding rules:
- Return 4-7 codes, primary diagnosis first
- Use real, valid codes only
- Apply ICD-10-CM specificity (laterality, acuity, episode of care)
- Apply PDPM and MDS linkage awareness for SNF contexts
- Sequence comorbidities after principal diagnosis
- Flag procedure codes (CPT) separately from diagnostic codes (ICD-10)
- Confidence >= 0.7 means the note clearly supports the code
"""


def _hash_note(note: str) -> str:
    """SHA-256 hash of note — stored instead of note text (PHI protection)."""
    return hashlib.sha256(note.encode("utf-8")).hexdigest()


async def analyze_and_persist(
    db: AsyncSession,
    request: Request,
    clinical_note: str,
    facility_type: str,
    user_id: UUID,
    facility_id: UUID | None,
) -> CodingResponse:
    """
    Call Claude, parse results, persist encounter (without PHI), write audit log.
    """
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Facility type: {facility_type}\n\nClinical Note:\n{clinical_note}"
            }],
        )
    except anthropic.APIError as e:
        await write_audit_log(
            db, AuditAction.analyze, request,
            user_id=user_id,
            detail={"error": str(e), "facility_type": facility_type},
            success=False,
        )
        raise HTTPException(status_code=502, detail="AI service temporarily unavailable.")

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()

    try:
        parsed = json.loads(raw)
        codes = [CodeResult(**c) for c in parsed["codes"]]
        summary = parsed["summary"]
    except (json.JSONDecodeError, KeyError, Exception) as e:
        await write_audit_log(
            db, AuditAction.analyze, request,
            user_id=user_id,
            detail={"error": "parse_failure", "raw_length": len(raw)},
            success=False,
        )
        raise HTTPException(status_code=500, detail="Could not parse AI response. Please try again.")

    encounter_id = uuid.uuid4()
    top_code = codes[0].code if codes else "N/A"

    # Persist encounter — note hash only, never raw note text
    encounter = Encounter(
        id=encounter_id,
        user_id=user_id,
        facility_id=facility_id,
        note_hash=_hash_note(clinical_note),
        note_length=len(clinical_note),
        facility_type=FacilityType(facility_type),
        codes=[c.model_dump() for c in codes],
        summary=summary,
        model_used=message.model,
        code_count=len(codes),
        top_code=top_code,
    )
    db.add(encounter)

    await write_audit_log(
        db, AuditAction.analyze, request,
        user_id=user_id,
        resource_id=str(encounter_id),
        detail={
            "facility_type": facility_type,
            "note_length": len(clinical_note),
            "code_count": len(codes),
            "top_code": top_code,
            "model": message.model,
        },
        success=True,
    )

    await db.flush()

    return CodingResponse(
        encounter_id=encounter_id,
        codes=codes,
        summary=summary,
        model_used=message.model,
        code_count=len(codes),
        created_at=datetime.now(timezone.utc),
    )


async def get_user_encounters(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> list[Encounter]:
    result = await db.execute(
        select(Encounter)
        .where(Encounter.user_id == user_id)
        .order_by(Encounter.created_at.desc())
        .limit(min(limit, 100))
        .offset(offset)
    )
    return list(result.scalars().all())
