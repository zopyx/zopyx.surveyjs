# In-Depth Security Analysis: zopyx.surveyjs

**Analysis Date:** 2026-03-27  
**Scope:** Complete codebase review of zopyx.surveyjs Plone add-on  
**Version:** Current HEAD (post-EXTENDED_SECURITY.md implementation)

---

## Executive Summary

The zopyx.surveyjs package is a Plone add-on that integrates SurveyJS for form creation and management. It implements a multi-layered security architecture including JWT-based authenticity tokens, replay protection via diskcache, trusted access modes, and direct DOM embedding security. This analysis reviews implemented controls, identifies residual risks, and provides remediation recommendations.

### Risk Summary

| Severity | Count | Categories |
|----------|-------|------------|
| 🚨 Critical | 1 | SSRF via POST action |
| 🔴 High | 3 | Permission model, replay protection, information disclosure |
| 🟡 Medium | 4 | Rate limiting, audit logging, dependency management |
| 🟢 Low | 3 | Security headers, timing attacks, session binding |

---

## 🛡️ Security Architecture Overview

### Implemented Security Controls

| Control | Implementation | Status |
|---------|---------------|--------|
| **CSRF Protection** | Plone's built-in CSRF tokens | ✅ Active |
| **JWT Authenticity Tokens** | Custom HMAC-SHA256, form/version binding | ✅ Active |
| **Replay Protection** | Diskcache-based nonce tracking (jti) | ✅ Active |
| **Payload Size Limits** | `max_payload_size_mb` per survey | ✅ Active |
| **Trusted Access Modes** | Cache-based and Token Store-based | ✅ Active |
| **Direct DOM Embedding** | Origin-bound JWTs, one-time tokens | ✅ Active |
| **External Validation** | Optional Deno binary validation | ✅ Optional |
| **Audit Logging** | Persistent logger for changes | ✅ Active |

### Authentication & Authorization Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Request Processing Flow                       │
├─────────────────────────────────────────────────────────────────┤
│ 1. CORS Preflight (if applicable)                               │
│    └── Origin validation against allowlist                      │
│                                                                 │
│ 2. Trusted Access Check (if enabled)                            │
│    ├── "trusted" mode: Cache-based token validation             │
│    └── "trusted-tokens" mode: ITokenStore adapter               │
│                                                                 │
│ 3. Authenticity Token Validation (if enabled)                   │
│    ├── JWT signature verification (HS256)                       │
│    ├── Claims validation (iss, aud, exp, nbf, iat)              │
│    ├── Form/version binding check                               │
│    └── Replay protection (diskcache jti tracking)               │
│                                                                 │
│ 4. Direct DOM Embed Validation (if applicable)                  │
│    ├── Origin validation                                        │
│    ├── JWT token validation (PyJWT)                             │
│    └── One-time use enforcement (jti tracking)                  │
│                                                                 │
│ 5. Form Submission Processing                                   │
│    └── Event subscribers (store, mail, post actions)            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚨 Critical Severity Findings

### 1. SSRF via POST Action Endpoint (CWE-918)

**Location:** `src/zopyx/surveyjs/subscribers.py:560-572`

**Description:**
The `post_endpoint_url` is user-configurable per survey without validation or an allowlist. An attacker can configure the endpoint to target internal services.

**Current Code:**
```python
endpoint_url = getattr(context, "post_endpoint_url", None)
# ... no validation ...
response = httpx.post(endpoint_url, json=payload, timeout=10.0)
```

**Attack Scenarios:**
1. **AWS Metadata Service:** `http://169.254.169.254/latest/meta-data/`
2. **Internal Services:** `http://localhost:8080/admin/`
3. **Cloud Provider Metadata:** GCP, Azure internal endpoints
4. **Port Scanning:** Iterate through internal IP ranges

**Impact:**
- Cloud credential exfiltration
- Internal infrastructure access
- Data exfiltration to attacker-controlled servers

**Remediation (High Priority):**
```python
import ipaddress
from urllib.parse import urlparse

def _validate_post_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    
    # Block private/reserved IPs
    blocked_hosts = {
        'localhost', '127.0.0.1', '::1',
        '169.254.169.254',  # AWS metadata
        'metadata.google.internal',
        'metadata.google.internal.'
    }
    if parsed.hostname in blocked_hosts:
        return False
    
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast:
            return False
    except ValueError:
        pass  # Not an IP, continue with hostname checks
    
    return True
```

