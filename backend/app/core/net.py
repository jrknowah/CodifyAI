import ipaddress
from functools import lru_cache
from starlette.requests import Request
from app.core.config import settings


@lru_cache
def _trusted_networks() -> tuple:
    return tuple(ipaddress.ip_network(p, strict=False) for p in settings.trusted_proxies_list)


def _is_trusted(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in _trusted_networks())


def get_client_ip(request: Request) -> str:
    """
    The real client IP. X-Forwarded-For is only honoured when the direct peer is a
    configured trusted proxy, and then we take the right-most address that isn't
    one of our proxies — anything left of that could be forged by the client.
    """
    peer = request.client.host if request.client else "unknown"
    if not _is_trusted(peer):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    for hop in reversed([h.strip() for h in forwarded.split(",") if h.strip()]):
        if not _is_trusted(hop):
            return hop
    return peer
