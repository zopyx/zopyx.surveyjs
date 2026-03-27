# Token Store Implementation

## Overview

The Token Store provides token-based access control for surveys. Each survey can have multiple unique access tokens (UUID4) that grant one-time access to participants.

## Architecture

```
Survey (ISurvey)
    |
    +-- ITokenStore (adapter)
            |
            +-- OOBTree storage (annotation)
                    |
                    +-- token -> {token, created, used}
```

## Components

### 1. ITokenStore Interface

**Location:** `src/zopyx/surveyjs/interfaces.py`

```python
class ITokenStore(Interface):
    def generate_tokens(number: int) -> list:
        """Generate N new UUID4 tokens."""
        
    def has_token(token: str) -> bool:
        """Check if token exists and is unused."""
        
    def invalidate(token: str) -> bool:
        """Mark token as used."""
        
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

**Storage Schema:**
```python
{
    "token": "uuid4-string",
    "created": "2024-01-15T10:30:00+00:00",
    "used": None  # or "2024-01-15T11:00:00+00:00"
}
```

**Annotation Key:** `zopyx.surveyjs.token-store`

### 3. Browser View

**Location:** `src/zopyx/surveyjs/browser/token_store.py`
**Template:** `src/zopyx/surveyjs/browser/token_store.pt`

**URL:** `http://localhost:8080/demo/path/to/survey/@@token-store`

**Features:**
- Generate up to 10,000 tokens at once
- Display statistics (total/unused/used)
- Download CSV of unused tokens
- Clear all tokens

## Usage

### Programmatic API

```python
from zope.component import getAdapter
from zopyx.surveyjs.interfaces import ITokenStore

# Get adapter
token_store = getAdapter(survey, ITokenStore)

# Generate tokens
tokens = token_store.generate_tokens(100)
# Returns: ['uuid4-1', 'uuid4-2', ...]

# Check token
if token_store.has_token('uuid4-1'):
    print("Token valid")

# Invalidate (mark as used)
token_store.invalidate('uuid4-1')

# Get info
info = token_store.get_token_info('uuid4-1')
# Returns: {'token': 'uuid4-1', 'created': '...', 'used': '...'}

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
uuid4-1,http://.../survey?auth_token=uuid4-1
uuid4-2,http://.../survey?auth_token=uuid4-2
```

## Security

- **Permission:** `cmf.ManagePortal` (Manager role required)
- **Single-use tokens:** Each token can only be used once
- **No listing of used tokens:** CSV only includes unused tokens
- **Confirmation required:** Clear action requires JavaScript confirmation

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
- Token generation uniqueness
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
