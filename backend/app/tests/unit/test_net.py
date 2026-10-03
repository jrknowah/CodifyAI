from types import SimpleNamespace
from app.core import net
from app.core.config import settings


def _request(peer, xff=None):
    headers = {"x-forwarded-for": xff} if xff else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def _trust(monkeypatch, proxies):
    monkeypatch.setattr(settings, "trusted_proxies", proxies)
    net._trusted_networks.cache_clear()


def test_xff_ignored_without_trusted_proxies(monkeypatch):
    _trust(monkeypatch, "")
    assert net.get_client_ip(_request("203.0.113.9", "1.2.3.4")) == "203.0.113.9"


def test_xff_ignored_from_untrusted_peer(monkeypatch):
    _trust(monkeypatch, "10.0.0.0/8")
    assert net.get_client_ip(_request("203.0.113.9", "1.2.3.4")) == "203.0.113.9"


def test_xff_rightmost_untrusted_hop_from_trusted_proxy(monkeypatch):
    _trust(monkeypatch, "10.0.0.0/8")
    # Client forged "6.6.6.6"; real client is 198.51.100.7, then two internal proxies
    req = _request("10.0.0.2", "6.6.6.6, 198.51.100.7, 10.0.0.5")
    assert net.get_client_ip(req) == "198.51.100.7"
    _trust(monkeypatch, "")
