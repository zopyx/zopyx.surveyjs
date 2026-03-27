# Security Action Items - Immediate Priority

**Date:** 2026-03-27  
**Project:** zopyx.surveyjs  

---

## 🚨 CRITICAL - Fix Within 7 Days

### 1. SSRF Vulnerability in POST Action (CWE-918)

**File:** `src/zopyx/surveyjs/subscribers.py:560-572`

**Problem:** The `post_endpoint_url` setting accepts any URL without validation, allowing attackers to target internal services.

**Attack:** Configure survey POST action to `http://169.254.169.254/latest/meta-data/` to steal AWS credentials.

**Fix:**
```python
# Add to subscribers.py
def _validate_post_url(url: str) -> bool:
    from urllib.parse import urlparse
    import ipaddress
    
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    
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
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            return False
    except ValueError:
        pass
    
    return True

# Use before httpx.post()
if not _validate_post_url(endpoint_url):
    logger.warning("POST action blocked: invalid URL %s", endpoint_url)
    return
```

---

## 🔴 HIGH - Fix Within 30 Days

### 2. Overly Permissive Export Endpoints

**File:** `src/zopyx/surveyjs/browser/configure.zcml:233-252`

**Problem:** Data export endpoints use `zope2.View` permission, allowing any viewer to download all form submissions.

**Fix:**
```xml
<!-- Change these lines -->
<browser:page name="download-polls-csv" permission="cmf.ModifyPortalContent" ... />
<browser:page name="download-polls-json" permission="cmf.ModifyPortalContent" ... />
<browser:page name="download-form-json" permission="cmf.ModifyPortalContent" ... />
```

### 3. Replay Protection Fails Open

**File:** `src/zopyx/surveyjs/browser/services/auth.py:403`

**Problem:** When diskcache is unavailable, `require_auth_token()` returns `True`, bypassing replay protection.

**Fix:**
```python
# Line ~385-403: Change the final return
        cache = self._token_cache(settings)
        if cache is None:
            # FAIL CLOSED - reject when cache unavailable
            if logger:
                logger.error("Auth token cache unavailable - rejecting request")
            json_error(self.request.response, 503, "auth_service_unavailable")
            return False  # Changed from True
        
        try:
            received_key = self._received_cache_key(token)
            added = self._cache_add(cache, received_key, "RECEIVED")
            if not added:
                # ... replay detected ...
                return False
        finally:
            cache.close()
        return True
```

### 4. Error Information Disclosure

**File:** `src/zopyx/surveyjs/browser/views.py` (multiple locations)

**Problem:** Error responses include exception strings that may reveal internal paths.

**Fix:**
```python
# Instead of:
json_error(self.request.response, 500, "validation_error", message=str(exc))

# Use:
logger.exception("Validation error: %s", exc)
json_error(self.request.response, 500, "validation_error", 
           message="An error occurred processing your request")
```

---

## 🟡 MEDIUM - Fix Within 90 Days

### 5. Add Rate Limiting

**Priority:** Prevents abuse of email actions and submission flooding

**Implementation approach:**
- Use diskcache for rate limit tracking
- Per-IP limits: 10 requests/minute for submissions
- Per-form limits: Configurable per survey

### 6. Add Audit Logging

**Priority:** Compliance and forensics

**Implementation approach:**
- Log all data exports (CSV/JSON downloads)
- Log authentication failures
- Log admin configuration changes

### 7. File Upload Validation

**Priority:** Prevent abuse of AI PDF upload feature

**Implementation approach:**
- Add file size limits (50MB max)
- Validate MIME type via python-magic
- Scan for PDF structure validity

---

## 📋 Quick Verification Checklist

After applying fixes, verify:

- [ ] POST action rejects `http://localhost/` URLs
- [ ] POST action rejects `http://169.254.169.254/` URLs
- [ ] Export endpoints require `ModifyPortalContent` permission
- [ ] Replay protection rejects tokens when cache is stopped
- [ ] Error messages don't include file paths
- [ ] Rate limiting blocks excessive requests
- [ ] Audit logs capture export events

---

## 🧪 Test Commands

```bash
# Test SSRF prevention
make test TESTARGS="-k test_ssrf"

# Test replay protection
make test TESTARGS="-k test_replay"

# Test permission changes
make test TESTARGS="-k test_permissions"

# Run all security tests
make test TESTARGS="-k security"
```

---

**Next Steps:**
1. Implement CRITICAL fix immediately
2. Schedule HIGH priority fixes for next sprint
3. Add security tests to CI pipeline
4. Schedule security review after fixes are deployed
