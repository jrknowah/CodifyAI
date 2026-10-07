import anthropic
import hashlib
import hmac
import logging
from pydantic import ValidationError
from app.core.config import settings
from app.schemas.schemas import CodeResult, CodingResponse, EmLevel, FlaggedCode
from app.models.models import Encounter, FacilityType
from app.services.audit_service import write_audit_log, AuditAction
from app.services.coding_prompts import (
    RECORD_TOOL_NAME, build_record_tool, build_system_prompt, requires_em_level,
)
from app.services.code_validation import check_em_level, validate_codes
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, Request
from uuid import UUID
from datetime import datetime, timezone
import uuid

logger = logging.getLogger("codifyai.coding")

# Async client so a slow model call doesn't block the event loop for every other request.
client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

# Fields of a code result that are safe to persist. `reason` (and the summary)
# are written by the model about the note and can quote PHI — never stored.
PERSISTED_CODE_FIELDS = {"code", "type", "description", "confidence", "modifiers"}
# Same for E/M: levels and computed checks are kept, the MDM `support` text isn't.
PERSISTED_EM_FIELDS = {
    "patient_type", "level", "basis", "total_time_minutes", "modifiers", "confidence",
    "mdm_level", "computed_level", "consistent", "cpt_code",
}

# One retry when the model answers without calling the tool (tool_choice can't be
# forced on current models; strict mode only guarantees the arguments' shape).
MAX_ATTEMPTS = 2


class CodingOutputError(Exception):
    """The model's answer couldn't be turned into a coding result."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _hash_note(note: str) -> str:
    """Keyed HMAC-SHA256 of the note — stored instead of note text (PHI protection).
    Keyed so someone holding a candidate note can't confirm it against the database."""
    return hmac.new(settings.encryption_key.encode(), note.encode("utf-8"), hashlib.sha256).hexdigest()


async def _call_model(clinical_note: str, facility_type: str):
    """Ask the model for a coding result via the strict `record_coding_result` tool.
    Returns (tool_input, model_id). Raises CodingOutputError or anthropic.APIError."""
    tool = build_record_tool(facility_type, settings.cpt_licensed)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        message = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            output_config={"effort": settings.anthropic_effort},
            system=build_system_prompt(facility_type, settings.cpt_licensed),
            tools=[tool],
            tool_choice={"type": "auto"},
            messages=[{
                "role": "user",
                "content": (
                    f"Facility type: {facility_type}\n\n"
                    f"<clinical_note>\n{clinical_note}\n</clinical_note>\n\n"
                    f"Code this note and record the result with the {RECORD_TOOL_NAME} tool."
                ),
            }],
        )
        if message.stop_reason == "refusal":
            raise CodingOutputError("refusal")
        if message.stop_reason == "max_tokens":
            raise CodingOutputError("max_tokens")
        for block in message.content:
            if block.type == "tool_use" and block.name == RECORD_TOOL_NAME:
                return block.input, message.model
        logger.warning("Model answered without calling %s (attempt %d)", RECORD_TOOL_NAME, attempt)
    raise CodingOutputError("no_tool_call")


def _build_result(raw: dict, facility_type: str):
    """Validate the tool input. Returns (codes, em_level, flagged, summary)."""
    try:
        kept, flagged = validate_codes(raw["codes"], settings.cpt_licensed)
        codes = [CodeResult(**c) for c in kept]
        em_level = None
        if requires_em_level(facility_type):
            try:
                em_level = EmLevel(**check_em_level(raw["em_level"], settings.cpt_licensed))
            except (KeyError, ValueError) as e:
                # A bad E/M suggestion shouldn't sink the diagnosis codes
                flagged.append({"code": None, "type": "E/M", "issue": f"E/M suggestion dropped: {e}"[:200]})
        return codes, em_level, [FlaggedCode(**f) for f in flagged], raw["summary"]
    except (KeyError, TypeError, ValidationError) as e:
        raise CodingOutputError(f"invalid_output:{type(e).__name__}")


async def analyze_and_persist(
    db: AsyncSession,
    request: Request,
    clinical_note: str,
    facility_type: str,
    user_id: UUID,
    facility_id: UUID | None,
) -> CodingResponse:
    """
    Call Claude, validate results, persist encounter (without PHI), write audit log.
    """
    try:
        raw, model_used = await _call_model(clinical_note, facility_type)
        codes, em_level, flagged, summary = _build_result(raw, facility_type)
    except anthropic.APIError as e:
        await write_audit_log(
            db, AuditAction.analyze, request,
            user_id=user_id,
            detail={
                "error": type(e).__name__,
                "status_code": getattr(e, "status_code", None),
                "facility_type": facility_type,
            },
            success=False,
        )
        raise HTTPException(status_code=502, detail="AI service temporarily unavailable.")
    except CodingOutputError as e:
        await write_audit_log(
            db, AuditAction.analyze, request,
            user_id=user_id,
            detail={"error": "output_failure", "reason": e.reason, "facility_type": facility_type},
            success=False,
        )
        if e.reason == "refusal":
            raise HTTPException(status_code=502, detail="The AI declined to code this note. Please code it manually.")
        raise HTTPException(status_code=502, detail="Could not get a valid coding result. Please try again.")

    encounter_id = uuid.uuid4()
    top_code = codes[0].code if codes else "N/A"

    # Persist encounter — note hash and de-identified results only; no note text,
    # no model-written reasons, MDM support text or summary
    encounter = Encounter(
        id=encounter_id,
        user_id=user_id,
        facility_id=facility_id,
        note_hash=_hash_note(clinical_note),
        note_length=len(clinical_note),
        facility_type=FacilityType(facility_type),
        codes=[c.model_dump(include=PERSISTED_CODE_FIELDS) for c in codes],
        em_level=em_level.model_dump(include=PERSISTED_EM_FIELDS) if em_level else None,
        flagged_codes=[f.model_dump() for f in flagged],
        model_used=model_used,
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
            "flagged_count": len(flagged),
            "em_level": em_level.level if em_level else None,
            "top_code": top_code,
            "model": model_used,
            "cpt_licensed": settings.cpt_licensed,
        },
        success=True,
    )

    return CodingResponse(
        encounter_id=encounter_id,
        facility_type=facility_type,
        codes=codes,
        em_level=em_level,
        flagged_codes=flagged,
        cpt_licensed=settings.cpt_licensed,
        summary=summary,
        model_used=model_used,
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
