# Trusted Tokens (One-Time Use) Security Feature

## Overview

The **Trusted Tokens** feature provides a secure, single-use access control mechanism for surveys/forms. Each token can only be used once to access and submit a form, ensuring that:

- Each respondent can only submit the form once
- Access links cannot be shared or reused
- Form owners have full control over who can participate

## Architecture

### Components

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Token Store   │────▶│  ITokenStore     │────▶│   ZODB/BTree    │
│   View (UI)     │     │  Adapter         │     │   Storage       │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                       │
         │              ┌────────┴────────┐
         │              │                 │
         ▼              ▼                 ▼
┌─────────────────┐  ┌─────────────┐  ┌─────────────┐
│  Token Actions  │  │  generate_  │  │  has_token  │
│  (Generate,     │  │  tokens()   │  │  invalidate │
│   Download,     │  │             │  │  list_tokens│
│   Clear)        │  │             │  │  get_stats  │
└─────────────────┘  └─────────────┘  └─────────────┘
```

### Data Model

Each token is stored as a dictionary with the following structure:

```python
{
    "token": "abc123...xyz",      # 32-char URL-safe token
    "created": "2026-03-27T10:30:00+00:00",  # ISO format timestamp
    "used": None | "2026-03-27T11:15:00+00:00"  # None if unused, timestamp if used
}
```

### Storage

- **Backend**: ZODB via BTrees.OOBTree
- **Key**: `zopyx.surveyjs.token-store` (constant)
- **Location**: Stored as annotation on the survey object
- **Scope**: Per-survey (each survey has its own token store)

## Usage

### Enabling Trusted Tokens Mode

1. Navigate to the survey and click **Metadata**
2. Set **Access Mode** to `trusted-tokens`
3. Save the survey

### Managing Tokens

Once enabled, a **Tokens** action button appears in the survey actions (only visible to Managers):

#### Generate Tokens

1. Go to **Tokens** view
2. Enter the number of tokens to generate (1-10000)
3. Click **Generate**

#### Download Tokens

Two CSV export options are available:

| Export Type | Contents | Use Case |
|-------------|----------|----------|
| **Download valid tokens** | Only unused tokens with URLs | Distribute to new participants |
| **Download all tokens** | All tokens with metadata (created, used timestamps, status) | Auditing and reporting |

**CSV Formats:**

Valid tokens CSV:
```csv
token,url
abc123...,https://example.com/survey?tt=abc123...
```

All tokens CSV:
```csv
token,url,created,used,status
abc123...,https://example.com/survey?tt=abc123...,2026-03-27T10:30:00+00:00,,unused
def456...,https://example.com/survey?tt=def456...,2026-03-27T10:30:00+00:00,2026-03-27T11:15:00+00:00,used
```

#### Clear All Tokens

Click **Clear All** to remove all tokens from the store (requires confirmation).

### Token Lifecycle

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Generated  │───▶│   Issued     │───▶│    Used      │───▶│   Expired    │
│   (created)  │    │   (URL sent) │    │  (submitted) │    │   (rejected) │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
       │                   │                   │
       │                   │                   │
       ▼                   ▼                   ▼
  created=now       used=None            used=now
  used=None                              (locked)
```

### Access Flow

1. **Form Owner**: Generates tokens → Downloads CSV → Distributes URLs to participants
2. **Participant**: Receives unique URL with `?tt=<token>` parameter
3. **Access Check**: System validates token via `ITokenStore.has_token()`
4. **Submission**: On successful form submission, token is invalidated via `ITokenStore.invalidate()`
5. **Reuse Attempt**: Any subsequent access with same token shows error state

## Technical Implementation

### ITokenStore Interface

```python
class ITokenStore(Interface):
    def generate_tokens(number: int) -> list:
        """Generate N new tokens, return list of token strings."""
        
    def has_token(token: str) -> bool:
        """Check if token exists and is valid (unused)."""
        
    def invalidate(token: str) -> bool:
        """Mark token as used (called on successful submission)."""
        
    def list_tokens() -> list:
        """Return all tokens with their info dicts."""
        
    def get_stats() -> dict:
        """Return {total, used, unused} counts."""
        
    def clear() -> None:
        """Remove all tokens."""
```

### Access Validation

Located in `browser/services/auth.py`:

```python
def _require_trusted_access_tokens(self, token, logger=None):
    """Validate token using ITokenStore."""
    token_store = getAdapter(self.context, ITokenStore)
    
    if not token_store.has_token(token):
        # Token invalid, expired, or already used
        return False
    
    # Token valid - proceed to form
    return True
```

### Token Consumption

Located in `browser/services/auth.py`:

```python
def consume_trusted_access_token(self, logger=None):
    """Invalidate token after successful submission."""
    token_store = getAdapter(self.context, ITokenStore)
    
    if not token_store.invalidate(token):
        return False
    
    # Token marked as used
    return True
```

## Security Considerations

### Token Generation

- **Cryptography**: Uses `secrets.token_urlsafe(24)` - cryptographically secure random
- **Length**: 32 characters URL-safe base64
- **Uniqueness**: Generated tokens are unique within the survey

### Token Validation

- **Timing-safe**: No timing attacks possible (direct dict lookup)
- **Atomic consumption**: Token is only invalidated on successful submission
- **No reuse**: Once used, token cannot be reused (permanent state change)

### Error Handling

Five distinct error states ensure users receive clear feedback without security information leakage:

1. **Missing Token**: No token parameter in URL
2. **Invalid/Expired**: Token doesn't exist or was already used
3. **Revoked**: Token was manually revoked (future feature)
4. **Service Unavailable**: Token store backend unavailable
5. **Generic**: Fallback for unexpected errors

### Protection Against

| Attack Vector | Protection |
|---------------|------------|
| **Token reuse** | Single-use design, permanent invalidation |
| **Token sharing** | Each URL unique to one participant |
| **Brute force** | 32-char random tokens, rate limiting via standard Plone |
| **Token enumeration** | No enumeration endpoint, single-token validation only |

## Comparison with Trusted Access (Cached Tokens)

| Feature | Trusted Tokens (This) | Trusted Access (Cached) |
|---------|----------------------|-------------------------|
| **Use count** | Single-use only | Can be reused within TTL |
| **Storage** | ZODB (permanent) | Diskcache (temporary) |
| **Management** | Token Store UI | Auto-generated links |
| **Best for** | Controlled distribution, single submissions | Time-limited access windows |

## Troubleshooting

### Common Issues

**"This access token is invalid, expired, or has already been used"**
- Token was already used for submission
- Generate new tokens and distribute fresh URLs

**"Token store service is temporarily unavailable"**
- ZODB connection issue
- Check Plone error logs

**Tokens action not visible**
- Verify user has Manager role
- Verify survey access_mode is set to "trusted-tokens"

## Future Enhancements

Potential improvements for the token system:

1. **Bulk import**: Import tokens from external systems
2. **Email integration**: Direct email distribution of tokens
3. **Usage tracking**: Track IP address and user agent on token use
4. **Revocation API**: Programmatic token revocation
5. **Token expiration**: Time-based expiration in addition to single-use
