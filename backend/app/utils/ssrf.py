from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class SSRFError(ValueError):
    pass


def validate_public_url(url: str, *, allow_private: bool = False) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise SSRFError("Only http/https URLs are allowed")
    if not parsed.hostname:
        raise SSRFError("URL must include a hostname")

    host = parsed.hostname.lower()
    if allow_private:
        return url

    if host in {"localhost"} or host.endswith(".localhost"):
        raise SSRFError("Private/local hostnames are blocked")

    try:
        # Prefer literal IP if hostname is already an IP
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
            addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
        except socket.gaierror as exc:
            raise SSRFError("Unable to resolve hostname") from exc

    for addr in addresses:
        for network in BLOCKED_NETWORKS:
            if addr in network:
                raise SSRFError("Private/reserved IP addresses are blocked")
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise SSRFError("Private/reserved IP addresses are blocked")

    return url
