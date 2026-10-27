"""DoH (DNS over HTTPS) resolver for requests.

Provides DNS resolution via Cloudflare (1.1.1.1) and Google (8.8.8.8) DoH endpoints.
"""
from __future__ import annotations

import logging
import socket
from functools import lru_cache
from typing import Optional

import requests

log = logging.getLogger("doh")

# DoH endpoints
DOH_ENDPOINTS = [
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/dns-query",
]

# DNS record types
DNS_TYPE_A = 1
DNS_TYPE_AAAA = 28


class DoHResolver:
    """DNS resolver using DoH (DNS over HTTPS)."""

    def __init__(self, endpoints: Optional[list[str]] = None, timeout: int = 5):
        self.endpoints = endpoints or DOH_ENDPOINTS
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/dns-json",
            "User-Agent": "PyCache-DoH/1.0",
        })

    @lru_cache(maxsize=1024)
    def resolve(self, hostname: str, family: int = socket.AF_INET) -> list[str]:
        """Resolve hostname to IP addresses using DoH.

        Args:
            hostname: The hostname to resolve
            family: socket.AF_INET for IPv4, socket.AF_INET6 for IPv6

        Returns:
            List of IP addresses as strings
        """
        qtype = DNS_TYPE_A if family == socket.AF_INET else DNS_TYPE_AAAA

        for endpoint in self.endpoints:
            try:
                resp = self._session.get(
                    endpoint,
                    params={"name": hostname, "type": qtype},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()

                if data.get("Status") == 0 and "Answer" in data:
                    ips = []
                    for answer in data["Answer"]:
                        if answer.get("type") == qtype:
                            ip = answer.get("data", "").strip()
                            if ip:
                                ips.append(ip)
                    if ips:
                        log.debug("DoH resolved %s to %s via %s", hostname, ips, endpoint)
                        return ips
            except Exception as exc:
                log.warning("DoH resolution failed for %s via %s: %s", hostname, endpoint, exc)
                continue

        # Fallback to system resolver
        log.debug("Falling back to system resolver for %s", hostname)
        return self._system_resolve(hostname, family)

    def _system_resolve(self, hostname: str, family: int) -> list[str]:
        """Fallback to system DNS resolver."""
        try:
            infos = socket.getaddrinfo(hostname, None, family, socket.SOCK_STREAM)
            ips = list({info[4][0] for info in infos})
            log.debug("System resolved %s to %s", hostname, ips)
            return ips
        except socket.gaierror as exc:
            log.error("System DNS resolution failed for %s: %s", hostname, exc)
            return []


def create_doh_session() -> requests.Session:
    """Create a requests Session configured with DoH DNS resolution.

    Note: This uses a simple approach where we resolve via DoH but then connect
    to the hostname normally (relying on system DNS which is already configured
    via Docker to use 1.1.1.1 and 8.8.8.8). The DoH resolution is used for
    logging/debugging purposes and as a fallback.
    """
    resolver = DoHResolver()
    session = requests.Session()
    session.resolver = resolver

    # Don't monkey-patch - let the system DNS (configured via Docker) handle resolution
    # The DoH resolver is available via session.resolver for debugging/probing

    return session


# Global DoH session for use by downloader
_doh_session: Optional[requests.Session] = None


def get_doh_session() -> requests.Session:
    """Get or create the global DoH session."""
    global _doh_session
    if _doh_session is None:
        _doh_session = create_doh_session()
    return _doh_session