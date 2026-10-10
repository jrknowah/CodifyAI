"""ENFORCE_HTTPS behaviour behind the Container Apps ingress."""
from app.core import net
from app.core.config import settings


async def test_plain_http_is_redirected_when_https_enforced(client, monkeypatch):
    monkeypatch.setattr(settings, "enforce_https", True)
    resp = await client.get("/api/v1/coding/history", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"].startswith("https://")


async def test_health_probe_over_plain_http_is_not_redirected(client, monkeypatch):
    monkeypatch.setattr(settings, "enforce_https", True)
    resp = await client.get("/health", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_forwarded_https_from_trusted_proxy_is_not_redirected(client, monkeypatch):
    monkeypatch.setattr(settings, "enforce_https", True)
    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.1/32")
    net._trusted_networks.cache_clear()
    try:
        resp = await client.get(
            "/api/v1/coding/history",
            headers={"X-Forwarded-Proto": "https"},
            follow_redirects=False,
        )
        assert resp.status_code != 301
    finally:
        net._trusted_networks.cache_clear()
