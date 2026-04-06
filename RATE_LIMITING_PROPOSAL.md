# Rate Limiting Implementation Proposal

**Date:** 2026-04-06  
**Status:** Draft for Review  
**Priority:** Medium (Post-Security Fixes)

---

## Executive Summary

This proposal outlines a comprehensive rate limiting implementation for zopyx.surveyjs based on the **existing diskcache infrastructure** already in use for token replay protection. The solution provides configurable per-endpoint rate limiting with minimal new dependencies and maximum reuse of proven patterns.

---

## Threat Model

### Current Risks (Without Rate Limiting)

| Threat | Impact | Likelihood | Risk Level |
|--------|--------|------------|------------|
| **Form Submission Flooding** | Database bloat, DoS | High | 🔴 Critical |
| **Email Action Abuse** | Spam/blacklisting | Medium | 🔴 High |
| **LLM API Cost Explosion** | Financial impact | Medium | 🔴 High |
| **Token Exhaustion** | Service degradation | Low | 🟡 Medium |
| **Credential Stuffing** | Account compromise | Low | 🟡 Medium |

### Attack Scenarios

1. **Submission Spam:** Attacker scripts 1000s of form submissions/minute
2. **Email Bomb:** Automated surveys trigger mail actions to harass recipients
3. **AI Upload Abuse:** Large PDFs uploaded rapidly to exhaust LLM API quotas
4. **Token Harvesting:** Rapid token generation attempts to find valid sequences

---

## Proposed Architecture

### Design Principles

1. **Leverage Existing Infrastructure:** Reuse diskcache from `AuthService`
2. **Fail-Open Gracefully:** Don't break functionality if cache unavailable
3. **Configurable Per-Endpoint:** Different limits for different risk profiles
4. **Dual-Key Strategy:** Rate limit by IP + by session/user where available
5. **Sliding Window:** Smooth rate limiting without burst issues

### Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     RateLimitService                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   IP-Based      │  │  Session-Based  │  │   User-Based    │  │
│  │   Limits        │  │     Limits      │  │     Limits      │  │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  │
│           └────────────────────┼────────────────────┘           │
│                                ▼                                │
│                    ┌─────────────────────┐                      │
│                    │    diskcache        │                      │
│                    │  (existing path)    │                      │
│                    └─────────────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  save_poll    │     │ upload_document│     │ @@embed-token │
│  (submissions)│     │   (AI upload)  │     │(token gen)    │
└───────────────┘     └───────────────┘     └───────────────┘
```

---

## Implementation Details

### 1. New Interface Fields (IFormsSettings)

```python
# Add to src/zopyx/surveyjs/interfaces.py

fieldset(
    "rate_limiting",
    label="Rate Limiting",
    fields=(
        "rate_limiting_enabled",
        "rate_limit_submissions_per_ip",
        "rate_limit_submissions_window",
        "rate_limit_ai_uploads_per_ip",
        "rate_limit_ai_uploads_window",
        "rate_limit_token_gen_per_ip",
        "rate_limit_token_gen_window",
        "rate_limit_burst_factor",
    ),
)

rate_limiting_enabled = schema.Bool(
    title="Enable Rate Limiting",
    description="Enable rate limiting on form submissions and sensitive endpoints.",
    default=True,
    required=False,
)

rate_limit_submissions_per_ip = schema.Int(
    title="Submissions per IP",
    description="Maximum form submissions allowed per IP per time window.",
    default=30,
    required=False,
)

rate_limit_submissions_window = schema.Int(
    title="Submission Rate Window (seconds)",
    description="Time window for submission rate limiting.",
    default=60,
    required=False,
)

rate_limit_ai_uploads_per_ip = schema.Int(
    title="AI Uploads per IP",
    description="Maximum AI document uploads per IP per window.",
    default=10,
    required=False,
)

rate_limit_ai_uploads_window = schema.Int(
    title="AI Upload Rate Window (seconds)",
    description="Time window for AI upload rate limiting.",
    default=3600,  # 1 hour
    required=False,
)

