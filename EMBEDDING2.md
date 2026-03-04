# Direct DOM Embedding — Implementation & Security Audit

**Status:** Partial Implementation / Security Review Required
**Version:** 2.0
**Date:** 2026-03-04
**Classification:** Security-Critical Feature

---

## Table of Contents

1. [Current Implementation State](#current-implementation-state)
2. [Architecture (As Built)](#architecture-as-built)
3. [API Reference](#api-reference)
4. [Security Audit](#security-audit)
5. [Threat Model (Revised)](#threat-model-revised)
6. [Required Fixes Before Production](#required-fixes-before-production)
7. [Deployment Checklist](#deployment-checklist)

---

## Current Implementation State

### What Is Implemented

| Component | File | Status |
|-----------|------|--------|
| Token generation (`@@embed-token`) | `browser/embed_direct.py` | ✅ Implemented |
| Token validation (HMAC) | `browser/embed_security.py` | ✅ Implemented |
| Origin allowlist validation | `browser/embed_security.py` | ✅ Implemented |
| CORS handling for `@@embed-config` | `browser/embed_direct.py` | ✅ Implemented |
| CORS preflight for `@@save-poll` | `browser/views.py` | ✅ Implemented |
| Shadow DOM isolation | `browser/embed_direct.py` (generated JS) | ✅ Implemented |
| `survey-core.min.css` in Shadow DOM | `browser/embed_direct.py` | ✅ Implemented |
| Local SurveyJS loading (no CDN) | `browser/embed_direct.py` | ✅ Implemented |
| `@@embed-direct-demo` with token display | `browser/embed_direct.py` | ✅ Implemented |
| Global enable/disable flag | `browser/controlpanel.py` | ✅ Implemented |
| Per-survey origin allowlist | `content/survey.py` | ✅ Implemented |
| Diskcache token store | `browser/embed_security.py` | ✅ Implemented |
| **One-time token use (replay protection)** | `browser/embed_security.py` | ❌ **NOT enforced** |
| **MessageChannel secure communication** | — | ❌ Not implemented |
| **Rate limiting** | — | ❌ Not implemented |
| **Audit logging** | — | ❌ Not implemented (debug logs only) |
| **SRI for SurveyJS bundle** | `browser/embed_direct.py` | ❌ Not implemented |
| **CSP headers on embed endpoints** | — | ❌ Not implemented |

---

## Architecture (As Built)

### Request Flow

```
External page (http://localhost:8000/demo.html)
    │
    │  1. User calls @@embed-token (POST, requires Modify portal content)
    │     → Plone validates origin against allowlist
    │     → Returns signed JWT-style token (HMAC-SHA256)
    │
    │  2. Browser loads @@embed-loader script
    │     → Returns dynamically generated JavaScript
    │     → No-cache headers; CORS open to any origin
    │
    │  3. <surveyjs-embed> element connects
    │     → Shadow DOM created
    │     → survey-core.min.css loaded via <link> in shadow root
    │     → survey.core.min.js + survey-js-ui.min.js loaded
    │       from ++resource++zopyx.surveyjs/surveyjs/ (cross-origin <script>)
    │
    │  4. GET @@embed-config
    │     → Origin validated against allowlist
    │     → HMAC token validated (signature + expiry + origin binding)
    │     → Survey UID in token compared to context UID
    │     → Returns form JSON + session_id + csrf_token
    │
    │  5. POST @@save-poll
    │     → OPTIONS preflight handled (CORS headers returned for any origin)
    │     → Origin validated against allowlist
    │     → HMAC token validated
    │     → _require_trusted_access() SKIPPED
    │     → _require_auth_token() SKIPPED
    │     → Form data stored/mailed/posted per survey configuration
    └──────────────────────────────────────────────────────────────
```

### Token Structure

```
header.payload.signature

header  = base64url({"alg":"HS256","typ":"JWT"})
payload = base64url({
    "iss": "privacyforms.studio",
    "aud": "embed-client",
    "sub": "<survey_uid>",
    "origin": "https://example.com",
    "iat": <unix_timestamp>,
    "exp": <unix_timestamp>,
    "jti": "<random_16_bytes_urlsafe>",
    "nonce": "<random_16_bytes_urlsafe>"
})
signature = base64url(HMAC-SHA256(header + "." + payload, signing_key))
```

**Note:** This is a custom JWT-style implementation, not a standards-compliant JWT library.

### Key Files

| File | Purpose |
|------|---------|
| `browser/embed_direct.py` | All embed views + dynamically generated JS |
| `browser/embed_security.py` | Token generation/validation, CORS helpers, origin validation |
| `browser/views.py` | `save_poll()` with embed submission handling |
| `content/survey.py` | Schema fields: `embedding_mode`, `embed_direct_origins`, `embed_direct_token_ttl` |
| `browser/controlpanel.py` | `embed_direct_global_enabled`, signing key, max origins |
| `embedding/demo.html` | Standalone test page (not part of Plone) |

---

## API Reference

### `POST /{survey-path}/@@embed-token`

**Permission:** `cmf.ModifyPortalContent`

**Request body:**
```json
{"origin": "https://example.com", "ttl_seconds": 300}
```

**Response:**
```json
{
  "token": "<header.payload.signature>",
  "expires_at": "2026-03-04T12:00:00+00:00",
  "origin": "https://example.com",
  "survey_uid": "<uid>",
  "embed_url": "https://plone.example.com/path/to/survey/@@embed-loader"
}
```

**Validation chain:** global enabled → `embedding_mode == "direct"` → origin in allowlist → token generated and stored in diskcache.

---

### `GET /{survey-path}/@@embed-config`

**Permission:** `zope2.View`

**Required headers:**
```
Origin: https://example.com
X-Embed-Token: <token>
```

**Response:**
```json
{
  "form_json": {...},
  "form_version": "<version_id>",
  "csrf_token": "<plone_auth_token>",
  "submit_endpoint": "https://plone.example.com/path/@@save-poll",
  "session_id": "<random_16_bytes>"
}
```

**Validation chain:** preflight → origin in allowlist → token signature + expiry + origin binding + survey UID match.

**CORS headers set on ALL responses** (including 403 errors) using the raw `Origin` header value.

---

### `GET /{survey-path}/@@embed-loader`

**Permission:** `zope2.View`

Returns dynamically generated JavaScript. Content includes hardcoded URLs to:
- `{portal_url}/++resource++zopyx.surveyjs/surveyjs/survey.core.min.js`
- `{portal_url}/++resource++zopyx.surveyjs/surveyjs/survey-js-ui.min.js`
- `{portal_url}/++resource++zopyx.surveyjs/surveyjs/survey-core.min.css`

**Headers:** `Cache-Control: no-cache, no-store, must-revalidate`

CORS: `Access-Control-Allow-Origin` set to any requesting `Origin`.

---

### `POST /{survey-path}/@@save-poll`

**Permission:** `zope2.View` (embed path bypasses Plone auth entirely)

For embed submissions (identified by `Origin` + `X-Embed-Token` headers):
- Runs origin validation and token validation
- **Skips** `_require_trusted_access()`
- **Skips** `_require_auth_token()`
- Proceeds directly to form action execution (store/mail/post)

---

## Security Audit

This section is a critical analysis of the current implementation. Issues are rated by severity.

---

### 🔴 CRITICAL

#### C1 — Replay Attacks: One-Time Token Use Not Enforced

`mark_token_used()` exists in `embed_security.py` and correctly implements single-use tracking via diskcache. **It is never called.**

```python
# embed_security.py — exists but unused:
def mark_token_used(jti):
    cache = _get_embed_cache()
    ...
    was_added = cache.add(cache_key, True, expire=3600)
    return was_added

# validate_embed_token() — no call to mark_token_used:
def validate_embed_token(token, expected_origin, secret=None):
    ...
    return payload  # ← mark_token_used(payload["jti"]) never called
```

**Impact:** A single embed token can be used to submit the same form an unlimited number of times during its TTL window. An attacker who intercepts or copies a token (e.g., from browser DevTools, network traffic, logs, or the demo page) can flood the survey with fake submissions. With the default 300-second TTL, thousands of submissions are possible per token.

**Fix:** Call `mark_token_used(payload["jti"])` inside `validate_embed_token()` or in `EmbedConfigView` after successful validation, and reject tokens where `mark_token_used()` returns False.

---

#### C2 — CORS Preflight Accepts Any Origin

`handle_cors_preflight()` responds with CORS success headers for **any** origin, even origins not in the allowlist:

```python
# embed_security.py
elif origin:
    # "Always set Allow-Origin... for preflight to avoid browser errors"
    response.setHeader("Access-Control-Allow-Origin", origin)
    response.setHeader("Access-Control-Allow-Credentials", "true")
    ...
response.setStatus(204)
return True
```

**Impact:** Any website in the world can successfully complete a CORS preflight to `@@embed-config` and `@@save-poll`. The actual request will then be rejected with 403, but:

1. The browser's CORS preflight cache stores the result — so browsers will proceed to make the actual request, incurring server-side processing for every reject.
2. It leaks that the endpoint exists and what headers it accepts.
3. The `Access-Control-Allow-Credentials: true` in the preflight from an unrecognized origin is strictly incorrect — it implies credentials may be sent from that origin.
4. This completely undermines the purpose of the allowlist at the preflight stage.

**Fix:** Return 204 with **no CORS headers** for unrecognized origins. Browsers will then block the actual request client-side without sending it.

---

#### C3 — Authentication Completely Bypassed for Embed Submissions

For any request to `@@save-poll` that includes both an `Origin` header and a valid `X-Embed-Token`, Plone's entire authentication stack is bypassed:

```python
# views.py
if origin and embed_token:
    # validate origin + token...
    pass  # ← falls through to form processing
else:
    if not self._require_trusted_access():  # ← SKIPPED for embeds
        return
    if not self._require_auth_token(form_version_id or ""):  # ← SKIPPED
        return
```

This means the embed token is the **sole** authentication mechanism for form submissions. There is no session check, no Plone user authentication, no CSRF verification.

**Consequence:** Any entity that obtains a valid embed token can:
- Submit arbitrary form data to the survey
- Trigger all configured survey actions (store, mail, POST to endpoint)
- Do so without any Plone user account or session

The 5-minute token TTL is the only protection, and because tokens are reusable (C1), the effective attack window is the full 5 minutes.

**Partial mitigations present:** Origin binding, HMAC signature. These prevent forging tokens without the signing key.

**Missing mitigations:** Rate limiting, one-time use, CAPTCHA, honeypot fields.

---

#### C4 — Sensitive Data in Production Logs at WARNING Level

The entire implementation contains extensive debug logging at `WARNING` level that will appear in production log files:

```python
logger.warning("[EMBED DEBUG] Token validated successfully, payload: %s", payload)
# payload contains: jti, nonce, origin, iat, exp, sub
```

```python
logger.warning("[EMBED DEBUG] validate_origin called with: origin=%s, allowed_origins=%s", ...)
logger.warning("[EMBED DEBUG] Preflight: origin valid, setting full CORS headers")
```

**Impact:**
- Token `jti` values are logged, enabling correlation attacks if logs are leaked.
- Token payloads expose origin, survey UID, and expiry to anyone with log access.
- High-volume request logging at WARNING level will flood monitoring systems, masking real warnings.
- Log aggregation services (Splunk, ELK, etc.) receiving these logs represent a secondary exfiltration vector.

**Fix:** Remove all `[EMBED DEBUG]` log lines entirely before production deployment. Real audit events should use `logger.info()` with structured, minimal fields — not `logger.warning()` with full object dumps.

---

### 🟠 HIGH

#### H1 — Signing Key Falls Back to General Auth Secret

```python
# embed_security.py
def _get_signing_key(settings=None):
    secret = getattr(settings, "embed_direct_signing_key", "") or ""
    if secret:
        return secret.strip()
    # Fallback to authenticity token secret
    secret = getattr(settings, "authenticity_token_secret", "") or ""
    return secret.strip() or None
```

**Impact:** If `embed_direct_signing_key` is not configured (the default), embed tokens are signed with the same key used for general Plone session/auth tokens. A valid Plone authenticity token could potentially be crafted as a valid embed token or vice versa. More importantly, rotating the embed signing key after a compromise requires rotating the general auth secret, which invalidates all existing Plone sessions.

**Fix:** Require `embed_direct_signing_key` to be explicitly set. Raise a clear error (not fall back silently) if it is absent.

---

#### H2 — No Rate Limiting on Any Embed Endpoint

The design document specifies:
- Token generation: 10/minute per user
- Config requests: 100/minute per IP
- Submissions: existing rate limits

None of this is implemented. All three endpoints are unbounded:

- `@@embed-token`: can be called as fast as the server allows (HMAC generation is cheap)
- `@@embed-config`: no limit on token validation attempts
- `@@save-poll`: no limit on form submissions from a valid token

**Impact:** DoS via CPU exhaustion (HMAC verification on every request), storage exhaustion (spam submissions to mail/store actions), and noise in audit data.

---

#### H3 — Schema Validator Allows HTTP for Any Domain

`survey.py:validate_origin()` uses this regex:

```python
pattern = r"^(https?://)[a-zA-Z0-9][-a-zA-Z0-9.]*(:[0-9]+)?$"
```

This allows `http://any-domain.com` to be saved as an allowed origin. The runtime validator in `embed_security.py` rejects non-localhost HTTP origins, but an admin can still store `http://production-site.com` in the database without error. The mismatch between what can be stored and what is accepted at runtime is confusing and could lead an administrator to believe they have configured a working embedding when they have not.

**Fix:** Align the two validators. Either: reject HTTP for non-localhost in the schema validator, or display a warning in the edit form when HTTP non-localhost origins are entered.

---

#### H4 — XSS via `context.title` in Demo Page

`DirectEmbedDemoView._render_demo_page()` interpolates `self.context.title` directly into HTML without escaping:

```python
<title>Direct DOM Embedding Demo - {self.context.title}</title>
...
<span class="info-value">{self.context.title}</span>
...
survey_url = self.context.absolute_url()
# and survey_url interpolated into onclick attributes
```

A survey with a title containing `</title><script>alert(1)</script>` would execute JavaScript in the browser of any user visiting `@@embed-direct-demo`. This view requires `cmf.ModifyPortalContent`, which limits the attack surface, but stored XSS in admin interfaces is still a serious vulnerability.

**Fix:** Use `html.escape(self.context.title)` and `html.escape(survey_url)` for all values interpolated into HTML strings.

---

#### H5 — `@@embed-loader` Served to Any Origin Without Restriction

```python
# embed_direct.py — EmbedLoaderView
origin = self.request.get_header("Origin") or self.request.get("HTTP_ORIGIN")
if origin:
    response.setHeader("Access-Control-Allow-Origin", origin)
```

The loader JavaScript is served to any origin. This JavaScript contains:
- The portal URL structure
- Hardcoded paths to static resources
- The full embed client logic

Any website can load and execute this script. While not immediately exploitable (the token is still required), it:
- Exposes implementation details to adversaries
- Allows competitors/scrapers to inspect the embed mechanism
- If combined with a CSRF or social engineering attack, could be used to probe the server

---

#### H6 — SurveyJS Loaded Cross-Origin Without Integrity Check

```javascript
// Generated by EmbedLoaderView
loadScript('http://localhost:8082/demo/++resource++zopyx.surveyjs/surveyjs/survey.core.min.js')
```

The SurveyJS library is loaded as a `<script>` tag from a cross-origin Plone server without any SRI (`integrity=`) attribute. If the Plone server or its static file serving is compromised, malicious JavaScript can be served to all pages that embed surveys, with full access to the form data being entered by users.

**Fix:** Compute and embed the SRI hash of `survey.core.min.js` and `survey-js-ui.min.js` at build time and include `integrity=` attributes on the generated `<script>` tags.

---

#### H7 — Token Stored and Displayed in Clear Text

The token is:
1. Shown in full on the `@@embed-direct-demo` page in an HTML element
2. Embedded in the onclick handler of a button: `navigator.clipboard.writeText('{token}')`
3. Embedded in the integration code snippet shown on the page
4. Stored in diskcache on the server filesystem in plaintext

Any user with access to `@@embed-direct-demo` (requires `cmf.ModifyPortalContent`) can see and copy the token. The token displayed on this page is the same token that grants write access to the form. Browser history, screenshot tools, screen recordings, and shoulder surfing all represent exposure vectors.

---

### 🟡 MEDIUM

#### M1 — Custom JWT Implementation Instead of Standard Library

The token implementation (`build_embed_token`, `validate_embed_token`) is a hand-rolled JWT-style system:

```python
def build_embed_token(payload, secret):
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(...).rstrip("=")
    ...
    signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
```

Issues with this approach:
- The token claims to be `{"alg":"HS256","typ":"JWT"}` but is not a valid JWT (non-standard padding stripping).
- No standard JWT library validation (audience, issuer, not-before).
- `hmac.new()` is deprecated in Python 3 in favor of `hmac.HMAC()`.
- The `aud` claim (`"embed-client"`) is never verified during validation.
- The `iss` claim (`"privacyforms.studio"`) is never verified during validation.

A third-party library such as `PyJWT` would handle all of this correctly and be audited by the security community.

---

#### M2 — Open Shadow DOM Allows Host Page JavaScript Access

```javascript
this.attachShadow({ mode: 'open' });
```

Open mode Shadow DOM means `element.shadowRoot` is accessible from the host page's JavaScript. Any script running on the host page (including third-party analytics, advertising, or a compromised dependency) can:
- Read all form field values as the user types
- Modify form content before submission
- Intercept the submission

The original design document describes Shadow DOM as providing "Style and DOM isolation" — open Shadow DOM provides style isolation, but **not** DOM isolation from the same page's JavaScript.

**Fix:** Consider `mode: 'closed'` for stronger isolation, accepting that browser developer tools will make this impractical to debug.

---

#### M3 — `embed_direct_signing_key` Readable by Plone Admins

The signing key is stored in Plone's registry (ZODB) as a `schema.Password` field. Any user with `cmf.ManagePortal` can read it via `@@registry` or by direct ZODB inspection. In a multi-tenant or managed Plone hosting environment, this is a significant concern.

---

#### M4 — `diskcache` Path is Relative and Non-Configurable

```python
def _get_embed_cache():
    return diskcache.Cache("var/embed_token_cache.db")
```

The path `var/embed_token_cache.db` resolves relative to the Plone process working directory, which may vary by deployment method. In multi-worker setups (multiple Waitress workers), each worker opens its own cache handle. `diskcache` handles concurrent access, but the path should be absolute and configurable via registry settings.

---

#### M5 — CSRF Token Fetched but Effectively Meaningless for Embeds

`@@embed-config` returns a Plone CSRF token (`_authenticator`). The embed client submits it in the `@@save-poll` POST body. However, Plone's CSRF validation (`plone.protect`) validates tokens against the current session. Cross-origin embedded requests may not have a Plone session (depending on `SameSite` cookie policy). The actual effect is:

- If a Plone session exists: CSRF token validates, but embed validation also passed (redundant)
- If no Plone session: CSRF token validation would fail — **but `_require_auth_token()` is bypassed entirely for embeds**, so it doesn't matter

The CSRF token round-trip adds complexity and latency with no actual security benefit for cross-origin embeds.

---

#### M6 — `@@embed-surveyjs-bundle` View Remains and Loads CDN

`EmbedSurveyJSBundleView` is registered in ZCML and publicly accessible, but is no longer used by `@@embed-loader`. It still contains code that dynamically loads SurveyJS from `https://unpkg.com/survey-core@1.9.132/` without an SRI hash (the placeholder was removed but not replaced with the real hash). It represents dead code that is a potential attack surface and causes confusion.

---

#### M7 — Token Generation Requires `cmf.ModifyPortalContent` But Demo Page Also Generates Tokens

`@@embed-token` correctly requires `cmf.ModifyPortalContent`. However, `@@embed-direct-demo` (which also requires `cmf.ModifyPortalContent`) internally generates tokens via `generate_embed_token()` without calling the token view. This bypasses any future rate limiting or additional validation that might be added to `@@embed-token`.

---

#### M8 — `Origin` Header Manually Set in Fetch Requests

```javascript
// embed_direct.py — generated JS
const response = await fetch(`${this.baseUrl}/@@embed-config`, {
    headers: {
        'X-Embed-Token': this.token,
        'Origin': this.origin,  // ← browser ignores this
    },
});
```

Setting `Origin` manually in a `fetch()` call has **no effect** — browsers always override this with the actual page origin and forbid JavaScript from setting it. This code is misleading: it creates the false impression that the origin is being explicitly declared by the client, when in reality the browser manages it. It should be removed to avoid confusing future maintainers.

---

### 🔵 LOW / INFORMATIONAL

#### L1 — Token Not Bound to Session

Tokens are bound to an origin but not to a browser session. Any visitor to the embedding page gets the same embed token (assuming the page operator embedded the token in the HTML). Token theft requires only viewing the page source.

#### L2 — No Visibility Into Active Tokens

There is no admin interface to list, inspect, or revoke active tokens. If a token is compromised, the only remediation is to wait for expiry or rotate the signing key (which invalidates all tokens, including legitimate ones).

#### L3 — `survey-core.min.css` Loaded via Cross-Origin `<link>` Without CORS

`<link rel="stylesheet">` elements load cross-origin CSS without CORS headers. While this is standard browser behavior, it means the CSS load is opaque — JavaScript cannot inspect the loaded styles via CSSOM. This is generally safe but worth documenting.

#### L4 — Token Expiry Not Reflected in Demo Page

The `@@embed-direct-demo` page shows `Token Expires: <timestamp>` but does not refresh or visually indicate when the token has expired. A user who keeps the demo page open past expiry will attempt to use an expired token without realizing it.

#### L5 — No Invariant Enforcing `embed_direct_origins` for `embedding_mode=direct`

The design document specifies an `@invariant` that requires at least one allowed origin when `embedding_mode == "direct"`. This invariant exists in the design document but is **absent** from the actual `ISurvey` schema in `content/survey.py`. A survey can be set to Direct DOM mode with an empty origins list, in which case all embed requests are silently rejected (origin not in empty allowlist).

---

## Threat Model (Revised)

| Threat | Severity | Design Mitigation | Implementation Status |
|--------|----------|-------------------|-----------------------|
| Replay attacks | **Critical** | One-time tokens via JTI | ❌ Not enforced |
| Unauthorized submission | Critical | Token + origin validation | ⚠️ Token reusable (C1) |
| Cross-origin data access | Critical | Allowlist CORS | ⚠️ Preflight bypasses allowlist (C2) |
| Form data exfiltration | High | Shadow DOM + token auth | ⚠️ Open Shadow DOM (M2) |
| Token forgery | High | HMAC-SHA256 signing | ✅ Mitigated (if key is strong) |
| Signing key exposure | High | Registry + access control | ⚠️ Readable by all admins (M3) |
| XSS via host page | High | Shadow DOM | ⚠️ Open mode allows JS access (M2) |
| Log-based token exfiltration | High | — | ❌ Tokens logged at WARNING (C4) |
| DoS via spam submissions | High | Rate limiting | ❌ Not implemented (H2) |
| Stored XSS in demo view | High | HTML escaping | ❌ Missing (H4) |
| SurveyJS supply chain attack | High | SRI + local hosting | ⚠️ Local hosting done, no SRI (H6) |
| HTTP origin in production | Medium | HTTPS enforcement | ⚠️ Schema allows HTTP for any host (H3) |

---

## Required Fixes Before Production

The following must be resolved before this feature is enabled in any production environment.

### P0 — Must Fix (Blocks Production)

1. **Remove all `[EMBED DEBUG]` log statements** — these log tokens and internal state at WARNING level in production.

2. **Enforce one-time token use** — call `mark_token_used()` in `validate_embed_token()` and reject tokens where it returns False.

3. **Fix CORS preflight** — do not return CORS headers for origins not in the allowlist. Return 204 with no CORS headers (browser blocks the actual request client-side).

4. **Fix XSS in demo page** — escape `self.context.title`, `survey_url`, `origin`, and `expires_at` with `html.escape()`.

5. **Require `embed_direct_signing_key` to be set** — do not silently fall back to `authenticity_token_secret`. Raise `EmbedSecurityError` with a clear message.

### P1 — Must Fix (Before Beta)

6. **Implement rate limiting** on `@@embed-token`, `@@embed-config`, and embed path of `@@save-poll`.

7. **Replace custom JWT with PyJWT** — use a standard, audited library. Verify `aud` and `iss` claims.

8. **Remove `Origin` header from JS fetch calls** — it does nothing and misleads maintainers.

9. **Add SRI hashes for SurveyJS static files** — compute at build time and embed in `loadSurveyJS()`.

10. **Delete or disable `@@embed-surveyjs-bundle`** — it is unused dead code with CDN loading.

11. **Add schema invariant** requiring at least one allowed origin when `embedding_mode == "direct"`.

### P2 — Should Fix (Before GA)

12. **Make diskcache path absolute and configurable** via registry settings.

13. **Add token revocation UI** — list active tokens by JTI, allow forced revocation.

14. **Add structured audit log** (separate from debug log) for: token generation, validation success/failure, submission accepted/rejected.

15. **Align schema and runtime origin validators** — prevent HTTP non-localhost origins from being stored.

16. **Consider `mode: 'closed'` Shadow DOM** — document the tradeoff explicitly.

---

## Deployment Checklist

Before enabling Direct DOM Embedding:

- [ ] All P0 and P1 fixes from above are applied
- [ ] `embed_direct_global_enabled` is `False` by default; enabled explicitly per environment
- [ ] `embed_direct_signing_key` is set to a cryptographically random 32+ byte value (NOT the same as `authenticity_token_secret`)
- [ ] HTTPS is enforced at the reverse proxy for the Plone server
- [ ] No HTTP origins are in any survey's `embed_direct_origins` list in production
- [ ] Token TTL is reviewed per use case (shorter = better for security)
- [ ] Plone log level is reviewed; WARNING-level logs do not contain sensitive data
- [ ] `diskcache` path is on an encrypted volume and backed up appropriately
- [ ] Rate limiting is configured at the reverse proxy level as a backstop
- [ ] `@@embed-direct-demo` is disabled or access-restricted in production (it generates and displays tokens)
- [ ] Security team has reviewed the open Shadow DOM decision for the deployment's threat model
