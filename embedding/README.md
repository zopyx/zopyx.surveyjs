# Direct DOM Embedding Implementation

This directory contains the implementation of the Direct DOM Embedding feature for zopyx.surveyjs, as specified in EMBEDDING2.md.

## Overview

Direct DOM Embedding allows SurveyJS forms to be seamlessly integrated into external websites without using iframes. Instead, forms are rendered directly in the host page using:

- **Shadow DOM**: For style and DOM isolation
- **HMAC-signed tokens**: For origin-bound authentication
- **CORS**: For controlled cross-origin access
- **Short-lived credentials**: Tokens expire after a configurable time (default: 5 minutes)

## Security Layers

1. **Origin Authentication**: Cryptographic tokens bound to specific origins
2. **CORS Enforcement**: Strict origin validation with no wildcards
3. **Shadow DOM Isolation**: Style and DOM separation from host page
4. **Token-Based Authorization**: HMAC-signed, time-limited tokens
5. **HTTPS Required**: Non-HTTPS origins are rejected

## Files

### Backend (Python)

| File | Description |
|------|-------------|
| `src/zopyx/surveyjs/browser/embed_security.py` | Token generation, validation, and security utilities |
| `src/zopyx/surveyjs/browser/embed_direct.py` | Browser views for token, config, loader endpoints |

### Frontend (JavaScript)

| File | Description |
|------|-------------|
| `src/zopyx/surveyjs/browser/static/embed-client.js` | Standalone embed client (reference) |
| `embedding/demo.html` | Standalone demo page for testing |

### Configuration

| File | Changes |
|------|---------|
| `src/zopyx/surveyjs/content/survey.py` | Added `embed_direct_*` fields to ISurvey schema |
| `src/zopyx/surveyjs/interfaces.py` | Added `embed_direct_*` registry settings |
| `src/zopyx/surveyjs/browser/configure.zcml` | Registered new views |
| `src/zopyx/surveyjs/browser/views.py` | Added direct embedding helpers and save_poll enhancement |

## API Endpoints

### 1. Token Generation

```
POST /path/to/survey/@@embed-token
Content-Type: application/json

{
  "origin": "https://example.com",
  "ttl_seconds": 300
}
```

Response:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_at": "2026-03-04T12:00:00Z",
  "origin": "https://example.com",
  "survey_uid": "abc123",
  "embed_url": "https://plone-site.com/path/to/survey/@@embed-loader"
}
```

### 2. Form Configuration

```
GET /path/to/survey/@@embed-config
Origin: https://example.com
X-Embed-Token: eyJhbGciOiJIUzI1NiIs...
```

Response:
```json
{
  "form_json": { /* SurveyJS form definition */ },
  "form_version": "v1.2.3",
  "csrf_token": "...",
  "submit_endpoint": "https://plone-site.com/.../@@save-poll",
  "session_id": "uuid-for-this-session"
}
```

### 3. Embed Loader Script

```
GET /path/to/survey/@@embed-loader
```

Returns the JavaScript bundle that creates the `<surveyjs-embed>` custom element.

### 4. Demo Page

```
GET /path/to/survey/@@embed-direct-demo
```

Renders a demo page showing the embedded form with configuration details.

## Setup Instructions

### 1. Enable Globally

Go to Site Setup -> Forms Settings -> Direct DOM Embedding:

- **Enable Direct DOM Embedding globally**: Check this box
- **Embed Token Signing Key**: Generate a random secret (32+ characters)
- **Maximum origins per survey**: Set your preferred limit (default: 10)

### 2. Configure Survey

Edit a Survey and set:

- **Embedding mode**: "Direct DOM (experimental)"
- **Allowed origins for direct embedding**: Add HTTPS origins (e.g., `https://example.com`)
- **Embed token TTL**: Token lifetime in seconds (60-3600, default: 300)

### 3. Generate Token

Users with `ModifyPortalContent` permission can generate tokens via:

```bash
curl -X POST \
  https://plone-site.com/path/to/survey/@@embed-token \
  -H "Content-Type: application/json" \
  -d '{"origin": "https://example.com", "ttl_seconds": 300}'
```

### 4. Embed on External Site

Add to your HTML:

```html
<script src="https://plone-site.com/path/to/survey/@@embed-loader"></script>
<surveyjs-embed 
  survey-url="https://plone-site.com/path/to/survey"
  token="YOUR_EMBED_TOKEN">
</surveyjs-embed>
```

## Demo

### In-Plone Demo

Visit the survey and navigate to `@@embed-direct-demo`:

```
https://plone-site.com/path/to/survey/@@embed-direct-demo
```

### Standalone Demo

Open `embedding/demo.html` in a browser and enter the Survey URL and Token.

## Security Considerations

- **Never commit the signing key** to version control
- **Always use HTTPS** for both Plone and embedded sites
- **Keep token lifetimes short** (5 minutes recommended)
- **Validate origins strictly** - no wildcards allowed
- **Monitor token cache** for unusual activity
- **Rotate signing keys regularly**

## Troubleshooting

### Token validation fails
- Check that the token hasn't expired
- Verify the origin matches exactly (including protocol)
- Ensure the signing key is configured correctly

### CORS errors
- Check that the origin is in the survey's allowed origins list
- Verify HTTPS is being used
- Check browser console for specific CORS error messages

### Form doesn't render
- Check browser console for JavaScript errors
- Verify SurveyJS library loaded correctly
- Ensure the Shadow DOM is supported by the browser (Chrome, Firefox, Safari, Edge)

## Browser Support

- Chrome 54+
- Firefox 63+
- Safari 10.1+
- Edge 79+

## References

- EMBEDDING2.md - Full design specification
- Shadow DOM: https://developer.mozilla.org/en-US/docs/Web/Web_Components/Using_shadow_DOM
- Custom Elements: https://developer.mozilla.org/en-US/docs/Web/Web_Components/Using_custom_elements