rate_limit_token_gen_per_ip = schema.Int(
    title="Token Generation per IP",
    description="Maximum embed token generations per IP per window.",
    default=20,
    required=False,
)

rate_limit_token_gen_window = schema.Int(
    title="Token Generation Window (seconds)",
    description="Time window for token generation rate limiting.",
    default=3600,
    required=False,
)

rate_limit_burst_factor = schema.Float(
    title="Burst Factor",
    description="Multiplier for burst allowance (e.g., 2.0 allows double the rate briefly).",
    default=2.0,
    required=False,
)
```

### 2. RateLimitService Implementation

Create `src/zopyx/surveyjs/browser/services/rate_limit.py`:

```python
"""Rate limiting service using diskcache.

Built on existing diskcache infrastructure from AuthService.
Provides sliding window rate limiting with dual-key support.
"""

import logging
import time
from typing import Optional, Tuple

import diskcache
from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from ...interfaces import IFormsSettings

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
        import hashlib
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
```

### 3. Integration Points

#### A. Form Submissions (views.py)

```python
# In src/zopyx/surveyjs/browser/views.py

from .services.rate_limit import RateLimitService, RateLimitExceeded

def save_poll(self):
    """Save poll with rate limiting."""
    # Initialize rate limiter
    rate_limiter = RateLimitService(self.context, self.request)
    
    try:
        # Check rate limit (30 requests per minute per IP)
        settings = rate_limiter._load_settings()
        limit = getattr(settings, "rate_limit_submissions_per_ip", 30)
        window = getattr(settings, "rate_limit_submissions_window", 60)
        
        rate_limiter.check_rate_limit(
            endpoint="save_poll",
            limit=limit,
            window=window,
            key_type="ip"
        )
    except RateLimitExceeded as e:
        return json_error(
            self.request.response,
            429,
            "rate_limit_exceeded",
            message="Too many submissions. Please slow down."
        )
    finally:
        rate_limiter.close()
    
    # ... rest of save_poll logic
```

#### B. AI Upload (ai.py)

```python
# In src/zopyx/surveyjs/browser/ai.py

def upload_document(self):
    """Handle document upload with rate limiting."""
    from .services.rate_limit import RateLimitService
    
    rate_limiter = RateLimitService(self.context, self.request)
    
    try:
        settings = rate_limiter._load_settings()
        limit = getattr(settings, "rate_limit_ai_uploads_per_ip", 10)
        window = getattr(settings, "rate_limit_ai_uploads_window", 3600)
        
        rate_limiter.check_rate_limit(
            endpoint="ai_upload",
            limit=limit,
            window=window,  # 10 uploads per hour
            key_type="ip"
        )
    except RateLimitExceeded:
        return self._redirect_ai(
            "Upload limit reached. Please try again later.",
            "error"
        )
    finally:
        rate_limiter.close()
    
    # ... rest of upload logic
```

#### C. Token Generation (embed_direct.py)

```python
# In src/zopyx.surveyjs/browser/embed_direct.py

class EmbedDirectTokenView(BrowserView):
    """Generate embedding tokens with rate limiting."""
    
    def __call__(self):
        from .services.rate_limit import RateLimitService
        
        rate_limiter = RateLimitService(self.context, self.request)
        
        try:
            settings = rate_limiter._load_settings()
            limit = getattr(settings, "rate_limit_token_gen_per_ip", 20)
            window = getattr(settings, "rate_limit_token_gen_window", 3600)
            
            rate_limiter.check_rate_limit(
                endpoint="embed_token_gen",
                limit=limit,
                window=window,
                key_type="ip"
            )
        except RateLimitExceeded as e:
            json_error(
                self.request.response,
                429,
                "rate_limit_exceeded",
                message="Token generation limit reached."
            )
            return
        finally:
            rate_limiter.close()
        
        # ... rest of token generation
