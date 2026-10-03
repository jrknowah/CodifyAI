import time
import pytest
from httpx import AsyncClient
from sqlalchemy import select, func
from app.core.security import create_refresh_token
from app.models.models import AuditAction, AuditLog, User
from app.services.token_service import REFRESH_COOKIE
from app.services.user_service import MAX_FAILED_ATTEMPTS, LOGIN_FAILED_DETAIL
from app.tests.conftest import login, make_user, USER_PASSWORD

pytestmark = pytest.mark.asyncio

EMAIL = "testcoder@codifyai.com"


async def _audit_count(db, action, user_id=None):
    q = select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    return (await db.execute(q)).scalar_one()


class TestLogin:

    async def test_login_success_sets_httponly_refresh_cookie(self, client: AsyncClient, test_user):
        res = await login(client, EMAIL)
        data = res.json()
        assert data["access_token"]
        assert data["token_type"] == "bearer"
        assert "refresh_token" not in data or data.get("refresh_token") is None
        cookie = res.headers["set-cookie"]
        assert REFRESH_COOKIE in cookie
        assert "HttpOnly" in cookie
        assert "samesite=strict" in cookie.lower()
        assert "Path=/api/v1/auth" in cookie

    async def test_login_success_is_audited(self, client, db, test_user):
        await login(client, EMAIL)
        assert await _audit_count(db, AuditAction.login, test_user.id) == 1

    async def test_wrong_password(self, client: AsyncClient, test_user):
        res = await client.post("/api/v1/auth/token", data={"username": EMAIL, "password": "WrongPassword1!"})
        assert res.status_code == 401
        assert res.json()["detail"] == LOGIN_FAILED_DETAIL

    async def test_nonexistent_user_gets_identical_response(self, client: AsyncClient, db):
        res = await client.post("/api/v1/auth/token", data={"username": "nobody@codifyai.com", "password": "AnyPass123!"})
        assert res.status_code == 401
        assert res.json()["detail"] == LOGIN_FAILED_DETAIL
        assert await _audit_count(db, AuditAction.login_failed) == 1

    async def test_failed_attempts_persist_and_lock_account(self, client: AsyncClient, db, test_user):
        """Regression: the counter used to be rolled back with the 401, so lockout never fired."""
        for _ in range(MAX_FAILED_ATTEMPTS):
            res = await client.post("/api/v1/auth/token", data={"username": EMAIL, "password": "WrongPassword1!"})
            assert res.status_code == 401

        await db.refresh(test_user)
        assert test_user.locked_until is not None
        assert await _audit_count(db, AuditAction.login_failed, test_user.id) == MAX_FAILED_ATTEMPTS
        assert await _audit_count(db, AuditAction.account_locked, test_user.id) == 1

        # Even the right password is refused now — with the same generic message
        res = await client.post("/api/v1/auth/token", data={"username": EMAIL, "password": USER_PASSWORD})
        assert res.status_code == 401
        assert res.json()["detail"] == LOGIN_FAILED_DETAIL

    async def test_disabled_account_gets_generic_response(self, client, db, test_user):
        test_user.is_active = False
        await db.commit()
        res = await client.post("/api/v1/auth/token", data={"username": EMAIL, "password": USER_PASSWORD})
        assert res.status_code == 401
        assert res.json()["detail"] == LOGIN_FAILED_DETAIL

    async def test_public_registration_is_disabled(self, client: AsyncClient):
        res = await client.post("/api/v1/auth/register", json={
            "email": "newuser@codifyai.com", "password": "NewUserPass123!", "full_name": "New User",
        })
        assert res.status_code in (404, 405)


