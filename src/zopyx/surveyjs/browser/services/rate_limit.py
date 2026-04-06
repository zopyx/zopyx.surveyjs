"""Rate limiting service using diskcache.

Built on existing diskcache infrastructure from AuthService.
Provides sliding window rate limiting with dual-key support.
"""

import hashlib
import logging
import time
from typing import Optional, Tuple

import diskcache
from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from ...interfaces import IFormsSettings
from .http import json_error

logger = logging.getLogger(__name__)

# Cache key prefixes
KEY_PREFIX_IP = "ratelimit:ip"
KEY_PREFIX_SESSION = "ratelimit:session"
KEY_PREFIX_USER = "ratelimit:user"


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, limit: int, window: int, retry_after: int):
        self.limit = limit
        self.window = window
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after} seconds.")


class RateLimitService:
    """Rate limiting service using diskcache.

    Leverages existing diskcache infrastructure for persistence.
    Implements sliding window algorithm for smooth rate limiting.
    """

    def __init__(self, context, request):
        """Initialize with context and request for key extraction."""
        self.context = context
        self.request = request
        self._settings = None
        self._cache = None

    def _load_settings(self) -> IFormsSettings:
        """Load rate limiting settings from registry."""
        if self._settings is None:
            registry = getUtility(IRegistry)
            self._settings = registry.forInterface(IFormsSettings, check=False)
        return self._settings

    def _get_cache(self) -> Optional[diskcache.Cache]:
        """Get diskcache instance, returning None if unavailable.

        Reuses the same cache path as AuthService for simplicity.
        """
        if self._cache is not None:
            return self._cache

        settings = self._load_settings()
        # Use same cache path as AuthService for shared infrastructure
        path = getattr(settings, "authenticity_token_cache_path", "") or "var/token_cache.db"

        try:
            self._cache = diskcache.Cache(path)
            return self._cache
        except Exception as e:
            logger.error("Failed to open rate limit cache at %s: %s", path, e)
            return None

    def _get_client_ip(self) -> str:
        """Extract client IP from request."""
        # Check for forwarded headers (when behind proxy)
        forwarded = self.request.get_header("X-Forwarded-For")
        if forwarded:
            # Take first IP in chain
            return forwarded.split(",")[0].strip()

        real_ip = self.request.get_header("X-Real-Ip")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct client address
        return self.request.getClientAddr() or "unknown"

    def _get_session_id(self) -> Optional[str]:
        """Extract session identifier if available."""
        # Check for existing survey session cookie
        return self.request.cookies.get("surveyjs_session")

    def _get_user_id(self) -> Optional[str]:
        """Get authenticated user ID if available."""
        user = self.request.get("AUTHENTICATED_USER")
        if user and user.getId():
            return user.getId()

        # Check for embed token session
        token_data = getattr(self.request, "_embed_token_payload", None)
        if token_data:
            return f"embed:{token_data.get('sub', 'unknown')}"

        return None

    def _build_cache_key(self, endpoint: str, key_type: str, identifier: str) -> str:
        """Build standardized cache key.

        Format: ratelimit:{type}:{endpoint_hash}:{identifier}
        """
        endpoint_hash = hashlib.sha256(endpoint.encode()).hexdigest()[:16]
        return f"{KEY_PREFIX_IP}:{endpoint_hash}:{identifier}"

    def _sliding_window_check(
        self,
        cache: diskcache.Cache,
        key: str,
        limit: int,
        window: int,
        burst_factor: float = 2.0
    ) -> Tuple[bool, int, int]:
        """Perform sliding window rate limit check.

        Args:
            cache: diskcache instance
            key: Rate limit key
            limit: Maximum requests allowed in window
            window: Time window in seconds
            burst_factor: Multiplier for burst allowance

        Returns:
            Tuple of (allowed, current_count, retry_after)
            - allowed: True if request should proceed
            - current_count: Current request count in window
            - retry_after: Seconds until retry (0 if allowed)
        """
        now = time.time()

        # Get existing request timestamps
        requests = cache.get(key, [])

        # Filter to current window
        window_start = now - window
        requests = [ts for ts in requests if ts > window_start]

        # Calculate burst limit
        burst_limit = int(limit * burst_factor)

        # Check if under limit
        if len(requests) < limit:
            # Under normal limit - allow
            requests.append(now)
            cache.set(key, requests, expire=window)
            return True, len(requests), 0

        if len(requests) < burst_limit:
            # In burst zone - allow but warn
            logger.warning(
                "Rate limit burst: key=%s count=%d/%d",
                key, len(requests), burst_limit
            )
            requests.append(now)
            cache.set(key, requests, expire=window)
            return True, len(requests), 0

        # Over limit - calculate retry after
        oldest_request = min(requests)
        retry_after = int(oldest_request + window - now) + 1

        # Store updated requests (with failed attempt counted)
        requests.append(now)
        cache.set(key, requests, expire=window)

        return False, len(requests), max(retry_after, 1)

    def check_rate_limit(
        self,
        endpoint: str,
        limit: int,
        window: int,
        key_type: str = "ip",
        burst_factor: Optional[float] = None
    ) -> bool:
        """Check if current request is within rate limit.

        Args:
            endpoint: Endpoint identifier (e.g., "save_poll", "ai_upload")
            limit: Maximum requests allowed
            window: Time window in seconds
            key_type: Type of key to use ("ip", "session", "user")
            burst_factor: Override default burst factor

        Returns:
            True if request is allowed

        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        settings = self._load_settings()

        # Check if rate limiting is globally disabled
        if not getattr(settings, "rate_limiting_enabled", True):
            return True

        # Get cache (fail-open if unavailable)
        cache = self._get_cache()
        if cache is None:
            logger.warning("Rate limit cache unavailable - allowing request")
            return True

        # Get identifier based on key type
        if key_type == "ip":
            identifier = self._get_client_ip()
        elif key_type == "session":
            identifier = self._get_session_id()
            if identifier is None:
                # Fall back to IP if no session
                identifier = self._get_client_ip()
                key_type = "ip"
        elif key_type == "user":
            identifier = self._get_user_id()
            if identifier is None:
                # Fall back to IP if not authenticated
                identifier = self._get_client_ip()
                key_type = "ip"
        else:
            identifier = self._get_client_ip()

        # Build cache key
        key = self._build_cache_key(endpoint, key_type, identifier)

        # Use default burst factor if not specified
        if burst_factor is None:
            burst_factor = getattr(settings, "rate_limit_burst_factor", 2.0)

        try:
            allowed, count, retry_after = self._sliding_window_check(
                cache, key, limit, window, burst_factor
            )

            if not allowed:
                logger.warning(
                    "Rate limit exceeded: endpoint=%s key=%s count=%d limit=%d",
                    endpoint, key, count, limit
                )
                raise RateLimitExceeded(limit, window, retry_after)

            return True

        except RateLimitExceeded:
            raise
        except Exception as e:
            # Fail-open on unexpected errors
            logger.error("Rate limit check failed: %s", e)
            return True

    def add_rate_limit_headers(self, response, endpoint: str, limit: int, window: int):
        """Add X-RateLimit-* headers to response."""
        cache = self._get_cache()
        if cache is None:
            return

        key = self._build_cache_key(endpoint, "ip", self._get_client_ip())
        requests = cache.get(key, [])

        now = time.time()
        window_start = now - window
        requests_in_window = [ts for ts in requests if ts > window_start]

        remaining = max(0, limit - len(requests_in_window))
        reset_time = int(now + window) if requests_in_window else int(now)

        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        response.headers["X-RateLimit-Window"] = str(window)

    def close(self):
        """Close cache connection."""
        if self._cache is not None:
            try:
                self._cache.close()
            except Exception:
                pass
            self._cache = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


def rate_limit_endpoint(
    endpoint: str,
    limit: int,
    window: int,
    key_type: str = "ip"
):
    """Decorator for applying rate limiting to view methods.

    Usage:
        @rate_limit_endpoint("save_poll", 30, 60)
        def save_poll(self):
            ...
    """
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            service = RateLimitService(self.context, self.request)
            try:
                service.check_rate_limit(endpoint, limit, window, key_type)
                return func(self, *args, **kwargs)
            except RateLimitExceeded as e:
                response = json_error(
                    self.request.response,
                    429,  # Too Many Requests
                    "rate_limit_exceeded",
                    message=f"Too many requests. Please try again in {e.retry_after} seconds."
                )
                response.headers["Retry-After"] = str(e.retry_after)
                return response
            finally:
                service.close()
        return wrapper
    return decorator
