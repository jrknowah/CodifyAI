import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestAuthEndpoints:

    async def test_register_success(self, client: AsyncClient):
        res = await client.post("/api/v1/auth/register", json={
            "email": "newuser@codifyai.com",
            "password": "NewUserPass123!",
            "full_name": "New User",
        })
        assert res.status_code == 201
        data = res.json()
        assert data["email"] == "newuser@codifyai.com"
        assert "hashed_password" not in data
        assert "id" in data

    async def test_register_duplicate_email(self, client: AsyncClient):
        payload = {
            "email": "duplicate@codifyai.com",
            "password": "ValidPass123!",
            "full_name": "First User",
        }
        await client.post("/api/v1/auth/register", json=payload)
        res = await client.post("/api/v1/auth/register", json=payload)
        assert res.status_code == 409

    async def test_register_weak_password(self, client: AsyncClient):
        res = await client.post("/api/v1/auth/register", json={
            "email": "weakpass@codifyai.com",
            "password": "weak",
            "full_name": "Weak User",
        })
        assert res.status_code == 422

    async def test_login_success(self, client: AsyncClient, test_user):
        res = await client.post("/api/v1/auth/token", data={
            "username": "testcoder@codifyai.com",
            "password": "TestPass123!",
        })
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient, test_user):
        res = await client.post("/api/v1/auth/token", data={
            "username": "testcoder@codifyai.com",
            "password": "WrongPassword!",
        })
        assert res.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        res = await client.post("/api/v1/auth/token", data={
            "username": "nobody@codifyai.com",
            "password": "AnyPass123!",
        })
        assert res.status_code == 401
        # Must not reveal whether email exists
        assert "does not exist" not in res.text
        assert "not found" not in res.text.lower()

    async def test_get_me_authenticated(self, client: AsyncClient, auth_headers):
        res = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == "testcoder@codifyai.com"
        assert "hashed_password" not in data

    async def test_get_me_unauthenticated(self, client: AsyncClient):
        res = await client.get("/api/v1/auth/me")
        assert res.status_code == 401

    async def test_get_me_invalid_token(self, client: AsyncClient):
        res = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer fake.token.here"})
        assert res.status_code == 401

    async def test_logout_blacklists_token(self, client: AsyncClient, test_user):
        login = await client.post("/api/v1/auth/token", data={
            "username": "testcoder@codifyai.com",
            "password": "TestPass123!",
        })
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        logout = await client.post("/api/v1/auth/logout", headers=headers)
        assert logout.status_code == 200

        # Token should now be rejected
        me = await client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 401

    async def test_refresh_token(self, client: AsyncClient, test_user):
        login = await client.post("/api/v1/auth/token", data={
            "username": "testcoder@codifyai.com",
            "password": "TestPass123!",
        })
        refresh_token = login.json()["refresh_token"]

        res = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert res.status_code == 200
        assert "access_token" in res.json()

    async def test_security_headers_present(self, client: AsyncClient):
        res = await client.get("/health")
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("x-frame-options") == "DENY"
        assert res.headers.get("cache-control") == "no-store"

    async def test_change_password(self, client: AsyncClient, auth_headers):
        res = await client.post("/api/v1/auth/change-password", headers=auth_headers, json={
            "current_password": "TestPass123!",
            "new_password": "NewTestPass456!",
        })
        assert res.status_code == 200
