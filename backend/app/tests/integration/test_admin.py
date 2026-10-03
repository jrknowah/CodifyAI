import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models.models import AuditAction, AuditLog, UserRole
from app.tests.conftest import login, make_user, USER_PASSWORD

pytestmark = pytest.mark.asyncio

NEW_USER = {"email": "nurse@codifyai.com", "password": "NursePass123!", "full_name": "Mary O'Brien"}


async def test_non_admin_forbidden(client: AsyncClient, auth_headers):
    assert (await client.get("/api/v1/admin/users", headers=auth_headers)).status_code == 403
    assert (await client.post("/api/v1/admin/users", headers=auth_headers, json=NEW_USER)).status_code == 403
    assert (await client.get("/api/v1/admin/audit-logs", headers=auth_headers)).status_code == 403


async def test_admin_creates_user_who_can_log_in(client, db, admin_headers, admin_user):
    res = await client.post("/api/v1/admin/users", headers=admin_headers, json={**NEW_USER, "role": "viewer"})
    assert res.status_code == 201, res.text
    assert res.json()["role"] == "viewer"
    assert res.json()["full_name"] == "Mary O'Brien"
    await login(client, NEW_USER["email"], NEW_USER["password"])

    log = (await db.execute(select(AuditLog).where(AuditLog.action == AuditAction.user_created))).scalars().one()
    assert log.user_id == admin_user.id


async def test_admin_cannot_create_with_unknown_facility(client, admin_headers):
    res = await client.post("/api/v1/admin/users", headers=admin_headers, json={
        **NEW_USER, "facility_id": "00000000-0000-0000-0000-000000000000",
    })
    assert res.status_code == 400


async def test_role_change_revokes_sessions(client, admin_headers, auth_headers, test_user):
    res = await client.patch(f"/api/v1/admin/users/{test_user.id}", headers=admin_headers, json={"role": "viewer"})
    assert res.status_code == 200
    assert res.json()["role"] == "viewer"
    assert (await client.get("/api/v1/auth/me", headers=auth_headers)).status_code == 401


async def test_deactivate_user(client, admin_headers, auth_headers, test_user):
    user_id, email = test_user.id, test_user.email
    res = await client.patch(f"/api/v1/admin/users/{user_id}", headers=admin_headers, json={"is_active": False})
    assert res.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=auth_headers)).status_code == 401
    bad = await client.post("/api/v1/auth/token", data={"username": email, "password": USER_PASSWORD})
    assert bad.status_code == 401


async def test_admin_cannot_demote_or_deactivate_self(client, admin_headers, admin_user):
    admin_id = admin_user.id
    for change in ({"role": "coder"}, {"is_active": False}):
        res = await client.patch(f"/api/v1/admin/users/{admin_id}", headers=admin_headers, json=change)
        assert res.status_code == 400


async def test_unlock_user(client, db, admin_headers, test_user):
    for _ in range(5):
        await client.post("/api/v1/auth/token", data={"username": test_user.email, "password": "WrongPassword1!"})
    res = await client.post(f"/api/v1/admin/users/{test_user.id}/unlock", headers=admin_headers)
    assert res.status_code == 200
    await login(client, test_user.email)


async def test_reset_mfa_and_revoke_sessions(client, db, admin_headers, auth_headers, test_user):
    user_id, email = test_user.id, test_user.email
    test_user.mfa_enabled = True
    test_user.mfa_secret_encrypted = "x"
    await db.commit()
    res = await client.post(f"/api/v1/admin/users/{test_user.id}/reset-mfa", headers=admin_headers)
    assert res.status_code == 200
    await db.refresh(test_user)
    assert test_user.mfa_enabled is False and test_user.mfa_secret_encrypted is None
    assert (await client.get("/api/v1/auth/me", headers=auth_headers)).status_code == 401

    fresh = await login(client, email)
    headers = {"Authorization": f"Bearer {fresh.json()['access_token']}"}
    res = await client.post(f"/api/v1/admin/users/{user_id}/revoke-sessions", headers=admin_headers)
    assert res.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_audit_log_listing_and_filter(client, admin_headers, test_user):
    await client.post("/api/v1/auth/token", data={"username": test_user.email, "password": "WrongPassword1!"})
    res = await client.get(
        "/api/v1/admin/audit-logs", headers=admin_headers,
        params={"action": "login_failed", "user_id": str(test_user.id)},
    )
    assert res.status_code == 200
    logs = res.json()
    assert len(logs) == 1 and logs[0]["action"] == "login_failed" and logs[0]["success"] is False

    # Viewing the audit log is itself audited
    res = await client.get("/api/v1/admin/audit-logs", headers=admin_headers, params={"action": "view_audit_log"})
    assert len(res.json()) >= 1


async def test_list_users(client, admin_headers, test_user):
    res = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert res.status_code == 200
    emails = {u["email"] for u in res.json()}
    assert {"admin@codifyai.com", test_user.email} <= emails
    assert all("hashed_password" not in u and "mfa_secret_encrypted" not in u for u in res.json())