**References:**
- [OWASP SSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- CWE-918

---

## 🔴 High Severity Findings

### 2. Overly Permissive Endpoint Permissions (CWE-285)

**Location:** `src/zopyx/surveyjs/browser/configure.zcml:189-252`

**Description:**
Several sensitive endpoints are exposed with `zope2.View` permission instead of stronger permissions like `cmf.ModifyPortalContent`.

**Affected Endpoints:**
| Endpoint | Current Permission | Risk |
|----------|-------------------|------|
| `save-form-json` | `zope2.View` | Form modification by any viewer |
| `save-poll` | `zope2.View` | Submission spam (partially mitigated by tokens) |
| `get-polls-json` | `zope2.View` | Data enumeration |
| `get-polls-json2` | `zope2.View` | Data enumeration |
| `download-form-json` | `zope2.View` | Schema exfiltration |
| `download-polls-json` | `zope2.View` | Bulk data export |
| `download-polls-csv` | `zope2.View` | Bulk data export |

**Impact:**
- Unauthorized data access
- Bulk data exfiltration
- Form schema theft

**Remediation:**
Review and tighten permissions:
```xml
<!-- Change from: -->
<browser:page name="download-polls-csv" permission="zope2.View" ... />

<!-- To: -->
<browser:page name="download-polls-csv" permission="cmf.ModifyPortalContent" ... />
```

### 3. Replay Protection Fails Open (CWE-294)

**Location:** `src/zopyx/surveyjs/browser/services/auth.py:385-403`

**Description:**
When the diskcache is unavailable, `require_auth_token()` silently returns `True`, bypassing replay protection.

**Current Code:**
```python
cache = self._token_cache(settings)
if cache is not None:
    try:
        # ... replay check ...
    finally:
        cache.close()
return True  # Bypasses if cache is None!
```

**Impact:**
- Token replay attacks possible when cache is down
- Reduced security during cache failures

**Remediation:**
```python
def require_auth_token(self, form_version_id, logger=None):
    settings = self._auth_settings()
    if not self._auth_token_enabled(settings):
        return True
    
    cache = self._token_cache(settings)
    if cache is None:
        # Fail secure - reject if cache unavailable
        if logger:
            logger.error("Auth token cache unavailable - rejecting request")
        json_error(self.request.response, 503, "auth_service_unavailable")
        return False
    
    try:
        # ... validation logic ...
    finally:
        cache.close()
```

### 4. Information Disclosure via Error Messages (CWE-209)

**Location:** Multiple locations in `browser/views.py`

**Description:**
Error responses include exception details that may reveal internal paths or system information.

**Examples:**
```python
# Line ~955, ~1037, ~1193
json_error(..., message=str(exc))  # May contain file paths
```

**Remediation:**
```python
def safe_json_error(response, status, error_code, message=None, exc=None):
    """Return safe error message to user, log details internally."""
    if exc:
        logger.error("Internal error: %s", exc, exc_info=True)
    
    # Generic messages for production
    user_message = message or "An error occurred. Please try again."
    json_response(response, {"error": error_code, "message": user_message}, status=status)
```

---

## 🟡 Medium Severity Findings

### 5. Missing Rate Limiting (CWE-770)

**Location:** `save_poll`, `ai-upload`, PDF import endpoints

**Description:**
No rate limiting is implemented on form submission endpoints. Combined with email actions, this creates a vector for abuse.

**Attack Scenarios:**
1. **Storage Exhaustion:** Flood submissions to fill database/ZODB
2. **Email Spam:** Form with "mail" action sends emails on each submission
3. **LLM Cost Explosion:** AI form generation endpoints can be abused

**Remediation:**
Implement rate limiting using diskcache or Plone's caching infrastructure:
```python
from functools import wraps
import time

def rate_limit(max_requests=10, window=60):
    """Decorator to rate limit view methods."""
    def decorator(func):
        cache = {}
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            key = self.request.getClientAddr() or self.request.get("REMOTE_ADDR")
            now = time.time()
            
            # Clean old entries
            cache[key] = [t for t in cache.get(key, []) if now - t < window]
            
            if len(cache[key]) >= max_requests:
                json_error(self.request.response, 429, "rate_limit_exceeded")
                return
            
            cache[key].append(now)
            return func(self, *args, **kwargs)
        return wrapper
    return decorator
```

### 6. Missing Audit Logging for Data Access

**Description:**
While metadata changes are audited via `log_metadata_changes`, bulk data exports (CSV/JSON downloads) lack audit logging.

**Remediation:**
Add audit logging to export endpoints:
```python
def download_polls_csv(self):
    logger.warning(
        "Bulk export: user=%s survey=%s format=csv",
        plone.api.user.get_current().getId(),
        self.context.absolute_url()
    )
    # ... existing logic ...
```

### 7. File Upload Validation Gaps

**Location:** `src/zopyx/surveyjs/browser/views.py`, `browser/ai.py`

**Description:**
PDF uploads for AI processing and form import don't validate:
- File size limits
- MIME type via magic bytes
- Content structure before processing

**Remediation:**
```python
import magic

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_MIME_TYPES = {'application/pdf', 'application/x-pdf'}

def validate_pdf_upload(uploaded_file) -> tuple[bool, str]:
    # Check size
    uploaded_file.seek(0, 2)
    size = uploaded_file.tell()
    uploaded_file.seek(0)
    
    if size > MAX_UPLOAD_SIZE:
        return False, f"File too large"
    
    # Check magic bytes
    mime = magic.from_buffer(uploaded_file.read(2048), mime=True)
    uploaded_file.seek(0)
    
    if mime not in ALLOWED_MIME_TYPES:
        return False, f"Invalid file type: {mime}"
    
    return True, ""
```

### 8. Dependency Management

**Description:**
Dependencies are declared without hash pinning, exposing the project to supply chain attacks.

**Remediation:**
```
# requirements.txt with hashes
orjson==3.9.10 \
    --hash=sha256:abcdef...
diskcache==5.6.3 \
    --hash=sha256:123456...
```

---

## 🟢 Low Severity Findings

### 9. Permissive Security Headers for Embedding

**Location:** `src/zopyx/surveyjs/browser/views.py:1080-1085`

**Description:**
The `EmbedViewer` removes X-Frame-Options and sets a permissive CSP to allow iframe embedding from any origin.

**Current Code:**
```python
self.request.response.setHeader("X-Frame-Options", "")
self.request.response.setHeader("Content-Security-Policy", "frame-ancestors *")
```

**Risk:** Clickjacking attacks on forms

**Remediation:**
Allow specific origins only:
```python
def __call__(self):
    allowed_origins = getattr(self.context, 'embedding_origins', [])
    if not allowed_origins:
        self.request.response.setStatus(403)
        return "Embedding is not configured for this survey."
    
    origins_str = ' '.join(allowed_origins)
    self.request.response.setHeader("Content-Security-Policy", f"frame-ancestors {origins_str}")
```

### 10. Timing Attack Possibility (CWE-208)

**Description:**
Different validation error paths have different execution times. However, HMAC comparison uses `hmac.compare_digest()` which is constant-time.

**Risk:** Low - signature comparison is secure

### 11. Weak Session Binding (CWE-384)

**Description:**
JWT tokens do not include session_id or user_id binding. Tokens can be used across different sessions. This is an intentional design tradeoff (per EXTENDED_SECURITY.md to avoid IP-based binding issues).

---

## 📊 Attack Matrix

| Attack Vector | Severity | Exploitability | Impact | Mitigation Status |
|--------------|----------|----------------|--------|-------------------|
| SSRF via POST Action | 🚨 Critical | High | Data exfiltration, infra access | ❌ Not mitigated |
| Permission bypass on exports | 🔴 High | Medium | Data exfiltration | ❌ Not mitigated |
| Replay when cache down | 🔴 High | Low | Token replay | ⚠️ Partial (fails open) |
| Info disclosure via errors | 🔴 High | Low | Reconnaissance | ⚠️ Partial |
| Rate limiting bypass | 🟡 Medium | High | DoS, cost explosion | ❌ Not mitigated |
| Missing audit on exports | 🟡 Medium | Medium | No accountability | ❌ Not mitigated |
| File upload abuse | 🟡 Medium | Medium | Resource exhaustion | ⚠️ Partial |
| Clickjacking | 🟢 Low | Low | UI redressing | ⚠️ By design |
| Timing attacks | 🟢 Low | Low | Token validation leak | ✅ Mitigated |

---

## 🛠️ Remediation Roadmap

### Immediate (Fix within 7 days)

1. **Implement URL validation for POST action endpoints**
   - Block private IP ranges
   - Block cloud metadata endpoints
   - Add allowlist option for administrators

2. **Fix replay protection to fail closed**
   - Reject requests when cache is unavailable
   - Add monitoring for cache failures

### Short-term (Fix within 30 days)

3. **Review and tighten endpoint permissions**
   - Change export endpoints to `cmf.ModifyPortalContent`
   - Document permission model clearly

4. **Sanitize error messages in production**
   - Remove exception details from client responses
   - Log full details server-side

5. **Add rate limiting for submission endpoints**
   - Per-IP rate limiting
   - Per-form rate limiting
   - Configurable thresholds

### Medium-term (Fix within 90 days)

6. **Add comprehensive audit logging**
   - Log all data exports
   - Log authentication failures
   - Log admin actions

7. **Implement file upload validation**
   - Size limits
   - MIME type validation
   - Content scanning

8. **Dependency hardening**
   - Hash pinning
   - Vulnerability scanning
   - SBOM generation

---

## 🔐 Security Best Practices for Deployment

### 1. Network Security
```nginx
# Nginx reverse proxy configuration
location / {
    # Rate limiting
    limit_req zone=form_submissions burst=20 nodelay;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    proxy_pass http://plone_backend;
}
```

### 2. Registry Settings Checklist

| Setting | Recommended Value | Reason |
|---------|------------------|--------|
| `authenticity_token_enabled` | `True` | Enable token validation |
| `authenticity_token_secret` | 32+ random chars | Strong signing key |
| `authenticity_token_ttl_seconds` | 300-600 | Short-lived tokens |
| `embed_direct_signing_key` | 32+ random chars | Separate from auth tokens |
| `embed_direct_global_enabled` | `False` (enable per-site) | Defense in depth |
| `log_ip_addresses` | `True` | Audit trail |
| `log_user_agent` | `True` | Audit trail |

### 3. Monitoring & Alerting

```python
# Log-based alerts to configure
ALERT_PATTERNS = [
    "auth_token_replay",           # Possible replay attack
    "trusted_access_denied",       # Unauthorized access attempts
    "embed.submission.rejected",   # Embedding abuse
    "rate_limit_exceeded",         # Potential DoS
    "external_validation_failed",  # Validation bypass attempts
]
```

---

## 🧪 Security Testing Recommendations

### Unit Tests
```python
class TestSSRFPrevention(unittest.TestCase):
    """Test POST action URL validation."""
    
    def test_blocks_private_ips(self):
        blocked_urls = [
            'http://169.254.169.254/latest/meta-data/',
            'http://localhost:8080/admin',
            'http://127.0.0.1:22/',
            'http://10.0.0.1/internal',
        ]
        for url in blocked_urls:
            self.assertFalse(_validate_post_url(url))

class TestReplayProtection(unittest.TestCase):
    """Test token replay detection."""
    
    def test_replay_detected(self):
        token = generate_token()
        # First use should succeed
        self.assertTrue(validate_token(token))
        # Second use should fail
        self.assertFalse(validate_token(token))
    
    def test_fails_closed_when_cache_down(self):
        # Simulate cache failure
        with mock.patch('diskcache.Cache', side_effect=Exception):
            self.assertFalse(validate_token(token))
```

### Integration Tests
```python
class TestEndToEndSecurity(unittest.TestCase):
    """End-to-end security tests."""
    
    def test_submission_without_token_rejected(self):
        # Test that submissions without auth_token are rejected
        pass
    
    def test_expired_token_rejected(self):
        # Test that expired tokens are rejected
        pass
    
    def test_cross_form_token_rejected(self):
        # Test that tokens from one form don't work on another
        pass
```

---

## 📚 References

- [OWASP Top 10 2021](https://owasp.org/Top10/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Plone Security](https://plone.org/security)
- [SurveyJS Security](https://surveyjs.io/documentation)
- [JWT Best Practices (RFC 8725)](https://tools.ietf.org/html/rfc8725)

---

## Appendix: Files by Security Relevance

| File | Purpose | Lines | Risk Level |
|------|---------|-------|------------|
| `browser/views.py` | Main view handlers | ~1160 | 🚨 Critical |
| `subscribers.py` | Email/POST actions | ~677 | 🚨 Critical |
| `browser/services/auth.py` | Token auth | ~403 | 🔴 High |
| `security.py` | JWT implementation | ~117 | 🔴 High |
| `browser/embed_security.py` | Embed security | ~387 | 🔴 High |
| `adapters/token_store.py` | Token storage | ~120 | 🟡 Medium |
| `browser/configure.zcml` | Permission config | ~570 | 🔴 High |

---

*This analysis was generated based on automated code review and manual inspection. Penetration testing is recommended for critical deployments.*
