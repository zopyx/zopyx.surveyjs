# Direct DOM Embedding Concept for zopyx.surveyjs

**Status:** Design Document  
**Version:** 1.0  
**Date:** 2026-03-04  
**Classification:** Security-Critical Feature

---

## Executive Summary

This document describes a new **Direct DOM Embedding** mode for `zopyx.surveyjs` that enables seamless integration of forms directly into the DOM of external websites, as an alternative to the existing iframe-based approach. This mode trades the isolation benefits of iframes for deeper integration capabilities while implementing multiple layers of security controls to mitigate the associated risks.

**Key Design Principles:**
1. **Security First**: Defense in depth with multiple independent security layers
2. **Opt-in Only**: Requires explicit enablement per survey with strict validation
3. **Origin Control**: Cryptographic origin validation with allowlist enforcement
4. **Isolation via Shadow DOM**: Style and DOM isolation even without iframes
5. **Auditability**: Complete logging of all embedding activities

---

## Table of Contents

1. [Threat Model](#threat-model)
2. [Security Architecture](#security-architecture)
3. [Technical Implementation](#technical-implementation)
4. [API Specification](#api-specification)
5. [Code Changes Required](#code-changes-required)
6. [Implementation Plan](#implementation-plan)
7. [Testing Strategy](#testing-strategy)
8. [Deployment Considerations](#deployment-considerations)

---

## Threat Model

### Attack Vectors Addressed

| Threat | Severity | Mitigation |
|--------|----------|------------|
| **Clickjacking** | Critical | Shadow DOM encapsulation + CSP frame-ancestors + X-Frame-Options |
| **XSS via Malicious Host** | Critical | Strict origin validation, CORS, token-based authentication |
| **Data Exfiltration** | High | CORS preflight validation, signed payloads, origin allowlist |
| **CSRF** | High | CSRF tokens + origin validation + SameSite cookies |
| **DOM Pollution** | Medium | Shadow DOM isolation, sanitized CSS injection |
| **Replay Attacks** | Medium | Short-lived tokens, nonce validation, request signing |
| **Host Site Compromise** | High | Isolated execution context, strict CSP, no eval() |

### Trust Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                     UNTRUSTED ZONE                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  Host Site   │    │  Attacker    │    │   Malicious  │      │
│  │   (Client)   │    │   Scripts    │    │    Styles    │      │
│  └──────┬───────┘    └──────────────┘    └──────────────┘      │
│         │                                                        │
│         │  1. Script injection with origin claim                  │
│         ▼                                                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              TRUST BOUNDARY: Origin Validation               ││
│  │         (CORS + Cryptographic Origin Verification)           ││
│  └─────────────────────────────────────────────────────────────┘│
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    TRUSTED ZONE (Controlled)                 ││
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  ││
│  │  │  Shadow DOM  │    │   Sandboxed  │    │   Form JS    │  ││
│  │  │   Container  │◄───│   Execution  │◄───│   Runtime    │  ││
│  │  │              │    │   Context    │    │              │  ││
│  │  └──────────────┘    └──────────────┘    └──────────────┘  ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## Security Architecture

### Layer 1: Origin Authentication & CORS

**Problem:** The host site claims to be `trusted-domain.com` but could be an attacker.

**Solution:**
1. **Pre-registered Origin Allowlist**: Survey administrators must explicitly register allowed origins
2. **Cryptographic Origin Binding**: Each embedded form instance is bound to a specific origin via HMAC
3. **CORS with Credentials**: Strict CORS policy that validates against the allowlist
4. **Origin Header Verification**: Server-side validation of `Origin` header against registered values

```python
# Origin validation pseudocode
def validate_origin(request, survey):
    origin = request.get_header('Origin') or request.get_header('Referer')
    allowed_origins = survey.embed_direct_origins  # List of registered origins
    
    if not origin:
        return False, "Origin header required"
    
    parsed = urlparse(origin)
    if parsed.scheme not in ('https',):
        return False, "HTTPS required"
    
    origin_host = f"{parsed.scheme}://{parsed.netloc}"
    if origin_host not in allowed_origins:
        return False, "Origin not in allowlist"
    
    return True, origin_host
```

### Layer 2: Token-Based Authentication

**Problem:** Even with origin validation, we need to authenticate each embedding request.

**Solution:**
1. **Embedding Token**: Short-lived JWT-style tokens issued per embedding session
2. **Token Binding**: Tokens are bound to the registered origin (cannot be reused on different origins)
3. **One-Time Use**: Tokens are single-use for form initialization (replay protection)
4. **Time-Bounded**: Tokens expire after a short window (e.g., 5 minutes)

```python
# Token structure
token_payload = {
    "iss": "privacyforms.studio",
    "aud": "embed-client",
    "sub": survey_uid,
    "origin": "https://trusted-site.com",  # Bound to specific origin
    "exp": datetime.utcnow() + timedelta(minutes=5),
    "nonce": secrets.token_urlsafe(16),
    "jti": uuid.uuid4().hex,  # Unique token ID
}
```

### Layer 3: Shadow DOM Isolation

**Problem:** Host site CSS/JavaScript can interfere with the form.

**Solution:**
1. **Open Shadow DOM**: Renders form inside shadow root for style isolation
2. **CSS Reset Injection**: Injected CSS reset that cannot be overridden by host
3. **Event Boundary**: Form events are encapsulated within shadow boundary
4. **No External Dependencies**: Bundled, minified JavaScript with no external CDN deps

```javascript
// Shadow DOM encapsulation
class SurveyJSEmbed extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    
    // Inject isolated styles
    const style = document.createElement('style');
    style.textContent = SURVEY_CSS_BUNDLE;  // Bundled CSS, no external refs
    this.shadowRoot.appendChild(style);
    
    // Create isolated container
    this.container = document.createElement('div');
    this.container.className = 'surveyjs-embed-container';
    this.shadowRoot.appendChild(this.container);
  }
}
customElements.define('surveyjs-embed', SurveyJSEmbed);
```

### Layer 4: Communication Security

**Problem:** Need to communicate between host and form securely.

**Solution:**
1. **No Direct DOM Access**: Host cannot access form internals via DOM queries
2. **MessageChannel API**: Dedicated, unguessable communication channel
3. **Message Authentication**: All messages are signed with HMAC
4. **Origin Verification**: Each message verified against the registered origin

```javascript
// Secure communication via MessageChannel
const channel = new MessageChannel();

// Port is transferred to the embedded form
formElement.contentWindow.postMessage({
  type: 'INIT_CHANNEL',
  token: embedToken,
  port: channel.port2
}, origin, [channel.port2]);

// All subsequent communication through the dedicated port
channel.port1.onmessage = (event) => {
  // Verify message signature
  if (!verifyHMAC(event.data, sharedSecret)) {
    return;
  }
  // Process message...
};
```

### Layer 5: CSP and Security Headers

**Headers for embed endpoint:**
```http
Content-Security-Policy: 
  default-src 'none';
  script-src 'self' 'nonce-{random}';
  style-src 'self' 'unsafe-inline';  /* Required for dynamic theming */
  connect-src 'self' {api_origin};
  frame-ancestors {allowed_origin};  /* Specific origin, not wildcard */
  base-uri 'none';
  form-action 'none';
X-Content-Type-Options: nosniff
X-Frame-Options: DENY  /* Deny framing, we're in shadow DOM not iframe */
Referrer-Policy: strict-origin-when-cross-origin
```

---

## Technical Implementation

### Component Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                         External Website                            │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     Host Page HTML                            │  │
│  │  <script src="https://plone-site.com/embed-loader.js"></script>│  │
│  │  <surveyjs-embed survey="uid" token="jwt"></surveyjs-embed>   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼────────────────────────────────────┐│
│  │                 Shadow DOM (Isolated Context)                   ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ ││
│  │  │ Form Renderer│  │  Event Bus  │  │  Secure API Client      │ ││
│  │  │  (SurveyJS) │  │  (Pub/Sub)  │  │  (Token + Sig)          │ ││
│  │  └─────────────┘  └─────────────┘  └─────────────────────────┘ ││
│  └────────────────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼ HTTPS + CORS
┌────────────────────────────────────────────────────────────────────┐
│                         Plone Backend                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │ Embed Token │  │  Origin     │  │   Form      │  │ Submission │ │
│  │  Service    │  │ Validator   │  │   Service   │  │  Handler   │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

### New Content Schema Fields

Add to `ISurvey` schema in `content/survey.py`:

```python
# New vocabulary for embedding modes
survey_embedding_vocabulary = SimpleVocabulary([
    SimpleTerm(value="none", title=_("None")),
    SimpleTerm(value="iframe", title=_("Iframe")),
    SimpleTerm(value="direct", title=_("Direct DOM (experimental)")),
])

# New fields in ISurvey interface
class ISurvey(model.Schema):
    # ... existing fields ...
    
    embedding_mode = schema.Choice(
        title=_("Embedding mode"),
        description=_(
            "Controls whether this survey may be embedded. "
            "Direct DOM embedding allows seamless integration but requires "
            "careful security configuration."
        ),
        vocabulary=survey_embedding_vocabulary,
        required=True,
        default="none",
    )
    
    # Direct DOM embedding specific fields
    embed_direct_origins = schema.List(
        title=_("Allowed origins for direct embedding"),
        description=_(
            "List of origins allowed to embed this survey via direct DOM. "
            "Format: https://example.com (no trailing slash). "
            "Required when embedding mode is 'Direct DOM'."
        ),
        value_type=schema.URI(
            title=_("Origin"),
            description=_("HTTPS origin")
        ),
        required=False,
        defaultFactory=list,
    )
    
    embed_direct_token_ttl = schema.Int(
        title=_("Embed token TTL (seconds)"),
        description=_("Lifetime of embedding tokens in seconds."),
        required=False,
        default=300,  # 5 minutes
        min=60,
        max=3600,
    )
    
    embed_direct_require_sri = schema.Bool(
        title=_("Require Subresource Integrity"),
        description=_(
            "When enabled, the embed script must include a valid "
            "integrity attribute matching the expected hash."
        ),
        required=False,
        default=True,
    )
```

### New Registry Settings

Add to `IFormsSettings` in `interfaces.py`:

```python
class IFormsSettings(IPloneLoggingSettings):
    # ... existing fields ...
    
    fieldset(
        "embed_direct",
        label="Direct DOM Embedding",
        fields=(
            "embed_direct_global_enabled",
            "embed_direct_signing_key",
            "embed_direct_default_origins",
            "embed_direct_max_origins",
        ),
    )
    
    embed_direct_global_enabled = schema.Bool(
        title="Enable Direct DOM Embedding globally",
        description="Master switch for the direct DOM embedding feature.",
        required=False,
        default=False,  # Opt-in at site level
    )
    
    embed_direct_signing_key = schema.Password(
        title="Embed Token Signing Key",
        description="HMAC key for signing embed tokens. Rotate regularly.",
        required=False,
        default="",
    )
    
    embed_direct_max_origins = schema.Int(
        title="Maximum origins per survey",
        description="Limit the number of allowed origins for security.",
        required=False,
        default=10,
        min=1,
        max=100,
    )
```

---

## API Specification

### 1. Token Generation Endpoint

**URL:** `POST /{survey-path}/@@embed-token`

**Permission:** `cmf.ModifyPortalContent` (only form owners can generate tokens)

**Request:**
```json
{
  "origin": "https://example.com",
  "ttl_seconds": 300
}
```

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_at": "2026-03-04T12:00:00Z",
  "origin": "https://example.com",
  "survey_uid": "abc123",
  "embed_url": "https://plone-site.com/embed-loader.js"
}
```

### 2. Form Configuration Endpoint

**URL:** `GET /{survey-path}/@@embed-config`

**Headers:**
```http
Origin: https://example.com
X-Embed-Token: eyJhbGciOiJIUzI1NiIs...
```

**Response (CORS-enabled):**
```json
{
  "form_json": { /* SurveyJS form definition */ },
  "form_version": "v1.2.3",
  "csrf_token": "...",
  "submit_endpoint": "https://plone-site.com/{survey-path}/@@save-poll",
  "session_id": "uuid-for-this-session"
}
```

### 3. Submission Endpoint (Enhanced)

The existing `@@save-poll` endpoint needs enhancement:

**Additional Headers:**
```http
Origin: https://example.com
X-Embed-Token: eyJhbGciOiJIUzI1NiIs...
X-Session-ID: uuid-for-this-session
```

**Validation:**
1. Verify `Origin` header matches token-bound origin
2. Verify token signature and expiration
3. Verify `session_id` is valid
4. Apply existing `save_poll` validations

### 4. Embed Loader Script

**URL:** `GET /embed-loader.js`

**Response:** Bundled JavaScript containing:
- Shadow DOM Web Component definition
- Secure API client
- MessageChannel setup
- SurveyJS runtime (bundled, no CDN)

**Security:**
- Served with `Content-Type: application/javascript; charset=utf-8`
- Subresource Integrity hash available via separate endpoint
- Minified and obfuscated

---

## Code Changes Required

### 1. Content Schema (`content/survey.py`)

```python
# Add new fields to ISurvey interface
# Lines to add after existing embedding_mode field:

from zope.schema import ValidationError
import re

class InvalidOriginError(ValidationError):
    __doc__ = "Invalid origin format. Use https://example.com (no path, no trailing slash)"


def validate_origin(value):
    """Validate origin format: https://example.com"""
    if not value:
        return True
    pattern = r'^https://[a-zA-Z0-9][-a-zA-Z0-9.]*(:[0-9]+)?$'
    if not re.match(pattern, value):
        raise InvalidOriginError()
    return True


class ISurvey(model.Schema):
    # ... existing fields ...
    
    # Updated embedding_mode vocabulary
    embedding_mode = schema.Choice(
        title=_("Embedding mode"),
        description=_(
            "Controls whether this survey may be embedded. "
            "Iframe is the recommended secure option. "
            "Direct DOM embedding allows seamless integration but "
            "requires careful origin configuration."
        ),
        vocabulary=survey_embedding_vocabulary,  # Updated with 'direct' option
        required=True,
        default="none",
    )
    
    # New fields for direct embedding
    embed_direct_origins = schema.List(
        title=_("Allowed origins for direct embedding"),
        description=_(
            "Origins allowed to embed this survey. Format: https://example.com "
            "Required for Direct DOM mode. Max 10 origins."
        ),
        value_type=schema.TextLine(
            title=_("Origin"),
            constraint=validate_origin,
        ),
        required=False,
        defaultFactory=list,
        max_length=10,
    )
    
    embed_direct_token_ttl = schema.Int(
        title=_("Embed token TTL (seconds)"),
        description=_("Lifetime of embedding tokens. 60-3600 seconds."),
        required=False,
        default=300,
        min=60,
        max=3600,
    )
    
    @invariant
    def validate_embed_direct_config(data):
        """Validate that direct embedding config is complete when enabled."""
        if data.embedding_mode == "direct":
            if not data.embed_direct_origins:
                raise InvalidValueError(
                    "At least one allowed origin is required for Direct DOM embedding"
                )
            # Check global setting
            # (will be checked in view code to avoid circular imports)
```

### 2. New Views (`browser/views.py`)

Add new view classes:

```python
class EmbedDirectTokenView(Views):
    """Generate embedding tokens for direct DOM embedding."""
    
    def __call__(self):
        """POST endpoint to generate embed tokens."""
        # Check permission
        if not self.can_manage_portal_content:
            json_error(self.request.response, 403, "permission_denied")
            return
        
        # Check if direct embedding is enabled globally
        if not self._embed_direct_global_enabled():
            json_error(self.request.response, 403, "feature_disabled")
            return
        
        # Check survey embedding mode
        if getattr(self.context, "embedding_mode", None) != "direct":
            json_error(self.request.response, 400, "direct_embedding_not_enabled")
            return
        
        # Parse request
        try:
            body = json.loads(self.request.get("BODY", "{}"))
        except json.JSONDecodeError:
            json_error(self.request.response, 400, "invalid_json")
            return
        
        origin = body.get("origin", "").strip()
        ttl = body.get("ttl_seconds", 300)
        
        # Validate origin against allowlist
        allowed_origins = getattr(self.context, "embed_direct_origins", []) or []
        if origin not in allowed_origins:
            json_error(self.request.response, 403, "origin_not_allowed")
            return
        
        # Generate token
        token, metadata = self._generate_embed_token(origin, ttl)
        
        json_response(self.request.response, {
            "token": token,
            "expires_at": metadata["expires_at"],
            "origin": origin,
            "survey_uid": self._form_id(),
            "embed_url": f"{self.context.absolute_url()}/@@embed-loader",
        })
    
    def _embed_direct_global_enabled(self):
        """Check if direct embedding is enabled globally."""
        settings = self._get_forms_settings()
        if not settings:
            return False
        return getattr(settings, "embed_direct_global_enabled", False)
    
    def _generate_embed_token(self, origin: str, ttl: int) -> tuple:
        """Generate cryptographically secure embed token."""
        settings = self._get_forms_settings()
        secret = getattr(settings, "embed_direct_signing_key", "")
        
        # Fallback to authenticity token secret if embed secret not set
        if not secret:
            secret = getattr(settings, "authenticity_token_secret", "")
        
        issued_at = int(time.time())
        expires_at = issued_at + min(max(ttl, 60), 3600)
        
        payload = {
            "iss": "privacyforms.studio",
            "aud": "embed-client",
            "sub": self._form_id(),
            "origin": origin,
            "iat": issued_at,
            "exp": expires_at,
            "jti": uuid.uuid4().hex,
            "nonce": secrets.token_urlsafe(16),
        }
        
        # Sign token
        token = build_embed_token(payload, secret)
        
        # Cache token metadata for validation
        self._cache_embed_token(payload)
        
        metadata = {
            "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        }
        
        return token, metadata


class EmbedConfigView(Views):
    """Serve form configuration to embedded clients with CORS."""
    
    def __call__(self):
        """Return form JSON with CORS headers for validated requests."""
        # Validate origin
        origin = self.request.get_header("Origin")
        is_valid, error_msg = self._validate_origin(origin)
        if not is_valid:
            json_error(self.request.response, 403, "invalid_origin", message=error_msg)
            return
        
        # Validate token
        token = self.request.get_header("X-Embed-Token")
        if not self._validate_embed_token(token, origin):
            json_error(self.request.response, 403, "invalid_token")
            return
        
        # Set CORS headers
        self.request.response.setHeader("Access-Control-Allow-Origin", origin)
        self.request.response.setHeader("Access-Control-Allow-Credentials", "true")
        self.request.response.setHeader("Vary", "Origin")
        
        # Get form data
        annos = IAnnotations(self.context)
        form_versions = forms_service.sorted_form_versions(annos)
        form_data = form_versions[-1]["form_json"] if form_versions else {}
        form_version_id = form_versions[-1]["id"] if form_versions else ""
        
        # Generate session ID
        session_id = secrets.token_urlsafe(16)
        self._store_session(session_id, origin)
        
        json_response(self.request.response, {
            "form_json": form_data,
            "form_version": form_version_id,
            "csrf_token": self._generate_csrf_token(),
            "submit_endpoint": f"{self.context.absolute_url()}/@@save-poll",
            "session_id": session_id,
        })
    
    def _validate_origin(self, origin: str) -> tuple:
        """Validate origin against allowlist."""
        if not origin:
            return False, "Origin header required"
        
        # Parse and normalize
        try:
            parsed = urlparse(origin)
        except Exception:
            return False, "Invalid origin format"
        
        # Require HTTPS
        if parsed.scheme != "https":
            return False, "HTTPS required"
        
        # No path, query, or fragment allowed
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            return False, "Origin must not contain path or query"
        
        origin_host = f"{parsed.scheme}://{parsed.netloc}"
        
        # Check against allowlist
        allowed = getattr(self.context, "embed_direct_origins", []) or []
        if origin_host not in allowed:
            return False, "Origin not in allowlist"
        
        return True, origin_host


class EmbedLoaderView(Views):
    """Serve the embed loader JavaScript bundle."""
    
    def __call__(self):
        """Return the JavaScript bundle for direct DOM embedding."""
        self.request.response.setHeader("Content-Type", "application/javascript; charset=utf-8")
        self.request.response.setHeader("X-Content-Type-Options", "nosniff")
        
        # Return bundled JavaScript
        # In production, this would be a pre-built bundle
        return self._get_embed_js_bundle()
```

### 3. Enhanced Save Poll (`browser/views.py`)

Modify existing `save_poll` method to handle embed submissions:

```python
def save_poll(self):
    """Enhanced to support direct DOM embed submissions."""
    
    # Check if this is an embed submission
    origin = self.request.get_header("Origin")
    embed_token = self.request.get_header("X-Embed-Token")
    
    if origin and embed_token:
        # This is an embed submission - validate it
        if not self._validate_embed_submission(origin, embed_token):
            json_error(self.request.response, 403, "embed_validation_failed")
            return
        
        # Set CORS headers for response
        self.request.response.setHeader("Access-Control-Allow-Origin", origin)
        self.request.response.setHeader("Access-Control-Allow-Credentials", "true")
    else:
        # Regular submission - check if embedding mode allows it
        embed_mode = getattr(self.context, "embedding_mode", "none")
        if embed_mode == "direct":
            # Direct embed mode requires origin/token
            json_error(self.request.response, 403, "embed_token_required")
            return
    
    # ... continue with existing save_poll logic ...


def _validate_embed_submission(self, origin: str, token: str) -> bool:
    """Validate an embed submission."""
    # Validate origin
    is_valid, _ = self._validate_origin(origin)
    if not is_valid:
        return False
    
    # Validate token
    if not self._validate_embed_token(token, origin):
        return False
    
    return True
```

### 4. JavaScript Embed Client

New file: `browser/static/embed-client.js`

```javascript
/**
 * Direct DOM Embedding Client for zopyx.surveyjs
 * Security-first implementation with Shadow DOM isolation
 */

(function() {
  'use strict';

  // Bundled CSS (injected into Shadow DOM)
  const EMBED_CSS = `
    :host {
      display: block;
      width: 100%;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    .surveyjs-embed-container {
      width: 100%;
      min-height: 400px;
    }
    /* Reset styles that can't be inherited */
    .surveyjs-embed-container * {
      box-sizing: border-box;
    }
    /* SurveyJS theme styles */
    ${SURVEYJS_THEME_CSS}
  `;

  /**
   * Secure API client for communicating with Plone backend
   */
  class SecureAPIClient {
    constructor(baseUrl, token, origin) {
      this.baseUrl = baseUrl;
      this.token = token;
      this.origin = origin;
    }

    /**
     * Fetch form configuration from server
     */
    async getFormConfig() {
      const response = await fetch(`${this.baseUrl}/@@embed-config`, {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
          'X-Embed-Token': this.token,
          'Origin': this.origin,
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to load form: ${response.status}`);
      }

      return response.json();
    }

    /**
     * Submit form data to server
     */
    async submitForm(data, sessionId, csrfToken) {
      const formData = new FormData();
      formData.append('pollResult', JSON.stringify(data));
      formData.append('_authenticator', csrfToken);

      const response = await fetch(`${this.baseUrl}/@@save-poll`, {
        method: 'POST',
        credentials: 'include',
        body: formData,
        headers: {
          'X-Embed-Token': this.token,
          'X-Session-ID': sessionId,
          'Origin': this.origin,
        },
      });

      if (!response.ok) {
        throw new Error(`Submission failed: ${response.status}`);
      }

      return response.json();
    }
  }

  /**
   * Web Component for embedding SurveyJS forms
   */
  class SurveyJSEmbed extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      
      // Inject styles
      const style = document.createElement('style');
      style.textContent = EMBED_CSS;
      this.shadowRoot.appendChild(style);
      
      // Create container
      this.container = document.createElement('div');
      this.container.className = 'surveyjs-embed-container';
      this.shadowRoot.appendChild(this.container);
      
      // State
      this.survey = null;
      this.config = null;
      this.api = null;
    }

    static get observedAttributes() {
      return ['survey-url', 'token'];
    }

    async connectedCallback() {
      const baseUrl = this.getAttribute('survey-url');
      const token = this.getAttribute('token');
      
      if (!baseUrl || !token) {
        this.showError('Missing required attributes: survey-url, token');
        return;
      }

      try {
        // Initialize API client
        this.api = new SecureAPIClient(baseUrl, token, window.location.origin);
        
        // Load form configuration
        this.config = await this.api.getFormConfig();
        
        // Initialize SurveyJS
        await this.initializeSurvey(this.config.form_json);
      } catch (error) {
        console.error('Survey embed error:', error);
        this.showError('Failed to load survey. Please try again.');
      }
    }

    async initializeSurvey(formJson) {
      // Ensure SurveyJS is loaded
      if (typeof Survey === 'undefined') {
        await this.loadSurveyJS();
      }

      // Create survey model
      this.survey = new Survey.Model(formJson);
      
      // Apply theme
      this.survey.applyTheme(SurveyTheme.LayeredDarkPanelless);
      
      // Handle completion
      this.survey.onComplete.add(async (sender) => {
        try {
          await this.api.submitForm(
            sender.data,
            this.config.session_id,
            this.config.csrf_token
          );
          this.showSuccess('Thank you for your submission!');
        } catch (error) {
          console.error('Submission error:', error);
          this.showError('Submission failed. Please try again.');
        }
      });

      // Render
      this.survey.render(this.container);
    }

    loadSurveyJS() {
      return new Promise((resolve, reject) => {
        // Check if already loading
        if (window.__surveyJSLoading) {
          const checkInterval = setInterval(() => {
            if (typeof Survey !== 'undefined') {
              clearInterval(checkInterval);
              resolve();
            }
          }, 100);
          return;
        }

        window.__surveyJSLoading = true;

        // Load from same origin to avoid SRI issues with CDNs
        const script = document.createElement('script');
        script.src = `${this.getAttribute('survey-url')}/@@embed-surveyjs-bundle`;
        script.onload = () => {
          window.__surveyJSLoading = false;
          resolve();
        };
        script.onerror = () => {
          window.__surveyJSLoading = false;
          reject(new Error('Failed to load SurveyJS'));
        };
        document.head.appendChild(script);
      });
    }

    showError(message) {
      this.container.innerHTML = `
        <div class="surveyjs-error" style="color: #d32f2f; padding: 20px; text-align: center;">
          <p>${this.escapeHtml(message)}</p>
        </div>
      `;
    }

    showSuccess(message) {
      this.container.innerHTML = `
        <div class="surveyjs-success" style="color: #388e3c; padding: 20px; text-align: center;">
          <p>${this.escapeHtml(message)}</p>
        </div>
      `;
    }

    escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }
  }

  // Register custom element
  customElements.define('surveyjs-embed', SurveyJSEmbed);
})();
```

### 5. ZCML Configuration (`browser/configure.zcml`)

Add new view registrations:

```xml
<!-- Direct DOM Embedding Views -->
<browser:page
  name="embed-token"
  for="zopyx.surveyjs.content.survey.ISurvey"
  permission="cmf.ModifyPortalContent"
  class=".views.EmbedDirectTokenView"
/>

<browser:page
  name="embed-config"
  for="zopyx.surveyjs.content.survey.ISurvey"
  permission="zope2.View"
  class=".views.EmbedConfigView"
/>

<browser:page
  name="embed-loader"
  for="zopyx.surveyjs.content.survey.ISurvey"
  permission="zope2.View"
  class=".views.EmbedLoaderView"
/>

<browser:page
  name="embed-surveyjs-bundle"
  for="*"
  permission="zope2.View"
  class=".views.EmbedSurveyJSBundleView"
/>
```

---

## Implementation Plan

### Phase 1: Foundation (Week 1-2)

1. **Schema Changes**
   - [ ] Add `embed_direct_*` fields to `ISurvey`
   - [ ] Add registry settings to `IFormsSettings`
   - [ ] Create migration for existing surveys (default to disabled)
   - [ ] Update vocabulary for `embedding_mode`

2. **Core Security Module**
   - [ ] Create `browser/embed_security.py` with token functions
   - [ ] Implement `validate_embed_token()` with HMAC verification
   - [ ] Implement origin validation utilities
   - [ ] Add diskcache integration for token storage

3. **Tests**
   - [ ] Unit tests for token generation/validation
   - [ ] Origin validation tests
   - [ ] Schema validation tests

### Phase 2: Backend API (Week 3-4)

1. **View Implementations**
   - [ ] `EmbedDirectTokenView` (token generation)
   - [ ] `EmbedConfigView` (CORS form serving)
   - [ ] `EmbedLoaderView` (JS bundle serving)
   - [ ] Enhance `save_poll` for embed submissions

2. **CORS Middleware/Helpers**
   - [ ] CORS preflight handler
   - [ ] Origin header validation middleware
   - [ ] Security headers for embed endpoints

3. **Tests**
   - [ ] Integration tests for token endpoint
   - [ ] CORS validation tests
   - [ ] End-to-end embed flow tests

### Phase 3: Frontend Client (Week 5-6)

1. **JavaScript Build Pipeline**
   - [ ] Set up bundler (Rollup/Webpack) for embed client
   - [ ] Bundle SurveyJS dependencies
   - [ ] CSS injection system
   - [ ] Minification and SRI hash generation

2. **Web Component**
   - [ ] Implement `surveyjs-embed` custom element
   - [ ] Shadow DOM isolation
   - [ ] Secure API client
   - [ ] Error handling and loading states

3. **Tests**
   - [ ] Unit tests for API client
   - [ ] Web component tests
   - [ ] Browser compatibility tests

### Phase 4: Integration & Documentation (Week 7-8)

1. **Admin UI**
   - [ ] Token generation UI in survey management
   - [ ] Origin management interface
   - [ ] Embed code generator with copy button

2. **Documentation**
   - [ ] Administrator guide for direct embedding
   - [ ] Developer integration guide
   - [ ] Security best practices
   - [ ] Migration guide from iframe

3. **Final Testing**
   - [ ] Security audit
   - [ ] Penetration testing
   - [ ] Performance testing
   - [ ] Accessibility audit

---

## Testing Strategy

### Security Testing

```python
# Example security test patterns

class TestEmbedDirectSecurity(unittest.TestCase):
    """Security-focused tests for direct DOM embedding."""
    
    def test_token_rejected_for_wrong_origin(self):
        """Token generated for origin A should not work on origin B."""
        token = generate_token(origin="https://site-a.com")
        
        with self.assertRaises(ValidationError):
            validate_token(token, origin="https://site-b.com")
    
    def test_expired_token_rejected(self):
        """Expired tokens must be rejected."""
        token = generate_token(origin="https://site.com", ttl=-1)
        
        with self.assertRaises(ValidationError):
            validate_token(token, origin="https://site.com")
    
    def test_origin_must_match_exactly(self):
        """Subdomain mismatch should reject."""
        token = generate_token(origin="https://www.site.com")
        
        with self.assertRaises(ValidationError):
            validate_token(token, origin="https://site.com")
    
    def test_http_origin_rejected(self):
        """Non-HTTPS origins must be rejected."""
        with self.assertRaises(ValidationError):
            generate_token(origin="http://insecure.com")
    
    def test_cors_headers_set_correctly(self):
        """CORS headers must reflect allowed origin, not wildcard."""
        response = self.get_embed_config(origin="https://allowed.com")
        
        self.assertEqual(
            response.headers['Access-Control-Allow-Origin'],
            'https://allowed.com'
        )
        self.assertNotEqual(
            response.headers['Access-Control-Allow-Origin'],
            '*'
        )
```

### Integration Testing

1. **End-to-End Flow:**
   - Generate token → Load config → Render form → Submit → Verify stored
   
2. **Error Scenarios:**
   - Invalid token, expired token, wrong origin, missing CORS headers
   
3. **Browser Compatibility:**
   - Shadow DOM support (Chrome, Firefox, Safari, Edge)
   - Custom Elements support
   - Fetch API with credentials

---

## Deployment Considerations

### Security Checklist

Before enabling Direct DOM Embedding in production:

- [ ] `embed_direct_signing_key` is set to a cryptographically random value (32+ bytes)
- [ ] HTTPS is enforced site-wide
- [ ] `embed_direct_global_enabled` is explicitly enabled (opt-in)
- [ ] Token cache is stored on encrypted volume
- [ ] Rate limiting is configured on embed endpoints
- [ ] Security headers are verified via scan
- [ ] CSP is tested and doesn't break functionality
- [ ] Audit logging is enabled for all embed activities

### Performance Considerations

1. **Bundle Size:**
   - SurveyJS bundle is ~500KB minified
   - Consider lazy loading for multiple forms
   - CDN caching vs. same-origin serving tradeoffs

2. **Token Cache:**
   - Use Redis for distributed deployments
   - Set appropriate TTL (5 minutes default)
   - Monitor cache hit rates

3. **Rate Limiting:**
   - Token generation: 10/minute per user
   - Config requests: 100/minute per IP
   - Submissions: existing rate limits apply

---

## Recommendations

### Immediate Actions

1. **Do NOT enable Direct DOM Embedding by default** - Keep as opt-in only
2. **Require HTTPS** - Never allow HTTP origins
3. **Limit origins** - Maximum 10 origins per survey
4. **Short token lifetime** - Default 5 minutes, max 1 hour
5. **Audit everything** - Log all token generations and validation failures

### Future Enhancements

1. **Web Workers:** Run form JavaScript in a Web Worker for additional isolation
2. **WASM Sandboxing:** Evaluate WASM-based JavaScript isolation
3. **Content Security Policy Report-Only:** Monitor violations before enforcement
4. **Automated Security Scanning:** Regular automated pen-testing of embed endpoints
5. **Federated Identity:** Support for SSO/SAML in embedded contexts

---

## Conclusion

Direct DOM Embedding provides significant integration benefits over iframe-based approaches but introduces substantial security complexity. This design implements defense in depth with multiple independent security layers:

1. **Origin Authentication** via cryptographic tokens
2. **CORS Enforcement** with specific origins (no wildcards)
3. **Shadow DOM Isolation** for style and DOM separation
4. **Token-Based Authorization** with binding to specific origins
5. **Secure Communication** via MessageChannel and HMAC-signed messages

The feature must remain **opt-in only** with strict validation requirements. Administrators must explicitly enable the feature both globally and per-survey, and must register allowed origins explicitly.

---

**Appendix: Security Header Examples**

```nginx
# Nginx configuration for embed endpoints
location /@@embed- {
    # CORS headers
    add_header 'Access-Control-Allow-Origin' $http_origin always;
    add_header 'Access-Control-Allow-Credentials' 'true' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'X-Embed-Token,X-Session-ID,Content-Type' always;
    
    # Security headers
    add_header 'X-Content-Type-Options' 'nosniff' always;
    add_header 'X-Frame-Options' 'DENY' always;
    add_header 'Content-Security-Policy' "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'" always;
    add_header 'Referrer-Policy' 'strict-origin-when-cross-origin' always;
    
    # Handle preflight
    if ($request_method = 'OPTIONS') {
        return 204;
    }
}
```
