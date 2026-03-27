# Token Store Implementation

## Overview

The Token Store provides token-based access control for surveys. Each survey can have multiple unique access tokens (32-character URL-safe) that grant one-time access to participants.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Survey (ISurvey)                         │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              ITokenStore (adapter)                       │   │
│  │                                                          │   │
│  │   ┌─────────────────────────────────────────────────┐   │   │
│  │   │         OOBTree storage (annotation)             │   │   │
│  │   │                                                  │   │   │
│  │   │   token1 -> {token, created, used}              │   │   │
│  │   │   token2 -> {token, created, used}              │   │   │
│  │   │   ...                                           │   │   │
│  │   └─────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Access Flow

```
Participant                    SurveyJS Viewer                    Auth Service
    |                                |                                  |
    |  1. Request with ?auth_token   |                                  |
    | ─────────────────────────────> |                                  |
    |                                |  2. Validate token               |
    |                                | ───────────────────────────────> |
    |                                |                                  | 3. Check ITokenStore
    |                                |                                  |    (has_token)
    |                                |                                  |
    |                                |  4. Token valid                  |
    |                                | <─────────────────────────────── |
    |                                |                                  | 5. Invalidate token
    |                                |                                  |    (invalidate)
    |  6. Show form                  |                                  |
    | <───────────────────────────── |                                  |
    |                                |                                  |
    |  7. Submit form                |                                  |
    | ─────────────────────────────> |                                  |
    |  8. Success response           |                                  |
    | <───────────────────────────── |                                  |
```

## Components

### 1. ITokenStore Interface

**Location:** `src/zopyx/surveyjs/interfaces.py`

```python
class ITokenStore(Interface):
    def generate_tokens(number: int) -> list:
        """Generate N new 32-character URL-safe tokens."""
        
    def has_token(token: str) -> bool:
        """Check if token exists and is unused."""
        
    def invalidate(token: str) -> bool:
        """Mark token as used (single-use)."""
        
    def get_token_info(token: str) -> dict:
        """Get token metadata."""
        
    def list_tokens() -> list:
        """List all tokens."""
        
    def clear() -> None:
        """Remove all tokens."""
```

### 2. TokenStore Adapter

**Location:** `src/zopyx/surveyjs/adapters/token_store.py`

Uses `BTrees.OOBTree` for efficient ZODB storage.

**Token Format:**
- Length: 32 characters
- Alphabet: URL-safe base64 (A-Z, a-z, 0-9, -, _)
- Example: `aB3xK9mP2vL5-nQ8w_R4tY7jU1zXcD4e`
- Entropy: ~192 bits (24 bytes × 8)

**Storage Schema:**
```python
{
    "token": "aB3xK9mP2vL5nQ8wR4tY7jU1",
    "created": "2024-01-15T10:30:00+00:00",
    "used": None  # or "2024-01-15T11:00:00+00:00"
}
```

**Annotation Key:** `zopyx.surveyjs.token-store`

### 3. AuthService Integration

**Location:** `src/zopyx/surveyjs/browser/services/auth.py`

The AuthService handles two access modes:

| Mode | Token Source | Validation | Invalidation |
|------|--------------|------------|--------------|
| `trusted` | Cached tokens (diskcache) | Check cache metadata | TTL expiration |
| `trusted-tokens` | ITokenStore adapter | `has_token()` | `invalidate()` |

**Key Methods:**

```python
def _require_trusted_access_tokens(self, token, logger=None):
    """Validate token using ITokenStore (for 'trusted-tokens' mode)."""
    token_store = getAdapter(self.context, ITokenStore)
    
    # Check if token exists and is unused
    if not token_store.has_token(token):
        return False  # Token invalid or already used
    
    # Mark token as used (invalidate it) - SINGLE USE
    token_store.invalidate(token)
    return True
```

### 4. Browser View

**Location:** `src/zopyx/surveyjs/browser/token_store.py`
**Template:** `src/zopyx/surveyjs/browser/token_store.pt`

**URL:** `http://localhost:8080/demo/path/to/survey/@@token-store`

**Features:**
- Generate up to 10,000 tokens at once
- Display statistics (total/unused/used)
- Download CSV of unused tokens
- Clear all tokens

## Implementation Notes

### Token Generation

```python
import secrets

def _generate_token(self) -> str:
    """Generate a cryptographically secure URL-safe token."""
    return secrets.token_urlsafe(24)  # 32 characters
```

**Security Considerations:**
- Uses `secrets.token_urlsafe()` for cryptographic security
- 64^24 = 2^144 possible combinations (~2.2 × 10^43)
- ~192 bits of entropy from 24 random bytes

### Single-Use Token Flow

1. **Generation:** Manager generates tokens via `@@token-store`
2. **Distribution:** CSV download contains URLs with `?tt=TOKEN`
3. **First Access:** User opens URL → token validated → token invalidated
4. **Subsequent Access:** Same URL → token invalid → access denied

### Error Handling

**Backend Error Codes:**
- `trusted_access_token_missing` - No token provided
- `trusted_tokens_token_invalid` - Token invalid or already used
- `trusted_tokens_store_unavailable` - ITokenStore adapter unavailable

**Frontend Error Messages:**
- "This form requires a trusted access link. Please use the link provided by the form owner."
- "This access token is invalid or has already been used."
- "Token store service is temporarily unavailable. Please try again later."