```

### 4. HTTP Response Headers

Add rate limit headers to responses (similar to GitHub API):

```python
# In RateLimitService

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
```

---

## Configuration Examples

### Conservative (High Security)

```python
rate_limiting_enabled = True
rate_limit_submissions_per_ip = 10        # 10 submissions/minute
rate_limit_submissions_window = 60
rate_limit_ai_uploads_per_ip = 5          # 5 AI uploads/hour
rate_limit_ai_uploads_window = 3600
rate_limit_token_gen_per_ip = 10          # 10 tokens/hour
rate_limit_token_gen_window = 3600
rate_limit_burst_factor = 1.5             # 50% burst
```

### Balanced (Default)

```python
rate_limiting_enabled = True
rate_limit_submissions_per_ip = 30        # 30 submissions/minute
rate_limit_submissions_window = 60
rate_limit_ai_uploads_per_ip = 10         # 10 AI uploads/hour
rate_limit_ai_uploads_window = 3600
rate_limit_token_gen_per_ip = 20          # 20 tokens/hour
rate_limit_token_gen_window = 3600
rate_limit_burst_factor = 2.0             # 100% burst
```

### Permissive (Low Traffic Sites)

```python
rate_limiting_enabled = True
rate_limit_submissions_per_ip = 60        # 60 submissions/minute
rate_limit_submissions_window = 60
rate_limit_ai_uploads_per_ip = 20         # 20 AI uploads/hour
rate_limit_ai_uploads_window = 3600
rate_limit_token_gen_per_ip = 50          # 50 tokens/hour
rate_limit_token_gen_window = 3600
rate_limit_burst_factor = 3.0             # 200% burst
```

### Disabled (Emergency)

```python
rate_limiting_enabled = False
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_rate_limit.py

import time
import unittest
from unittest.mock import Mock, patch

from zopyx.surveyjs.browser.services.rate_limit import (
    RateLimitService,
    RateLimitExceeded
)


class TestRateLimitService(unittest.TestCase):
    """Test rate limiting service."""
    
    def setUp(self):
        self.context = Mock()
        self.request = Mock()
        self.request.getClientAddr.return_value = "192.168.1.1"
        self.request.get_header.return_value = None
        self.request.cookies = {}
    
    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    def test_check_rate_limit_allows_under_limit(self, mock_cache_class):
        """Test that requests under limit are allowed."""
        mock_cache = Mock()
        mock_cache.get.return_value = []
        mock_cache_class.return_value = mock_cache
        
        service = RateLimitService(self.context, self.request)
        
        # Should not raise
        result = service.check_rate_limit("test_endpoint", 10, 60)
        self.assertTrue(result)
    
    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    def test_check_rate_limit_blocks_over_limit(self, mock_cache_class):
        """Test that requests over limit are blocked."""
        mock_cache = Mock()
        # Simulate 10 requests in last minute
        mock_cache.get.return_value = [time.time() - i for i in range(10)]
        mock_cache_class.return_value = mock_cache
        
        service = RateLimitService(self.context, self.request)
        
        with self.assertRaises(RateLimitExceeded):
            service.check_rate_limit("test_endpoint", 10, 60)
    
    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    def test_sliding_window_expires_old_requests(self, mock_cache_class):
        """Test that old requests outside window are expired."""
        mock_cache = Mock()
        # 5 requests 2 minutes ago, 5 requests now
        now = time.time()
        mock_cache.get.return_value = [
            now - 120, now - 119, now - 118,  # Outside window
            now - 10, now - 5, now - 1       # Inside window
        ]
        mock_cache_class.return_value = mock_cache
        
        service = RateLimitService(self.context, self.request)
        
        # Should allow (only 3 in window)
        result = service.check_rate_limit("test_endpoint", 5, 60)
        self.assertTrue(result)
    
    def test_fail_open_when_cache_unavailable(self):
        """Test that requests are allowed when cache fails."""
        with patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache") as mock:
            mock.side_effect = Exception("Cache error")
            
            service = RateLimitService(self.context, self.request)
            
            # Should allow (fail-open)
            result = service.check_rate_limit("test_endpoint", 10, 60)
            self.assertTrue(result)
```

### Integration Tests

```python
# tests/test_rate_limit_integration.py

import time
import unittest
from plone.app.testing import TEST_USER_ID, setRoles
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING


