# Security Findings Validation (`secanalyze.md`)

This file validates each claim from `secanalyze.md` against the current repository state.

## Verdict Summary

| # | Finding | Verdict |
|---|---------|---------|
| 1 | SSRF via POST Action Endpoint | Valid |
| 2 | Command Injection via ImageMagick/pdfcpu | False positive (as written) |
| 3 | Weak JWT Secret Handling | Partially valid |
| 4 | Missing Rate Limiting | Valid |
| 5 | XSS via SurveyJS Form Rendering | Plausible / unproven |
| 6 | Insecure Deserialization via JSON Parsing | Misclassified / mostly invalid |
| 7 | Lack of Input Validation on File Uploads | Partially valid |
| 8 | Information Disclosure via Error Messages | Valid |
| 9 | Insecure Temporary File Handling | False positive |
| 10 | Missing Authorization on Data Export | Valid (and understated) |
| 11 | Replay Attack via Token Reuse | Valid |
| 12 | Email Header Injection | Likely false positive |
| 13 | Timing Attacks | Theoretical / low practical risk |
| 14 | Weak Session Binding | Design tradeoff, not concrete vuln |
| 15 | Dependency Confusion | Generic risk, not specific finding |
| 16 | Missing Security Headers | Valid (intentional tradeoff) |

## Detailed Validation

### 1. SSRF via POST Action Endpoint (CWE-918)
**Verdict:** Valid

- `post_endpoint_url` is consumed directly and used in `httpx.post()`.
- No URL validation / allowlist / IP-range blocking is implemented.

Evidence:
- `src/zopyx/surveyjs/subscribers.py:531`
- `src/zopyx/surveyjs/subscribers.py:561`

### 2. Command Injection via ImageMagick/pdfcpu (CWE-78)
**Verdict:** False positive (as written)

- Calls use `subprocess.run([...])` with argv lists, not shell command strings.
- Temporary filenames used for tool invocation are fixed (`uploaded.pdf`, `uploaded.png`) and not taken from attacker filename input.

Evidence:
- `src/zopyx/surveyjs/browser/views.py:1817`
- `src/zopyx/surveyjs/browser/services/pdf.py:53`
- `src/zopyx/surveyjs/pdf_form_extract.py:48`

### 3. Weak JWT Secret Handling (CWE-798)
**Verdict:** Partially valid

- Secret defaults to empty and is read from registry.
- If empty, token generation returns empty and validation rejects (`auth_token_config_missing`), so “forged with empty secret” is overstated.
- Still a configuration-hardening issue (no minimum entropy enforcement).

Evidence:
- `src/zopyx/surveyjs/interfaces.py:287`
- `src/zopyx/surveyjs/browser/services/auth.py:58`
- `src/zopyx/surveyjs/browser/services/auth.py:122`
- `src/zopyx/surveyjs/browser/services/auth.py:238`

### 4. Missing Rate Limiting (CWE-770)
**Verdict:** Valid

- No request throttling for submission endpoint (`save_poll`).

Evidence:
- `src/zopyx/surveyjs/browser/views.py:1233`

### 5. XSS via SurveyJS Form Rendering (CWE-79)
**Verdict:** Plausible / unproven from repo only

- Form JSON is loaded directly into `new Survey.Model(result)`.
- No explicit server-side HTML sanitization found in this codebase.
- Actual exploitability depends on SurveyJS runtime behavior/options.

Evidence:
- `src/zopyx/surveyjs/browser/static/viewer.js:310`

### 6. Insecure Deserialization via JSON Parsing (CWE-502)
**Verdict:** Misclassified / mostly invalid

- This is JSON parsing (`orjson.loads`), not unsafe object deserialization.
- DoS risk from large payloads is partially mitigated by payload size checks in critical paths.

Evidence:
- `src/zopyx/surveyjs/browser/views.py:1259`
- `src/zopyx/surveyjs/browser/views.py:1302`

### 7. Lack of Input Validation on File Uploads (CWE-434)
**Verdict:** Partially valid

- PDF upload/import paths do not enforce MIME magic checks.
- No explicit size limit check in upload/import path.
- Path traversal claim via filename is not supported by current usage in subprocess calls.

Evidence:
- `src/zopyx/surveyjs/browser/views.py:935`
- `src/zopyx/surveyjs/browser/views.py:1772`

### 8. Information Disclosure via Error Messages (CWE-209)
**Verdict:** Valid

- Multiple endpoints return `message=str(exc)` to clients.

