from types import SimpleNamespace
import anthropic
import httpx
import pytest
from sqlalchemy import select
from app.models.models import AuditAction, AuditLog, Encounter, UserRole
from app.services import coding_service
from app.tests.conftest import login, make_user

pytestmark = pytest.mark.asyncio

NOTE = "Patient John Smith, DOB 01/02/1950, POD 12 after right THA. HTN on lisinopril. T2DM."
MODEL_OUTPUT = """{
  "codes": [
    {"code": "Z96.641", "type": "ICD-10", "description": "Presence of right artificial hip joint",
     "confidence": 0.95, "reason": "John Smith is POD 12 after right THA"},
    {"code": "I10", "type": "ICD-10", "description": "Essential (primary) hypertension",
     "confidence": 0.9, "reason": "HTN on lisinopril"}
  ],
  "summary": "John Smith, 76, recovering from right THA with HTN and T2DM."
}"""


class FakeMessages:
    def __init__(self, result):
        self.result = result

    async def create(self, **kwargs):
        if isinstance(self.result, Exception):
            raise self.result
        return SimpleNamespace(model="claude-test", content=[SimpleNamespace(text=self.result)])


@pytest.fixture
def fake_claude(monkeypatch):
    def install(result):
        monkeypatch.setattr(coding_service, "client", SimpleNamespace(messages=FakeMessages(result)))
    install(MODEL_OUTPUT)
    return install


async def test_analyze_returns_reasons_but_never_stores_them(client, db, auth_headers, fake_claude):
    res = await client.post("/api/v1/coding/analyze", headers=auth_headers, json={"clinical_note": NOTE})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["codes"][0]["reason"]          # coder still sees the rationale
    assert "John Smith" in body["summary"]

    enc = (await db.execute(select(Encounter))).scalars().one()
    stored = str(enc.codes) + enc.note_hash
    assert "John Smith" not in stored
    assert "reason" not in enc.codes[0]
    assert not hasattr(enc, "summary")
    assert enc.codes[0] == {"code": "Z96.641", "type": "ICD-10",
                            "description": "Presence of right artificial hip joint", "confidence": 0.95}


async def test_ai_failure_is_audited_despite_error_response(client, db, auth_headers, test_user, fake_claude):
    """Regression: failure audit rows used to be rolled back along with the 502."""
    req = httpx.Request("POST", "https://api.anthropic.com")
    fake_claude(anthropic.APIConnectionError(request=req))
    res = await client.post("/api/v1/coding/analyze", headers=auth_headers, json={"clinical_note": NOTE})
    assert res.status_code == 502
    log = (await db.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.analyze, AuditLog.user_id == test_user.id)
    )).scalars().one()
    assert log.success is False
    assert "John" not in str(log.detail)


async def test_parse_failure_is_audited(client, db, auth_headers, fake_claude):
    fake_claude("not json")
    res = await client.post("/api/v1/coding/analyze", headers=auth_headers, json={"clinical_note": NOTE})
    assert res.status_code == 500
    logs = (await db.execute(select(AuditLog).where(AuditLog.action == AuditAction.analyze))).scalars().all()
    assert len(logs) == 1 and logs[0].detail["error"] == "parse_failure"


async def test_viewer_cannot_analyze(client, db, fake_claude):
    await make_user(db, "viewer@codifyai.com", role=UserRole.viewer)
    res = await login(client, "viewer@codifyai.com")
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert (await client.post("/api/v1/coding/analyze", headers=headers, json={"clinical_note": NOTE})).status_code == 403
    assert (await client.get("/api/v1/coding/history", headers=headers)).status_code == 200


async def test_history_is_audited(client, db, auth_headers, test_user, fake_claude):
    await client.post("/api/v1/coding/analyze", headers=auth_headers, json={"clinical_note": NOTE})
    res = await client.get("/api/v1/coding/history", headers=auth_headers)
    assert res.status_code == 200
    assert len(res.json()) == 1
    logs = (await db.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.view_history, AuditLog.user_id == test_user.id)
    )).scalars().all()
    assert len(logs) == 1


async def test_history_only_shows_own_encounters(client, db, auth_headers, fake_claude):
    await make_user(db, "other@codifyai.com")
    other = await login(client, "other@codifyai.com")
    await client.post("/api/v1/coding/analyze", json={"clinical_note": NOTE},
                      headers={"Authorization": f"Bearer {other.json()['access_token']}"})
    res = await client.get("/api/v1/coding/history", headers=auth_headers)
    assert res.json() == []
