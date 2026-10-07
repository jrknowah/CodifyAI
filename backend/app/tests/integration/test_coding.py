import anthropic
import httpx
import pytest
from sqlalchemy import select
from app.core.config import settings
from app.models.models import AuditAction, AuditLog, Encounter, UserRole
from app.tests.conftest import login, make_user
from app.tests import fakes

pytestmark = pytest.mark.asyncio

NOTE = "Patient John Smith, DOB 01/02/1950, POD 12 after right THA. HTN on lisinopril. T2DM."
SNF_OUTPUT = {
    "codes": [
        {"code": "Z96.641", "type": "ICD-10-CM", "description": "Presence of right artificial hip joint",
         "confidence": 0.95, "reason": "John Smith is POD 12 after right THA", "modifiers": []},
        {"code": "I10", "type": "ICD-10-CM", "description": "Essential (primary) hypertension",
         "confidence": 0.9, "reason": "HTN on lisinopril", "modifiers": []},
    ],
    "summary": "John Smith, 76, recovering from right THA with HTN and T2DM.",
}

UC_NOTE = ("Jane Doe, established patient, 3 days of sore throat and fever 101.4F. Rapid strep "
           "positive (reviewed). Amoxicillin 500 mg BID x10 days prescribed. Ceftriaxone 250 mg IM given.")


def uc_output(**em_overrides):
    em = {
        "patient_type": "established", "level": 4, "basis": "mdm",
        "problems": {"level": "moderate", "support": "Jane Doe: acute illness with systemic symptoms (fever 101.4F)"},
        "data": {"level": "limited", "support": "Rapid strep ordered and reviewed"},
        "risk": {"level": "moderate", "support": "Prescription drug management: amoxicillin"},
        "total_time_minutes": None, "modifiers": [], "confidence": 0.82,
    }
    em.update(em_overrides)
    return {
        "codes": [
            {"code": "J02.0", "type": "ICD-10-CM", "description": "Streptococcal pharyngitis",
             "confidence": 0.93, "reason": "Rapid strep positive for Jane Doe", "modifiers": []},
            {"code": "J0696", "type": "HCPCS", "description": "Injection, ceftriaxone sodium, per 250 mg",
             "confidence": 0.88, "reason": "Ceftriaxone 250 mg IM given", "modifiers": []},
        ],
        "summary": "Jane Doe seen for strep pharyngitis.",
        "em_level": em,
    }


async def analyze(client, headers, note=NOTE, facility_type="post-acute"):
    return await client.post("/api/v1/coding/analyze", headers=headers,
                             json={"clinical_note": note, "facility_type": facility_type})


# ── Request shape ─────────────────────────────────────────────────────────────

async def test_uses_strict_tool_and_configured_model(client, auth_headers, monkeypatch):
    fake = fakes.install(monkeypatch, fakes.tool_message(SNF_OUTPUT))
    assert (await analyze(client, auth_headers)).status_code == 200
    call = fake.calls[0]
    assert call["model"] == settings.anthropic_model
    assert call["output_config"] == {"effort": settings.anthropic_effort}
    assert call["tool_choice"] == {"type": "auto"}  # forced tool choice is a 400 on current models
    tool = call["tools"][0]
    assert tool["strict"] is True
    assert tool["input_schema"]["additionalProperties"] is False
    assert "PDPM" in call["system"]                  # SNF prompt kept for post-acute
    assert "<clinical_note>" in call["messages"][0]["content"]


async def test_default_model_is_current():
    assert settings.anthropic_model == "claude-opus-5-5"


# ── PHI ───────────────────────────────────────────────────────────────────────

