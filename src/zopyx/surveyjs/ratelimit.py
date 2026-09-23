# -*- coding: utf-8 -*-
"""Admission control (rate limiting) for public survey submissions.

``@@save-poll`` counts *attempts*, not accepted submissions: every request that
reaches the limiter consumes one slot in a per-survey, per-client minute and
hour bucket, so a rejected flood keeps its own budget drained instead of being
invisible to the counters (which is what the monitoring counters do — they run
after ``notify()``).

Buckets are fixed windows in the configured KV store (namespace
``ratelimit``), keyed by survey UID, a digest of the client address and the
window index, and they expire on their own.  The counter update is a
read-modify-write, so two fully concurrent requests can both read the same
count and admit one request more than the limit allows; the counter is bounded
and never loses more than that, which is the accepted trade-off for keeping the
hot path to one read and one write.

The limiter **fails closed**: without the KV store the submission is refused
with HTTP 503 (``rate_limit_unavailable``) instead of being admitted, matching
the authenticity-token and embed-token behaviour.

Client address: ``REMOTE_ADDR`` by default.  Behind a reverse proxy that is the
proxy's address, so ``submission_rate_limit_trust_proxy`` switches the limiter
to the right-most ``X-Forwarded-For`` entry — the one the trusted proxy
appended.  Only enable it when every request actually passes through that
proxy, otherwise clients can forge their own bucket key.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from .interfaces import IFormsSettings
from .kv import KVStore, get_configured_kv_store

logger = logging.getLogger(__name__)

#: KV namespace holding the rate-limit buckets.
KV_NAMESPACE = "ratelimit"

#: Defaults used when the registry records do not exist yet (fresh or
#: not-yet-saved sites) — the limiter is on unless it is switched off.
DEFAULT_ENABLED = True
DEFAULT_PER_MINUTE = 120
DEFAULT_PER_HOUR = 1200
DEFAULT_TRUST_PROXY = False

MINUTE_WINDOW_SECONDS = 60
HOUR_WINDOW_SECONDS = 3600

#: Reasons reported by :class:`RateLimitDecision`.
REASON_OK = "ok"
REASON_DISABLED = "disabled"
REASON_LIMIT_EXCEEDED = "rate_limited"
REASON_STORE_UNAVAILABLE = "store_unavailable"


class RateLimitStoreError(Exception):
    """Raised when the bucket store cannot be read or written."""


@dataclass(frozen=True)
class RateLimitSettings:
    """Effective rate-limit configuration of the site."""

    enabled: bool = DEFAULT_ENABLED
    per_minute: int = DEFAULT_PER_MINUTE
    per_hour: int = DEFAULT_PER_HOUR
    trust_proxy: bool = DEFAULT_TRUST_PROXY


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of one submission admission check."""

    allowed: bool
    reason: str = REASON_OK
    limit: Optional[int] = None
    count: int = 0
    retry_after: int = 0
    minute_count: int = 0
    hour_count: int = 0


