import time
import pyotp
import pytest
from httpx import AsyncClient
from app.core.config import settings
from app.core.security import decrypt_secret
from app.tests.conftest import login, USER_PASSWORD

pytestmark = pytest.mark.asyncio

EMAIL = "testcoder@codifyai.com"


async def _enroll(client, headers) -> str:
    setup = await client.post("/api/v1/auth/mfa/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/CodifyAI")
    res = await client.post("/api/v1/auth/mfa/enable", headers=headers, json={"code": pyotp.TOTP(secret).now()})
    assert res.status_code == 200
    return secret


def _next_code(secret):
    # Enrollment consumed the current step; the next step is still in the ±1
    # window and hasn't been used yet.
    return pyotp.TOTP(secret).at(time.time() + 30)


async def test_secret_is_encrypted_at_rest(client, db, auth_headers, test_user):
    secret = await _enroll(client, auth_headers)
    await db.refresh(test_user)
    assert secret not in test_user.mfa_secret_encrypted
    assert decrypt_secret(test_user.mfa_secret_encrypted) == secret
    assert test_user.mfa_enabled


async def test_enable_rejects_wrong_code(client, auth_headers):
    await client.post("/api/v1/auth/mfa/setup", headers=auth_headers)
    res = await client.post("/api/v1/auth/mfa/enable", headers=auth_headers, json={"code": "000000"})
    assert res.status_code == 400


async def test_login_with_mfa(client: AsyncClient, auth_headers, test_user):
    secret = await _enroll(client, auth_headers)

    res = await client.post("/api/v1/auth/token", data={"username": EMAIL, "password": USER_PASSWORD})
    assert res.status_code == 200
    body = res.json()
    assert body["mfa_required"] is True
    assert body["access_token"] is None
    assert "set-cookie" not in res.headers

    verify = await client.post("/api/v1/auth/mfa/verify", json={
        "mfa_token": body["mfa_token"], "code": _next_code(secret),
    })
    assert verify.status_code == 200, verify.text
    assert verify.json()["access_token"]

    # The mfa_token is single-use
    again = await client.post("/api/v1/auth/mfa/verify", json={
        "mfa_token": body["mfa_token"], "code": pyotp.TOTP(secret).now(),
    })
    assert again.status_code == 401


async def test_mfa_code_cannot_be_replayed(client, auth_headers):
    secret = await _enroll(client, auth_headers)  # consumes the current step
    res = await client.post("/api/v1/auth/token", data={"username": EMAIL, "password": USER_PASSWORD})
    verify = await client.post("/api/v1/auth/mfa/verify", json={
        "mfa_token": res.json()["mfa_token"], "code": pyotp.TOTP(secret).now(),
    })
    assert verify.status_code == 401


async def test_bad_mfa_codes_lock_account(client, db, auth_headers, test_user):
    await _enroll(client, auth_headers)
    for _ in range(5):
        res = await client.post("/api/v1/auth/token", data={"username": EMAIL, "password": USER_PASSWORD})
        if res.status_code != 200:
            break
        await client.post("/api/v1/auth/mfa/verify", json={"mfa_token": res.json()["mfa_token"], "code": "000000"})
    await db.refresh(test_user)
    assert test_user.locked_until is not None


async def test_access_token_cannot_be_used_as_mfa_token(client, auth_headers):
    await _enroll(client, auth_headers)
    token = auth_headers["Authorization"].split()[1]
    res = await client.post("/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": "123456"})
    assert res.status_code == 401


async def test_disable_mfa_requires_password_and_code(client, auth_headers, test_user):
    secret = await _enroll(client, auth_headers)
    bad = await client.post("/api/v1/auth/mfa/disable", headers=auth_headers, json={
        "password": "WrongPassword1!", "code": _next_code(secret),
    })
    assert bad.status_code == 400
    ok = await client.post("/api/v1/auth/mfa/disable", headers=auth_headers, json={
        "password": USER_PASSWORD, "code": _next_code(secret),
    })
    assert ok.status_code == 200


async def test_require_mfa_blocks_app_until_enrolled(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "require_mfa", True)

    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.status_code == 200
    assert me.json()["mfa_enrollment_required"] is True

    assert (await client.get("/api/v1/coding/history", headers=auth_headers)).status_code == 403

    await _enroll(client, auth_headers)
    assert (await client.get("/api/v1/coding/history", headers=auth_headers)).status_code == 200

    disable = await client.post("/api/v1/auth/mfa/disable", headers=auth_headers, json={
        "password": USER_PASSWORD, "code": "123456",
    })
    assert disable.status_code == 403