class TestRateLimitIntegration(unittest.TestCase):
    """Integration tests for rate limiting."""
    
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING
    
    def setUp(self):
        self.portal = self.layer["portal"]
        self.request = self.layer["request"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
    
    def test_save_poll_rate_limit_headers(self):
        """Test that rate limit headers are present on responses."""
        # Make request
        view = self.portal.unrestrictedTraverse("@@save_poll")
        response = view()
        
        # Check headers
        self.assertIn("X-RateLimit-Limit", response.headers)
        self.assertIn("X-RateLimit-Remaining", response.headers)
    
    def test_rate_limit_blocks_excessive_requests(self):
        """Test that excessive requests are blocked with 429."""
        # Make 31 requests (limit is 30)
        for i in range(31):
            view = self.portal.unrestrictedTraverse("@@save_poll")
            response = view()
        
        # Last request should be 429
        self.assertEqual(response.status, 429)
        self.assertIn("Retry-After", response.headers)
```

---

## Monitoring & Alerting

### Log-Based Metrics

```python
# Monitor these log patterns:

# Rate limit exceeded (potential attack)
"Rate limit exceeded: endpoint=%s key=%s"

# Rate limit burst (warning)
"Rate limit burst: key=%s count=%d/%d"

# Cache unavailable (infrastructure issue)
"Rate limit cache unavailable - allowing request"
```

### Prometheus-Style Metrics

```python
# Optional: Add metrics collection

RATE_LIMIT_HITS = Counter(
    "surveyjs_rate_limit_hits_total",
    "Total rate limit hits",
    ["endpoint"]
)

RATE_LIMIT_BLOCKS = Counter(
    "surveyjs_rate_limit_blocks_total",
    "Total rate limit blocks",
    ["endpoint"]
)

RATE_LIMIT_LATENCY = Histogram(
    "surveyjs_rate_limit_check_seconds",
    "Rate limit check latency"
)
```

---

## Rollout Plan

### Phase 1: Implementation (Week 1)
- [ ] Implement `RateLimitService`
- [ ] Add interface fields to `IFormsSettings`
- [ ] Write unit tests
- [ ] Write integration tests

### Phase 2: Integration (Week 2)
- [ ] Integrate with `save_poll` endpoint
- [ ] Integrate with `upload_document` endpoint
- [ ] Integrate with `@@embed-token` endpoint
- [ ] Add rate limit headers

### Phase 3: Testing (Week 3)
- [ ] Load testing with rate limiting enabled
- [ ] Test fail-open behavior
- [ ] Verify cache performance
- [ ] Test configuration changes

### Phase 4: Deployment (Week 4)
- [ ] Deploy with default (balanced) settings
- [ ] Monitor logs for rate limit events
- [ ] Adjust limits based on traffic patterns
- [ ] Document operational procedures

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **diskcache (selected)** | Already used, proven, persistent | File-based, single-node | Use |
| Redis | Distributed, fast | New dependency, infrastructure | Overkill |
| In-memory dict | Simple, fast | Not shared across workers, lost on restart | Not suitable |
| Nginx rate limit | External, fast | Less granular, no per-form limits | Partial solution |
| Plone caching | Integrated | Complex, overkill for this use case | Not suitable |

---

## Conclusion

This rate limiting implementation leverages existing infrastructure (diskcache) to provide:

1. **Immediate Protection** Against submission flooding and API abuse
2. **Operational Flexibility** Via Plone registry configuration
3. **Graceful Degradation** Fail-open if cache unavailable
4. **Low Overhead** Reuses proven token cache infrastructure
5. **Observability** Comprehensive logging and headers

**Estimated Effort:** 3-4 days implementation + 1 week testing
**Risk Level:** Low (proven patterns, fail-open)
**Breaking Changes:** None (opt-in via settings)

---

## Next Steps

1. **Review this proposal** with security team
2. **Approve approach** and prioritize in backlog
3. **Create implementation ticket** with this spec
4. **Schedule for next sprint**

---

*Document generated based on existing zopyx.surveyjs codebase patterns and diskcache infrastructure.*
