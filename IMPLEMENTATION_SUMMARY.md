# Direct DOM Embedding Implementation Summary

This document summarizes the implementation of the Direct DOM Embedding feature for zopyx.surveyjs based on EMBEDDING2.md.

## What Was Implemented

### 1. Schema Changes

#### Survey Content Type (`src/zopyx/surveyjs/content/survey.py`)
- Added "direct" option to `survey_embedding_vocabulary`
- Added `embed_direct_origins` field: List of allowed HTTPS origins
- Added `embed_direct_token_ttl` field: Token lifetime (60-3600 seconds)
- Added origin validation function to ensure proper format

#### Registry Settings (`src/zopyx/surveyjs/interfaces.py`)
- Added "Direct DOM Embedding" fieldset to `IFormsSettings`
- Added `embed_direct_global_enabled`: Master switch (default: False)
- Added `embed_direct_signing_key`: HMAC secret for token signing
- Added `embed_direct_max_origins`: Limit per survey (default: 10)

### 2. Security Module (`src/zopyx/surveyjs/browser/embed_security.py`)

Core security utilities:

- `build_embed_token()`: Creates HMAC-signed JWT-style tokens
- `validate_embed_token()`: Validates token signature, expiration, and origin binding
- `validate_origin()`: Validates HTTPS origins against allowlist
- `generate_embed_token()`: Generates new tokens with metadata
- `is_embed_direct_globally_enabled()`: Checks registry setting
- `set_cors_headers()`: Sets secure CORS headers
- `handle_cors_preflight()`: Handles OPTIONS requests
- `mark_token_used()`: For optional one-time use enforcement

Security features:
- HMAC-SHA256 signatures
- Token binding to specific origins
- 5-minute default expiration (configurable)
- HTTPS-only origins
- Strict CORS (no wildcards)

### 3. Browser Views (`src/zopyx/surveyjs/browser/embed_direct.py`)

#### `EmbedDirectTokenView` (@@embed-token)
- POST endpoint for token generation
- Requires ModifyPortalContent permission
- Validates origin against survey's allowlist
- Returns token with expiration metadata

#### `EmbedConfigView` (@@embed-config)
- GET endpoint for form configuration
- Validates origin and token headers
- Returns SurveyJS form JSON + session info
- Handles CORS preflight

#### `EmbedLoaderView` (@@embed-loader)
- Serves JavaScript embed client
- Creates `<surveyjs-embed>` Web Component
- Includes Shadow DOM isolation CSS
- Loads SurveyJS library dynamically

#### `EmbedSurveyJSBundleView` (@@embed-surveyjs-bundle)
- Serves SurveyJS library bundle
- Currently a stub that loads from CDN
- In production, would serve self-hosted bundle

#### `DirectEmbedDemoView` (@@embed-direct-demo)
- Full demo page with live embedded form
- Configuration display
- Integration code examples
- Security features documentation

### 4. JavaScript Client (`src/zopyx/surveyjs/browser/static/embed-client.js`)

Web Component implementation:

```javascript
class SurveyJSEmbed extends HTMLElement {
  // Shadow DOM for style isolation
  // Secure API client for backend communication
  // Dynamic SurveyJS loading
  // Error and loading states
}
```

Features:
- Shadow DOM encapsulation
- Style isolation from host page
- Secure token-based API calls
- Automatic SurveyJS loading
- Error handling and user feedback

### 5. Enhanced Save Poll (`src/zopyx/surveyjs/browser/views.py`)

Modified `save_poll()` to handle direct embed submissions:
- Detects embed tokens via X-Embed-Token header
- Validates origin and token
- Sets CORS headers for cross-origin responses
- Bypasses trusted access check for embed submissions

### 6. Configuration (`src/zopyx/surveyjs/browser/configure.zcml`)

Registered all new views:
- `@@embed-token`
- `@@embed-config`
- `@@embed-loader`
- `@@embed-surveyjs-bundle`
- `@@embed-direct-demo`

### 7. Demo Files

#### `embedding/demo.html`
Standalone demo page for testing:
- Input fields for Survey URL and Token
- Dynamic script loading
- Live form preview

#### `embedding/README.md`
Documentation for the implementation:
- Architecture overview
- API reference
- Setup instructions
- Security considerations
- Troubleshooting guide

## How to Use

### Step 1: Enable Global Setting

Go to Site Setup -> Forms Settings -> Direct DOM Embedding:
- Check "Enable Direct DOM Embedding globally"
- Set a signing key (or it will fall back to authenticity token secret)

### Step 2: Configure Survey

Edit a survey:
- Set Embedding mode to "Direct DOM (experimental)"
- Add allowed origins (e.g., `https://example.com`)
- Set token TTL (default: 300 seconds)

### Step 3: Access Demo

Navigate to:
```
https://your-plone-site.com/path/to/survey/@@embed-direct-demo
```

This shows:
- Live embedded form
- Token and configuration details
- Integration code examples
- Security feature list

### Step 4: Embed on External Site

```html
<script src="https://plone-site.com/path/to/survey/@@embed-loader"></script>
<surveyjs-embed 
  survey-url="https://plone-site.com/path/to/survey"
  token="YOUR_EMBED_TOKEN">
</surveyjs-embed>
```

## Security Checklist

- [x] Tokens are HMAC-signed and origin-bound
- [x] HTTPS required for all origins
- [x] Short token lifetimes (5 min default)
- [x] Shadow DOM for style/DOM isolation
- [x] Strict CORS (no wildcards)
- [x] Opt-in at both global and survey level
- [x] Origin allowlist validation
- [x] Token expiration enforcement
- [x] CSRF protection via authenticator tokens
- [x] Permission checks on token generation

## Browser Support

- Chrome 54+ (Shadow DOM v1)
- Firefox 63+ (Shadow DOM v1)
- Safari 10.1+ (Shadow DOM v1)
- Edge 79+ (Chromium-based)

## Files Changed

```
src/zopyx/surveyjs/
├── content/survey.py          (+ Direct DOM fields)
├── interfaces.py              (+ Registry settings)
├── browser/
│   ├── configure.zcml         (+ View registrations)
│   ├── views.py               (+ Embed handling)
│   ├── embed_security.py      (NEW - Token utilities)
│   ├── embed_direct.py        (NEW - Browser views)
│   └── static/
│       └── embed-client.js    (NEW - Web Component)
└── embedding/
    ├── demo.html              (NEW - Standalone demo)
    └── README.md              (NEW - Documentation)
```

## Next Steps (Future Enhancements)

1. **Self-hosted SurveyJS bundle**: Currently loads from CDN
2. **Rate limiting**: Add per-IP and per-origin limits
3. **Audit logging**: Log all token generations and usage
4. **Token revocation**: Allow admins to revoke tokens
5. **Subresource Integrity**: Add SRI hash verification
6. **Web Workers**: Run form JavaScript in isolated context
7. **Automated tests**: Unit and integration tests

## References

- EMBEDDING2.md - Full design specification
- embedding/README.md - Implementation documentation