class TestSession:

    async def test_me(self, client: AsyncClient, auth_headers):
        res = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == EMAIL
        assert "hashed_password" not in data
        assert "mfa_secret_encrypted" not in data
        assert data["mfa_enabled"] is False

    async def test_me_unauthenticated(self, client: AsyncClient):
        assert (await client.get("/api/v1/auth/me")).status_code == 401

    async def test_me_invalid_token(self, client: AsyncClient):
        res = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer fake.token.here"})
        assert res.status_code == 401

    async def test_logout_revokes_access_and_refresh(self, client: AsyncClient, db, test_user):
        user_id = test_user.id
        res = await login(client, EMAIL)
        headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

        assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 200
        assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401

        # The refresh cookie was revoked server-side, not just cleared client-side
        client.cookies.set(REFRESH_COOKIE, res.cookies[REFRESH_COOKIE])
        assert (await client.post("/api/v1/auth/refresh")).status_code == 401
        assert await _audit_count(db, AuditAction.logout, user_id) == 1

    async def test_logout_works_without_access_token(self, client: AsyncClient, test_user):
        await login(client, EMAIL)
        assert (await client.post("/api/v1/auth/logout")).status_code == 200
        assert (await client.post("/api/v1/auth/refresh")).status_code == 401

    async def test_refresh_rotates_cookie(self, client: AsyncClient, test_user):
        first = await login(client, EMAIL)
        old_cookie = first.cookies[REFRESH_COOKIE]

        res = await client.post("/api/v1/auth/refresh")
        assert res.status_code == 200
        assert res.json()["access_token"]
        assert res.cookies[REFRESH_COOKIE] != old_cookie

    async def test_refresh_token_reuse_revokes_all_sessions(self, client: AsyncClient, db, test_user):
        user_id = test_user.id
        first = await login(client, EMAIL)
        stolen = first.cookies[REFRESH_COOKIE]
        rotated = await client.post("/api/v1/auth/refresh")
        new_access = rotated.json()["access_token"]

        # Attacker replays the old refresh token (after the race grace window)
        from datetime import timedelta
        from sqlalchemy import update
        from app.models.models import RevokedToken
        await db.execute(update(RevokedToken).values(revoked_at=RevokedToken.revoked_at - timedelta(minutes=5)))
        await db.commit()
        client.cookies.clear()
        client.cookies.set(REFRESH_COOKIE, stolen)
        assert (await client.post("/api/v1/auth/refresh")).status_code == 401

        # ...which kills the legitimate session too
        me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
        assert me.status_code == 401
        assert await _audit_count(db, AuditAction.refresh_token_reuse, user_id) == 1

    async def test_concurrent_refresh_is_not_treated_as_theft(self, client: AsyncClient, db, test_user):
        """Two tabs refreshing with the same cookie at once must not sign the user out everywhere."""
        user_id = test_user.id
        first = await login(client, EMAIL)
        old = first.cookies[REFRESH_COOKIE]
        rotated = await client.post("/api/v1/auth/refresh")
        new_access = rotated.json()["access_token"]

        client.cookies.clear()
        client.cookies.set(REFRESH_COOKIE, old)
        assert (await client.post("/api/v1/auth/refresh")).status_code == 401

        me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
        assert me.status_code == 200
        assert await _audit_count(db, AuditAction.refresh_token_reuse, user_id) == 0

    async def test_refresh_without_cookie(self, client: AsyncClient):
        assert (await client.post("/api/v1/auth/refresh")).status_code == 401

    async def test_refresh_rejects_foreign_origin(self, client: AsyncClient, test_user):
        await login(client, EMAIL)
        res = await client.post("/api/v1/auth/refresh", headers={"Origin": "https://evil.example"})
        assert res.status_code == 403

    async def test_refresh_cannot_extend_past_max_session(self, client: AsyncClient, test_user):
        old = create_refresh_token(str(test_user.id), test_user.token_version, auth_time=int(time.time()) - 13 * 3600)
        client.cookies.set(REFRESH_COOKIE, old)
        assert (await client.post("/api/v1/auth/refresh")).status_code == 401

    async def test_deactivated_user_token_rejected(self, client, db, auth_headers, test_user):
        test_user.is_active = False
        await db.commit()
        assert (await client.get("/api/v1/auth/me", headers=auth_headers)).status_code == 401


class TestChangePassword:

    async def test_change_password_revokes_other_sessions(self, client: AsyncClient, db, test_user):
        other = await login(client, EMAIL)
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        mine = await login(client, EMAIL)
        my_headers = {"Authorization": f"Bearer {mine.json()['access_token']}"}

        res = await client.post("/api/v1/auth/change-password", headers=my_headers, json={
            "current_password": USER_PASSWORD, "new_password": "NewTestPass456!",
        })
        assert res.status_code == 200
        new_headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

        assert (await client.get("/api/v1/auth/me", headers=other_headers)).status_code == 401
        assert (await client.get("/api/v1/auth/me", headers=my_headers)).status_code == 401
        assert (await client.get("/api/v1/auth/me", headers=new_headers)).status_code == 200
        assert await _audit_count(db, AuditAction.password_changed, test_user.id) == 1

    async def test_change_password_wrong_current(self, client: AsyncClient, auth_headers):
        res = await client.post("/api/v1/auth/change-password", headers=auth_headers, json={
            "current_password": "NotMyPassword1!", "new_password": "NewTestPass456!",
        })
        assert res.status_code == 400

    async def test_change_password_weak(self, client: AsyncClient, auth_headers):
        res = await client.post("/api/v1/auth/change-password", headers=auth_headers, json={
            "current_password": USER_PASSWORD, "new_password": "weak",
        })
        assert res.status_code == 422


class TestHeaders:

    async def test_security_headers_present(self, client: AsyncClient):
        res = await client.get("/health")
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("x-frame-options") == "DENY"
        assert res.headers.get("cache-control") == "no-store"


async def test_audit_log_rows_cannot_be_modified(db, test_user):
    from sqlalchemy import update, delete
    from sqlalchemy.exc import DBAPIError
    db.add(AuditLog(user_id=test_user.id, action=AuditAction.login))
    await db.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        await db.execute(update(AuditLog).values(success=False))
    await db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        await db.execute(delete(AuditLog))
    await db.rollback()


async def test_rate_limit_on_login(client: AsyncClient):
    from app.core.rate_limit import limiter
    limiter.enabled = True
    codes = [
        (await client.post("/api/v1/auth/token", data={"username": "x@y.com", "password": "Nope12345678!"})).status_code
        for _ in range(11)
    ]
    assert codes[-1] == 429
    assert set(codes[:10]) == {401}


async def test_new_user_starts_without_mfa(db):
    user = await make_user(db, "fresh@codifyai.com")
    assert isinstance(user, User) and user.mfa_enabled is False and user.token_version == 0