async def test_analyze_returns_reasons_but_never_stores_them(client, db, auth_headers, monkeypatch):
    fakes.install(monkeypatch, fakes.tool_message(SNF_OUTPUT))
    res = await analyze(client, auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["codes"][0]["reason"]          # coder still sees the rationale
    assert "John Smith" in body["summary"]
    assert body["em_level"] is None

    enc = (await db.execute(select(Encounter))).scalars().one()
    assert "John Smith" not in str(enc.codes) + str(enc.em_level) + str(enc.flagged_codes)
    assert "reason" not in enc.codes[0]
    assert enc.codes[0] == {"code": "Z96.641", "type": "ICD-10-CM", "modifiers": [],
                            "description": "Presence of right artificial hip joint", "confidence": 0.95}


# ── Urgent care ───────────────────────────────────────────────────────────────

async def test_urgent_care_returns_em_level(client, db, auth_headers, monkeypatch):
    fake = fakes.install(monkeypatch, fakes.tool_message(uc_output()))
    res = await analyze(client, auth_headers, UC_NOTE, "urgent-care")
    assert res.status_code == 200, res.text
    call = fake.calls[0]
    assert "2021+" in call["system"] and "modifier 25" in call["system"]
    assert "em_level" in call["tools"][0]["input_schema"]["required"]

    em = res.json()["em_level"]
    assert em["level"] == 4 and em["patient_type"] == "established"
    assert em["problems"]["support"].startswith("Jane Doe")
    assert em["mdm_level"] == "moderate" and em["computed_level"] == 4 and em["consistent"] is True
    assert em["review_label"] == "For coder review"
    assert res.json()["facility_type"] == "urgent-care"

    enc = (await db.execute(select(Encounter))).scalars().one()
    assert enc.facility_type.value == "urgent-care"
    assert enc.em_level["level"] == 4
    assert "Jane Doe" not in str(enc.em_level)   # MDM support text is never stored
    assert "support" not in str(enc.em_level)


async def test_inconsistent_em_level_is_flagged(client, auth_headers, monkeypatch):
    fakes.install(monkeypatch, fakes.tool_message(uc_output(level=5)))
    em = (await analyze(client, auth_headers, UC_NOTE, "urgent-care")).json()["em_level"]
    assert em["consistent"] is False and em["computed_level"] == 4
    assert "doesn't match level 4" in em["consistency_notes"][0]


async def test_invalid_em_level_is_dropped_but_diagnoses_kept(client, auth_headers, monkeypatch):
    fakes.install(monkeypatch, fakes.tool_message(uc_output(patient_type="new", level=1)))
    body = (await analyze(client, auth_headers, UC_NOTE, "urgent-care")).json()
    assert body["em_level"] is None
    assert body["code_count"] == 2
    assert any(f["type"] == "E/M" for f in body["flagged_codes"])


async def test_post_acute_has_no_em_level_in_schema(client, auth_headers, monkeypatch):
    fake = fakes.install(monkeypatch, fakes.tool_message(SNF_OUTPUT))
    await analyze(client, auth_headers)
    assert "em_level" not in fake.calls[0]["tools"][0]["input_schema"]["properties"]


# ── CPT licensing ─────────────────────────────────────────────────────────────

def _with_cpt(output):
    return {**output, "codes": output["codes"] + [
        {"code": "87880", "type": "CPT", "description": "CPT DESCRIPTOR TEXT", "confidence": 0.9,
         "reason": "Rapid strep test performed", "modifiers": []},
    ]}


async def test_cpt_unlicensed_strips_cpt(client, db, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "cpt_licensed", False)
    fake = fakes.install(monkeypatch, fakes.tool_message(_with_cpt(uc_output())))
    res = await analyze(client, auth_headers, UC_NOTE, "urgent-care")
    body = res.json()
    call = fake.calls[0]

    # The schema doesn't even allow CPT, and the prompt forbids it
    code_enum = call["tools"][0]["input_schema"]["properties"]["codes"]["items"]["properties"]["type"]["enum"]
    assert "CPT" not in code_enum
    assert "Do not output CPT codes" in call["system"]

    # ...and if the model returns one anyway, it never reaches the response or the DB
    assert "87880" not in res.text and "CPT DESCRIPTOR TEXT" not in res.text
    assert {c["type"] for c in body["codes"]} == {"ICD-10-CM", "HCPCS"}
    assert body["em_level"]["cpt_code"] is None
    assert body["cpt_licensed"] is False
    assert {"code": None, "type": "CPT", "issue": "CPT output disabled (no CPT license)"} in body["flagged_codes"]
    enc = (await db.execute(select(Encounter))).scalars().one()
    assert "87880" not in str(enc.codes) + str(enc.flagged_codes)


async def test_cpt_licensed_returns_cpt_and_em_code(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "cpt_licensed", True)
    fake = fakes.install(monkeypatch, fakes.tool_message(_with_cpt(uc_output(modifiers=["-25"]))))
    body = (await analyze(client, auth_headers, UC_NOTE, "urgent-care")).json()
    assert "CPT" in fake.calls[0]["tools"][0]["input_schema"]["properties"]["codes"]["items"]["properties"]["type"]["enum"]
    assert "87880" in {c["code"] for c in body["codes"]}
    assert body["em_level"]["cpt_code"] == "99214"
    assert body["em_level"]["modifiers"] == ["25"]


# ── Code validation ───────────────────────────────────────────────────────────

async def test_malformed_codes_are_flagged_not_returned(client, auth_headers, monkeypatch):
    output = {**SNF_OUTPUT, "codes": SNF_OUTPUT["codes"] + [
        {"code": "Z999999999", "type": "ICD-10-CM", "description": "Made up", "confidence": 0.5,
         "reason": "x", "modifiers": []},
        {"code": "E119", "type": "ICD-10-CM", "description": "Type 2 diabetes mellitus without complications",
         "confidence": 0.8, "reason": "T2DM", "modifiers": []},
    ]}
    fakes.install(monkeypatch, fakes.tool_message(output))
    body = (await analyze(client, auth_headers)).json()
    codes = [c["code"] for c in body["codes"]]
    assert "E11.9" in codes                  # normalized, dot inserted
    assert "Z999999999" not in codes
    assert body["flagged_codes"][0]["issue"] == "not a valid ICD-10-CM code format"


# ── Failure handling ──────────────────────────────────────────────────────────

async def test_retries_once_when_model_skips_the_tool(client, auth_headers, monkeypatch):
    fake = fakes.install(monkeypatch, fakes.text_message(), fakes.tool_message(SNF_OUTPUT))
    assert (await analyze(client, auth_headers)).status_code == 200
    assert len(fake.calls) == 2


async def test_no_tool_call_twice_fails_and_is_audited(client, db, auth_headers, monkeypatch):
    fake = fakes.install(monkeypatch, fakes.text_message())
    res = await analyze(client, auth_headers)
    assert res.status_code == 502
    assert len(fake.calls) == 2
    log = (await db.execute(select(AuditLog).where(AuditLog.action == AuditAction.analyze))).scalars().one()
    assert log.success is False and log.detail["reason"] == "no_tool_call"


async def test_refusal_is_reported_and_audited(client, db, auth_headers, monkeypatch):
    fakes.install(monkeypatch, fakes.text_message("", stop_reason="refusal"))
    res = await analyze(client, auth_headers)
    assert res.status_code == 502 and "declined" in res.json()["detail"]
    log = (await db.execute(select(AuditLog).where(AuditLog.action == AuditAction.analyze))).scalars().one()
    assert log.detail["reason"] == "refusal"


async def test_ai_failure_is_audited_despite_error_response(client, db, auth_headers, test_user, monkeypatch):
    """Regression: failure audit rows used to be rolled back along with the 502."""
    user_id = test_user.id
    fakes.install(monkeypatch, anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com")))
    res = await analyze(client, auth_headers)
    assert res.status_code == 502
    log = (await db.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.analyze, AuditLog.user_id == user_id)
    )).scalars().one()
    assert log.success is False
    assert "John" not in str(log.detail)


