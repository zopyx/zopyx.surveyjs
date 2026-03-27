# Remaining Security Issues

**Date:** 2026-03-27  
**Status:** Post-Review

---

## Summary

| Priority | Issue | Severity | Status |
|----------|-------|----------|--------|
| P1 | Export endpoint permissions | 🔴 High | ❌ **NOT FIXED** |
| P2 | Error message info disclosure | 🔴 High | ❌ **NOT FIXED** |
| P3 | Rate limiting on submissions | 🟡 Medium | ❌ **NOT FIXED** |
| P4 | Audit logging for exports | 🟡 Medium | ❌ **NOT FIXED** |
| P5 | File upload validation | 🟡 Medium | ❌ **NOT FIXED** |

---

## P1: Export Endpoint Permissions (HIGH)

**File:** `src/zopyx/surveyjs/browser/configure.zcml:233-252`

**Problem:** Data export endpoints use `zope2.View` permission.

```xml
<!-- Current (vulnerable) -->
<browser:page name="download-polls-csv" permission="zope2.View" ... />
```

**Fix:** Change to `cmf.ModifyPortalContent`

```bash
# Apply this fix:
sed -i 's/name="download-form-json"/{n;s/permission="zope2.View"/permission="cmf.ModifyPortalContent"/}' src/zopyx/surveyjs/browser/configure.zcml
sed -i 's/name="download-polls-json"/{n;s/permission="zope2.View"/permission="cmf.ModifyPortalContent"/}' src/zopyx/surveyjs/browser/configure.zcml
sed -i 's/name="download-polls-csv"/{n;s/permission="zope2.View"/permission="cmf.ModifyPortalContent"/}' src/zopyx/surveyjs/browser/configure.zcml
```

**Impact:** Breaking change - users with only View permission will lose export access.

---

## P2: Error Message Information Disclosure (HIGH)

**Files:** `src/zopyx/surveyjs/browser/views.py` (multiple locations)

**Problem:** Exception details exposed in JSON error responses:

```python
# Current (vulnerable)
json_error(..., message=str(exc))  # May contain file paths
```

**Fix:** Log details server-side, return generic message to client:

```python
# Fixed
logger.exception("Validation error: %s", exc)
json_error(..., message="An error occurred. Please try again.")
```

**Locations to fix:**
- Line ~955
- Line ~1037  
- Line ~1193
- Line ~1938

---

## P3: Rate Limiting on Submissions (MEDIUM)

**Files:** `browser/views.py` (save_poll), `browser/ai.py` (upload_document)

**Problem:** No rate limiting allows:
- Submission spam / flooding
- Email abuse (if mail action enabled)
- LLM API cost explosion (AI endpoints)

**Fix Options:**
1. **Simple in-memory rate limiter**
2. **Diskcache-based rate limiting**
3. **Nginx/reverse proxy rate limiting** (recommended)

```python
# Example diskcache-based implementation
def check_rate_limit(self, key: str, max_requests: int = 10, window: int = 60) -> bool:
    cache = self._token_cache(settings)
    now = time.time()
    cache_key = f"ratelimit:{key}"
    
    requests = cache.get(cache_key, [])
    requests = [t for t in requests if now - t < window]
    
    if len(requests) >= max_requests:
        return False
    
    requests.append(now)
    cache.set(cache_key, requests, expire=window)
    return True
```

---

## P4: Audit Logging for Data Exports (MEDIUM)

**Files:** `browser/views.py` (download_polls_csv, download_polls_json, download_form_json)

**Problem:** Bulk data exports are not logged.

**Fix:** Add audit logging:

```python
def download_polls_csv(self):
    logger.warning(
        "BULK_EXPORT: user=%s survey=%s format=csv",
        plone.api.user.get_current().getId(),
        self.context.absolute_url()
    )
    # ... rest of method ...
```

---

## P5: File Upload Validation (MEDIUM)

**Files:** `browser/ai.py`, `browser/views.py`

**Problem:** PDF uploads for AI processing don't validate:
- File size limits
- MIME type via magic bytes
- Content structure

**Fix:**

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
        return False, f"File too large (max {MAX_UPLOAD_SIZE} bytes)"
    
    # Check magic bytes
    mime = magic.from_buffer(uploaded_file.read(2048), mime=True)
    uploaded_file.seek(0)
    
    if mime not in ALLOWED_MIME_TYPES:
        return False, f"Invalid file type: {mime}"
    
    return True, ""
```

**Dependency needed:** `python-magic`

---

## Low Priority Items (Optional)

| Issue | Severity | Notes |
|-------|----------|-------|
| Clickjacking on embed | 🟢 Low | By design for iframe embedding |
| Timing attacks | 🟢 Low | HMAC comparison is constant-time |
| Session binding | 🟢 Low | Design tradeoff per EXTENDED_SECURITY.md |
| Dependency pinning | 🟢 Low | Supply chain hardening |

---

## Recommended Priority Order

### Immediate (This Week)
1. **P2 - Error message sanitization** (Low effort, high impact)
2. **P4 - Audit logging** (Low effort, compliance benefit)

### Short Term (Next Sprint)
3. **P1 - Export permissions** (Breaking change, needs communication)
4. **P5 - File upload validation** (Medium effort, security hardening)

### Medium Term (Next Month)
5. **P3 - Rate limiting** (Higher effort, infrastructure change)

---

## Completed Fixes ✅

| Fix | File | Status |
|-----|------|--------|
| Replay protection fail-closed | `browser/services/auth.py` | ✅ Applied |
| SSRF documentation | `sec.md` | ⚠️ By Design |

---

## Quick Fix Script

```bash
#!/bin/bash
# Apply P1: Export permissions (breaking change!)

FILE="src/zopyx/surveyjs/browser/configure.zcml"

# Backup
cp $FILE $FILE.bak

# Fix permissions
sed -i '/name="download-form-json"/{n;s/permission="zope2.View"/permission="cmf.ModifyPortalContent"/}' $FILE
sed -i '/name="download-polls-json"/{n;s/permission="zope2.View"/permission="cmf.ModifyPortalContent"/}' $FILE
sed -i '/name="download-polls-csv"/{n;s/permission="zope2.View"/permission="cmf.ModifyPortalContent"/}' $FILE

echo "Permissions updated. Verify with:"
grep -A1 'name="download-.*-json"\|name="download-.*-csv"' $FILE | grep permission
```

---

**Next Steps:**
1. Review P1-P5 priorities with team
2. Decide on breaking change communication for P1
3. Create tickets for each remaining issue
4. Schedule fixes for upcoming sprints