def _positive_int(value: Any, default: int) -> int:
    """Return ``value`` as a positive int, or ``default`` when unusable."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def load_rate_limit_settings(settings: Any = None) -> RateLimitSettings:
    """Return the configured rate limits, falling back to the defaults.

    ``settings`` may be an already resolved :class:`RateLimitSettings`, a
    registry settings object (read through ``getattr``) or ``None`` to read the
    current site registry.  Registry records may be absent on a site that never
    saved the Forms settings; the defaults then apply (enabled).
    """
    if isinstance(settings, RateLimitSettings):
        return settings
    if settings is None:
        try:
            registry = getUtility(IRegistry)
            settings = registry.forInterface(IFormsSettings, check=False)
        except Exception:
            logger.debug("Rate limit settings unavailable; using defaults")
            return RateLimitSettings()
    return RateLimitSettings(
        enabled=bool(getattr(settings, "submission_rate_limit_enabled", DEFAULT_ENABLED)),
        per_minute=_positive_int(
            getattr(settings, "submission_rate_limit_per_minute", DEFAULT_PER_MINUTE),
            DEFAULT_PER_MINUTE,
        ),
        per_hour=_positive_int(
            getattr(settings, "submission_rate_limit_per_hour", DEFAULT_PER_HOUR),
            DEFAULT_PER_HOUR,
        ),
        trust_proxy=bool(
            getattr(settings, "submission_rate_limit_trust_proxy", DEFAULT_TRUST_PROXY)
        ),
    )


def _header(request, name: str) -> str:
    """Return the HTTP header ``name`` (``""`` when absent)."""
    get_header = getattr(request, "get_header", None) or getattr(
        request, "getHeader", None
    )
    value = None
    if get_header is not None:
        try:
            value = get_header(name)
        except Exception:
            value = None
    if not value:
        try:
            value = request.get("HTTP_" + name.upper().replace("-", "_"))
        except Exception:
            value = None
    return str(value or "").strip()


def client_address(request, *, trust_proxy: bool = DEFAULT_TRUST_PROXY) -> str:
    """Return the client address used as rate-limit identity.

    ``REMOTE_ADDR`` is read from the request environment (the WSGI key); with
    ``trust_proxy`` the right-most ``X-Forwarded-For`` entry — the one the
    trusted proxy appended — takes precedence.
    """
    if trust_proxy:
        forwarded = _header(request, "X-Forwarded-For")
        if forwarded:
            candidate = forwarded.split(",")[-1].strip()
            if candidate:
                return candidate
    try:
        remote_addr = request.get("REMOTE_ADDR") or ""
    except Exception:
        remote_addr = ""
    return str(remote_addr).strip() or _header(request, "REMOTE_ADDR")


def _identity(context, address: str) -> str:
    """Return the survey-scoped, non-reversible bucket identity."""
    try:
        survey_identifier = context.UID()
    except Exception:
        survey_identifier = context.getId()
    digest = hashlib.sha256(address.encode("utf-8")).hexdigest()[:16]
    return f"{survey_identifier}:{digest}"


def _open_store() -> KVStore:
    """Open the configured ratelimit KV store."""
    registry = getUtility(IRegistry)
    settings = registry.forInterface(IFormsSettings, check=False)
    return get_configured_kv_store(settings, KV_NAMESPACE)


def _consume(
    store: KVStore,
    unit: str,
    identity: str,
    now: float,
    limit: int,
    window_seconds: int,
) -> tuple[int, bool]:
    """Count one attempt in the current ``unit`` window.

    Returns ``(count, allowed)``; raises :class:`RateLimitStoreError` when the
    bucket cannot be read or written.
    """
    window_index = int(now // window_seconds)
    key = f"{unit}:{identity}:{window_index}"
    try:
        current = store.get(key, 0)
        count = current + 1 if isinstance(current, int) else 1
        # Keep the bucket one window longer than the window itself: a slow
        # request must not be able to resurrect a counter after it expired.
        store.set(key, count, expire=window_seconds * 2)
    except Exception as exc:
        raise RateLimitStoreError(str(exc)) from exc
    return count, count <= limit


def _retry_after(now: float, window_seconds: int) -> int:
    """Return seconds until the current window rolls over."""
    remaining = window_seconds - (now % window_seconds)
    return max(1, int(remaining))


def check_submission_rate_limit(context, request, settings: Any = None):
    """Count one submission attempt for ``context`` and admit or refuse it.

    Returns a :class:`RateLimitDecision`.  A decision with
    ``reason == REASON_STORE_UNAVAILABLE`` means the limiter could not be
    evaluated and the caller must fail closed.
    """
    config = load_rate_limit_settings(settings)
    if not config.enabled:
        return RateLimitDecision(True, REASON_DISABLED)

    identity = _identity(context, client_address(request, trust_proxy=config.trust_proxy))
    try:
        store = _open_store()
    except Exception as exc:
        logger.error("Rate limit store unavailable: %s", exc)
        return RateLimitDecision(False, REASON_STORE_UNAVAILABLE)

    try:
        now = time.time()
        minute_count, minute_allowed = _consume(
            store, "m", identity, now, config.per_minute, MINUTE_WINDOW_SECONDS
        )
        hour_count, hour_allowed = _consume(
            store, "h", identity, now, config.per_hour, HOUR_WINDOW_SECONDS
        )
    except RateLimitStoreError as exc:
        logger.error("Rate limit store unavailable: %s", exc)
        return RateLimitDecision(False, REASON_STORE_UNAVAILABLE)
    finally:
        try:
            store.close()
        except Exception:
            logger.debug("Rate limit store close failed", exc_info=True)

    if minute_allowed and hour_allowed:
        return RateLimitDecision(
            True,
            REASON_OK,
            count=minute_count,
            minute_count=minute_count,
            hour_count=hour_count,
        )

    exceeded_minute = not minute_allowed
    return RateLimitDecision(
        False,
        REASON_LIMIT_EXCEEDED,
        limit=config.per_minute if exceeded_minute else config.per_hour,
        count=minute_count if exceeded_minute else hour_count,
        retry_after=_retry_after(
            now, MINUTE_WINDOW_SECONDS if exceeded_minute else HOUR_WINDOW_SECONDS
        ),
        minute_count=minute_count,
        hour_count=hour_count,
    )
