"""Validation helpers for outbound requests to configured survey endpoints."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from .interfaces import IFormsSettings


POST_ENDPOINT_TIMEOUT = 10.0
_ALLOWED_SCHEMES = frozenset({"http", "https"})


def get_post_endpoint_policy() -> dict[str, object]:
    """Return the site-wide outbound POST policy from the Plone registry."""
    settings = getUtility(IRegistry).forInterface(IFormsSettings, check=False)
    return {
        "mode": getattr(settings, "post_endpoint_validation_mode", "public")
        or "public",
        "allowlist": getattr(settings, "post_endpoint_allowlist", ()) or (),
    }


def validate_post_endpoint_url(
    url: object,
    *,
    mode: str = "public",
    allowlist: object = (),
) -> str:
    """Return *url* when it is safe enough for an outbound POST.

    DNS is resolved before the request and every returned address is checked.
    This intentionally fails closed when DNS cannot be resolved; otherwise a
    typo or a transient resolver response could bypass the private-address
    protection.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("endpoint URL is empty")

    endpoint = url.strip()
    parsed = urlsplit(endpoint)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError("endpoint URL must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("endpoint URL must not contain credentials")
    if not parsed.hostname:
        raise ValueError("endpoint URL has no hostname")
    if mode not in {"public", "allowlist"}:
        raise ValueError("unknown endpoint validation mode")

    hostname = parsed.hostname.rstrip(".").lower()
    if mode == "allowlist" and not _hostname_allowed(hostname, allowlist):
        raise ValueError("endpoint hostname is not on the allowlist")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("endpoint URL has an invalid port") from exc
    port = port or (443 if parsed.scheme.lower() == "https" else 80)

    try:
        addresses = {
            ipaddress.ip_address(info[4][0])
            for info in socket.getaddrinfo(
                parsed.hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        }
    except (OSError, ValueError) as exc:
        raise ValueError("endpoint hostname could not be resolved") from exc

    if not addresses:
        raise ValueError("endpoint hostname has no addresses")
    if any(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        for address in addresses
    ):
        raise ValueError("endpoint hostname resolves to a blocked address")

    return endpoint


def _hostname_allowed(hostname: str, allowlist: object) -> bool:
    """Match an endpoint hostname against exact or ``*.suffix`` entries."""
    if not isinstance(allowlist, (list, tuple, set, frozenset)):
        return False
    for item in allowlist:
        if not isinstance(item, str):
            continue
        pattern = item.strip().rstrip(".").lower()
        if not pattern:
            continue
        if pattern.startswith("*."):
            suffix = pattern[2:]
            if suffix and hostname.endswith("." + suffix):
                return True
        elif hostname == pattern:
            return True
    return False