async def test_schema_violating_output_fails_cleanly(client, db, auth_headers, monkeypatch):
    fakes.install(monkeypatch, fakes.tool_message({"codes": [{"code": "I10"}], "summary": "x"}))
    res = await analyze(client, auth_headers)
    assert res.status_code == 502
    log = (await db.execute(select(AuditLog).where(AuditLog.action == AuditAction.analyze))).scalars().one()
    assert log.detail["reason"].startswith("invalid_output")


# ── Access ────────────────────────────────────────────────────────────────────

async def test_unknown_facility_type_rejected(client, auth_headers):
    assert (await analyze(client, auth_headers, facility_type="hospital")).status_code == 422


async def test_viewer_cannot_analyze(client, db, monkeypatch):
    fakes.install(monkeypatch, fakes.tool_message(SNF_OUTPUT))
    await make_user(db, "viewer@codifyai.com", role=UserRole.viewer)
    res = await login(client, "viewer@codifyai.com")
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert (await analyze(client, headers)).status_code == 403
    assert (await client.get("/api/v1/coding/history", headers=headers)).status_code == 200


async def test_history_is_audited(client, db, auth_headers, test_user, monkeypatch):
    user_id = test_user.id
    fakes.install(monkeypatch, fakes.tool_message(SNF_OUTPUT))
    await analyze(client, auth_headers)
    res = await client.get("/api/v1/coding/history", headers=auth_headers)
    assert res.status_code == 200 and len(res.json()) == 1
    logs = (await db.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.view_history, AuditLog.user_id == user_id)
    )).scalars().all()
    assert len(logs) == 1


async def test_history_only_shows_own_encounters(client, db, auth_headers, monkeypatch):
    fakes.install(monkeypatch, fakes.tool_message(SNF_OUTPUT))
    await make_user(db, "other@codifyai.com")
    other = await login(client, "other@codifyai.com")
    await analyze(client, {"Authorization": f"Bearer {other.json()['access_token']}"})
    res = await client.get("/api/v1/coding/history", headers=auth_headers)
    assert res.json() == []