### Viewer Integration

**Location:** `src/zopyx/surveyjs/browser/static/viewer.js`

The viewer handles token validation:

```javascript
// Check for both auth_token (token store) and access_token (cached)
const accessToken = urlParams.get("auth_token") || urlParams.get("access_token");

// Hide container initially when token is present
if (trustedAccessEnabled && accessToken) {
  surveyContainer.classList.add("survey-container-hidden");
}

// Load form with token
fetch(ACTUAL_URL + "/get-form-json?" + tokenParam + "=" + accessToken)
  .then(response => {
    if (!response.ok) {
      // Show error message
      showAccessError(trustedAccessMessages[errorKey]);
    }
  });
```

## Usage

### Programmatic API

```python
from zope.component import getAdapter
from zopyx.surveyjs.interfaces import ITokenStore

# Get adapter
token_store = getAdapter(survey, ITokenStore)

# Generate tokens
tokens = token_store.generate_tokens(100)
# Returns: ['aB3xK9mP2vL5-nQ8w_R4tY7jU1zXcD4e', 'xYz9AbC-dE3fG4hI5jK6lM7nP0qRsTuV', ...]

# Check token
if token_store.has_token('aB3xK9mP2vL5-nQ8w_R4tY7jU1zXcD4e'):
    print("Token valid")

# Invalidate (mark as used)
token_store.invalidate('aB3xK9mP2vL5-nQ8w_R4tY7jU1zXcD4e')

# Get info
info = token_store.get_token_info('aB3xK9mP2vL5-nQ8w_R4tY7jU1zXcD4e')
# Returns: {'token': 'aB3xK9mP2vL5nQ8wR4tY7jU1', 'created': '...', 'used': '...'}

# List all tokens
all_tokens = token_store.list_tokens()

# Clear all
token_store.clear()
```

### Web Interface

1. Navigate to survey → `@@token-store`
2. Enter quantity (1-10000)
3. Click **Generate**
4. Click **Download CSV** to get unused token URLs
5. Distribute URLs to participants

**CSV Format:**
```csv
token,url
aB3xK9mP2vL5-nQ8w_R4tY7jU1zXcD4e,http://.../survey?tt=aB3xK9mP2vL5-nQ8w_R4tY7jU1zXcD4e
xYz9AbC-dE3fG4hI5jK6lM7nP0qRsTuV,http://.../survey?tt=xYz9AbC-dE3fG4hI5jK6lM7nP0qRsTuV
```

## Security

- **Permission:** `cmf.ManagePortal` (Manager role required)
- **Single-use tokens:** Each token can only be used once
- **No listing of used tokens:** CSV only includes unused tokens
- **Confirmation required:** Clear action requires JavaScript confirmation
- **Cryptographic tokens:** Uses `secrets` module for generation

## Storage Details

- **Backend:** ZODB via OOBTree
- **Persistence:** Tokens survive server restarts
- **Per-survey isolation:** Each survey has its own token store
- **Key:** `zopyx.surveyjs.token-store` in object annotations

## Testing

```bash
# Run token store tests
bin/test -s zopyx.surveyjs.adapters

# Run browser view tests
bin/test -s zopyx.surveyjs.browser.tests

# Run all tests
make test
```

**Test Coverage:**
- Adapter interface compliance
- Token generation (32-char URL-safe format)
- Has/invalidate operations
- CSV download (only unused tokens)
- Statistics calculation
- View permissions

## Integration

The token store is registered in `configure.zcml`:

```xml
<adapter
    factory=".token_store.TokenStore"
    provides="zopyx.surveyjs.interfaces.ITokenStore"
    for="zopyx.surveyjs.content.survey.ISurvey"
/>
```

Browser view registration:

```xml
<browser:page
    name="token-store"
    for="zopyx.surveyjs.content.survey.ISurvey"
    permission="cmf.ManagePortal"
    class=".token_store.TokenStoreView"
    template="token_store.pt"
/>
```

## Files Modified/Created

| File | Description |
|------|-------------|
| `src/zopyx/surveyjs/interfaces.py` | ITokenStore interface |
| `src/zopyx/surveyjs/constants.py` | TOKEN_STORE_KEY constant |
| `src/zopyx/surveyjs/adapters/token_store.py` | TokenStore adapter |
| `src/zopyx/surveyjs/adapters/configure.zcml` | Adapter registration |
| `src/zopyx/surveyjs/browser/token_store.py` | Browser view |
| `src/zopyx/surveyjs/browser/token_store.pt` | View template |
| `src/zopyx/surveyjs/browser/services/auth.py` | AuthService integration |
| `src/zopyx/surveyjs/browser/static/viewer.js` | Frontend token handling |
| `src/zopyx/surveyjs/browser/survey_viewer.pt` | Viewer template updates |
| `src/zopyx/surveyjs/content/survey.py` | survey_access_vocabulary |
| `src/zopyx/surveyjs/browser/static/survey_add_form.json` | Add form schema |
| `src/zopyx/surveyjs/browser/static/survey_edit_form.json` | Edit form schema |

## Future Enhancements

- [ ] Token expiration (time-based invalidation)
- [ ] Token usage logging (track when/which tokens were used)
- [ ] Bulk token import (for external token generation)
- [ ] Token remaining count display in viewer
- [ ] Email token distribution