Evidence:
- `src/zopyx/surveyjs/browser/views.py:955`
- `src/zopyx/surveyjs/browser/views.py:1037`
- `src/zopyx/surveyjs/browser/views.py:1193`
- `src/zopyx/surveyjs/browser/views.py:1938`

### 9. Insecure Temporary File Handling (CWE-377)
**Verdict:** False positive

- `tempfile.TemporaryDirectory()` defaults to secure permissions (`0700`) on this platform.

Evidence:
- `src/zopyx/surveyjs/browser/views.py:1810`
- `src/zopyx/surveyjs/browser/services/pdf.py:46`

### 10. Missing Authorization on Data Export (CWE-285)
**Verdict:** Valid (and understated)

- Claim says protected by `cmf.ModifyPortalContent`; actual ZCML for exports is `zope2.View`.
- This is weaker than stated and may expose bulk data to viewers.

Evidence:
- `src/zopyx/surveyjs/browser/configure.zcml:247`
- `src/zopyx/surveyjs/browser/configure.zcml:248`
- `src/zopyx/surveyjs/browser/configure.zcml:249`
- `src/zopyx/surveyjs/browser/views.py:1437`

### 11. Replay Attack via Token Reuse (CWE-294)
**Verdict:** Valid

- If token cache is unavailable, replay-prevention insertion/check is skipped and function returns `True` after signature/claim validation.

Evidence:
- `src/zopyx/surveyjs/browser/services/auth.py:274`
- `src/zopyx/surveyjs/browser/services/auth.py:292`

### 12. Email Header Injection (CWE-93)
**Verdict:** Likely false positive

- Uses Python `EmailMessage` API, which generally rejects newline header injection in header values.
- No direct raw-header concatenation found.

Evidence:
- `src/zopyx/surveyjs/subscribers.py:500`
- `src/zopyx/surveyjs/subscribers.py:505`

### 13. Information Leakage via Timing Attacks (CWE-208)
**Verdict:** Theoretical / low practical risk

- Signature compare uses constant-time `hmac.compare_digest`.
- Other branch timing differences exist but are not clearly actionable in this context.

Evidence:
- `src/zopyx/surveyjs/security.py:84`

### 14. Weak Session Binding (CWE-384)
**Verdict:** Design tradeoff, not concrete vulnerability

- Tokens include expiry and claims; replay protection is implemented (cache-dependent).
- Lack of session/IP binding can be acceptable based on product requirements.

Evidence:
- `src/zopyx/surveyjs/security.py:41`
- `src/zopyx/surveyjs/browser/services/auth.py:278`

### 15. Dependency Confusion (CWE-1104)
**Verdict:** Generic supply-chain risk, not a specific code finding

- Dependencies are declared normally; no direct indicator of dependency confusion exploitability in-repo.

Evidence:
- `setup.py:51`

### 16. Missing Security Headers (CWE-693)
**Verdict:** Valid (intentional tradeoff)

- Embed view clears XFO and sets `frame-ancestors *`.
- This enables embedding broadly and increases clickjacking exposure.

Evidence:
- `src/zopyx/surveyjs/browser/views.py:2011`
- `src/zopyx/surveyjs/browser/views.py:2014`

## Additional Finding (not in original report)

### A1. Overly broad permissions on sensitive endpoints
**Severity:** High

- Several sensitive endpoints are exposed with `zope2.View` instead of stronger permissions:
  - `save-form-json`
  - `get-polls-json`
  - `get-polls-json2`
  - `download-form-json`
  - `download-polls-json`
  - `download-polls-csv`

Evidence:
- `src/zopyx/surveyjs/browser/configure.zcml:190`
- `src/zopyx/surveyjs/browser/configure.zcml:197`
- `src/zopyx/surveyjs/browser/configure.zcml:204`
- `src/zopyx/surveyjs/browser/configure.zcml:210`
- `src/zopyx/surveyjs/browser/configure.zcml:233`
- `src/zopyx/surveyjs/browser/configure.zcml:240`
- `src/zopyx/surveyjs/browser/configure.zcml:247`

## Priority Fix Order

1. Lock down endpoint permissions (`configure.zcml`) for submission/edit/export/data APIs.
2. Add URL validation/allowlisting for outbound `post_endpoint_url` (SSRF).
3. Enforce replay protection fail-closed when token cache is unavailable.
4. Remove exception details from client-facing API errors.
5. Add upload validation (size + MIME magic) for PDF ingestion paths.
6. Add rate limiting for `save_poll` / PDF import / costly endpoints.
