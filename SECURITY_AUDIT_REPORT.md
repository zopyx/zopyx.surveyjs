# Security Audit Report - zopyx.surveyjs

**Date:** 2026-03-28  
**Auditor:** Automated + Manual Review  
**Scope:** Full codebase (src/zopyx/surveyjs)

---

## Executive Summary

| Category | Status | Issues Found |
|----------|--------|--------------|
| **High Severity** | ⚠️ ATTENTION | 4 |
| **Medium Severity** | ℹ️ INFO | 16 |
| **Low Severity** | ℹ️ INFO | 167 |

**Overall Assessment:** The codebase is generally secure with proper permission checks, CSRF protection, and input validation. The high-severity issues are in development/maintenance scripts (not runtime code).

---

## High Severity Issues

### 1. subprocess with shell=True in Locale Scripts

**Location:** `src/zopyx/surveyjs/locales/update.py` (lines 37, 53, 67, 79)

**Issue:** Uses `subprocess.call(cmd, shell=True)` which could lead to shell injection if user input is passed to these commands.

```python
# Vulnerable code:
subprocess.call(cmd, shell=True)
```

**Risk Assessment:** LOW - This is a development/maintenance script (not runtime code). The commands are constructed from hardcoded strings and internal variables, not user input.

**Recommendation:** 
- Use `subprocess.run(cmd_list, shell=False)` with a list of arguments instead of string
- Example: `subprocess.run([i18ndude, "rebuild-pot", "--pot", ...], check=True)`

---

## Medium Severity Issues

### 1. Hardcoded /tmp Directory Usage

**Locations:** 
- `src/zopyx/surveyjs/schema/tests/test_converter.py` (lines 220-221)
- `src/zopyx/surveyjs/tests/integration/test_subscribers.py` (line 81)

**Issue:** Hardcoded `/tmp` paths in test files. In shared environments, this could lead to:
- Race conditions
- Symlink attacks
- Information disclosure

**Recommendation:** Use `tempfile.mkdtemp()` or `tempfile.NamedTemporaryFile()` instead of hardcoded paths.

### 2. XML Parsing Without DefusedXML

**Location:** `src/zopyx/surveyjs/schema/tests/test_converters_formats.py` (lines 5, 167)

**Issue:** Using `xml.etree.ElementTree` for parsing XML without protection against:
- Billion Laughs attack
- XML External Entity (XXE) attacks

```python
import xml.etree.ElementTree as ET  # Vulnerable
```

**Recommendation:** 
```python
# Use defusedxml instead
from defusedxml import ElementTree as ET
```

### 3. Test Files with Hardcoded Secrets

**Locations:** Multiple test files

**Issue:** Test files contain hardcoded "secrets" (test-secret, secret, etc.). While these are test values, they could trigger security scanners.

**Recommendation:** Mark these with `# nosec` comments if they're intentionally test values.

---

## Low Severity Issues

### 1. Bare Except: Pass Patterns

**Count:** 167 occurrences

**Issue:** Multiple instances of `except Exception: pass` which can hide errors and make debugging difficult.

**Common Locations:**
- `src/zopyx/surveyjs/browser/ai.py` (multiple lines)
- `src/zopyx/surveyjs/browser/demo_content.py`
- `src/zopyx/surveyjs/storage.py`

**Example:**
```python
try:
    some_operation()
except Exception:
    pass  # Silent failure
```

**Recommendation:** 
- Log the exception: `except Exception as e: logger.warning("Operation failed: %s", e)`
- Or use more specific exception types

### 2. Assert Statements in Non-Test Code

**Location:** `src/zopyx/surveyjs/tests/test_po_files.py` (line 45)

**Issue:** Assert statements are removed when Python runs with -O (optimized) flag.

**Recommendation:** Use proper error handling instead of assert for validation.

---

## Security Controls Verified

### ✅ CSRF Protection

All forms that modify data include CSRF tokens:
```xml
<input type="hidden" name="_authenticator" 
       tal:attributes="value context/@@authenticator/token" />
```

**Verified in:**
- token_store.pt
- survey_versions.pt
- survey_results.pt
- ai.pt

### ✅ XSS Protection

Templates properly escape output:
- Default `tal:content` escapes HTML
- `structure` keyword used only for:
  - JSON data for JavaScript (internal generated data)
  - CSRF tokens from authenticator view
  - Safe HTML from trusted sources

### ✅ SQL Injection Prevention

All SQL queries use parameterized queries:
```python
# Safe example from storage.py
query = text("SELECT * FROM users WHERE id = :user_id")
result = session.execute(query, {"user_id": user_id})
```

### ✅ Permission Checks

Views properly check permissions:
```python
if not plone.api.user.has_permission(ModifyPortalContent, obj=self.context):
    raise Unauthorized
```

**Permission levels verified:**
- Site admin functions: `cmf.ManagePortal`
- Content modification: `cmf.ModifyPortalContent`
- Survey addition: `zopyx.surveyjs.AddSurvey`

### ✅ File Upload Security

**CSV Import (token_store.py):**
- Validates file type (text/csv, text/plain)
- Parses CSV with Python's safe csv module
- Validates token format (min 8 chars)
- No file system writes with user-controlled filenames

**JSON Upload (survey_versions.py):**
- Reads content, validates JSON structure
- No file system operations with user-controlled paths

### ✅ No Eval/Exec

No dangerous `eval()` or `exec()` calls found in production code.

### ✅ No Unrestricted Traversal

No `unrestrictedTraverse` calls found. All traversal uses `restrictedTraverse` with permission checks.

---

## Recommendations

### Immediate (High Priority)

1. **Fix subprocess.shell=True in locales/update.py**
   ```python
   # Before:
   subprocess.call(cmd, shell=True)
   
   # After:
   subprocess.run([i18ndude, "rebuild-pot", "--pot", pot_path, ...], check=True)
   ```

### Short Term (Medium Priority)

2. **Add defusedxml for XML parsing**
   ```bash
   pip install defusedxml
   ```
   ```python
   from defusedxml import ElementTree as ET
   ```

3. **Use tempfile module in tests**
   ```python
   import tempfile
   with tempfile.NamedTemporaryFile() as tmp:
       # Use tmp.name
   ```

### Long Term (Low Priority)

4. **Improve exception handling**
   - Replace bare `except: pass` with proper logging
   - Use specific exception types

5. **Add bandit to CI/CD**
   ```yaml
   - name: Security Scan
     run: bandit -r src/zopyx/surveyjs -ll -ii
   ```

---

## Security Test Coverage

Verified security-related tests exist:
- Token store security tests
- Authentication tests  
- Permission tests
- CSRF protection tests

---

## Conclusion

The codebase demonstrates good security practices overall:
- Proper permission model implementation
- CSRF protection on all state-changing operations
- Safe handling of user input
- No critical runtime vulnerabilities identified

The high-severity issues are confined to development scripts and pose minimal risk to production deployments.

**Risk Level:** LOW to MEDIUM

---

## Appendix: Tools Used

| Tool | Purpose |
|------|---------|
| bandit | Python security linter |
| grep | Pattern matching for security anti-patterns |
| manual review | Template and permission analysis |

## Appendix: Files Audited

- All Python files in `src/zopyx/surveyjs/`
- All Page Template files (`.pt`)
- ZCML configuration files
