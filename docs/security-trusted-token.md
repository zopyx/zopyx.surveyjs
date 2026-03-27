# Trusted Token (Cached/Reusable) Security Feature

## Overview

The **Trusted Token** feature provides time-limited, reusable access control for surveys/forms. Unlike the single-use trusted-tokens mode, this mode generates a time-bound access token that can be reused multiple times within its validity period. This is ideal for:

- Time-limited survey campaigns
- Internal testing with team members
- Temporary access windows for specific groups
- Scenarios where users may need to access the form multiple times

## Architecture

### Components

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Trusted       │────▶│   Diskcache      │────▶│   Filesystem    │
│   Access Panel  │     │   Token Store    │     │   (var/token_)  │
│   (Manager UI)  │     │                  │     │   cache.db)     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                       │
         │              ┌────────┴────────┐
         │              │                 │
         ▼              ▼                 ▼
┌─────────────────┐  ┌─────────────┐  ┌─────────────┐
│  Token Issue    │  │  Token      │  │  Token      │
│  (@@trusted-    │  │  Validation │  │  Revocation │
│   access-token) │  │  (has/get)  │  │  (revoke)   │
└─────────────────┘  └─────────────┘  └─────────────┘
```

### Data Model

Each cached token is stored with the following metadata:

```python
{
    "form_id": "survey-uid-or-id",
    "form_version": "version-uuid",
    "issued_at": "2026-03-27T10:30:00+00:00",
    "expires_at": "2026-04-03T10:30:00+00:00",
    "state": "ISSUED"  # or "REVOKED"
}
```

### Storage

- **Backend**: Diskcache (sqlite-based file cache)
- **Path**: Configurable via registry, default `var/token_cache.db`
- **Key Format**: `trusted:<token_string>`
- **TTL**: Configurable per-survey (default 168 hours / 7 days)

## Usage

### Enabling Trusted Token Mode

1. Navigate to the survey and click **Metadata**
2. Set **Access Mode** to `trusted`
3. Configure **Trusted Access TTL (hours)** - how long tokens remain valid
4. Save the survey

### Managing Access

Once enabled, Managers see a **Trusted access link** panel on the survey view:

#### Generate Access Link

1. Go to **View** (the survey viewer page)
2. Expand the "Trusted access link" panel
3. The system automatically generates:
   - Access URL with token parameter
   - Token string
   - Expiration timestamp
4. Click **Copy link** to copy the URL to clipboard

#### Token Lifecycle

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Generated  │───▶│   Shared     │───▶│   Accessed   │───▶│   Expired    │
│   (issued)   │    │   (URL sent) │    │   (multiple) │    │   (TTL ends) │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
       │                   │                   │
       │                   │                   │
       ▼                   ▼                   ▼
  issued_at=now      state=ISSUED        state=ISSUED
  expires_at=+7d                         (until expires)
```

### Access Flow

1. **Manager**: Generates trusted access link via the panel
2. **Distribution**: Shares the link with intended participants
3. **Participant**: Opens link with `?access_token=<token>` parameter
4. **Validation**: System checks cache for valid, non-expired, non-revoked token
5. **Access**: Form renders if token valid
6. **Reuse**: Same link works for multiple accesses until expiration

## Technical Implementation

### Token Generation

Located in `browser/services/auth.py`:

```python
def issue_trusted_access_token(self, form_version_id):
    """Issue a single trusted-access token and persist its metadata."""
    token = secrets.token_urlsafe(TRUSTED_ACCESS_TOKEN_BYTES)  # 16 bytes
    ttl_seconds = self._trusted_access_ttl_seconds()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    
    metadata = {
        "form_id": self._form_id(),
        "form_version": form_version_id,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "state": "ISSUED",
    }
    
    cache.set(
        self._trusted_access_cache_key(token),
        metadata,
        expire=ttl_seconds,
    )
    return token, metadata
```

### Token Validation

```python
def _require_trusted_access_cached(self, token, logger=None):
    """Validate cached trusted access token."""
    cache = self._token_cache(settings)
    metadata = cache.get(self._trusted_access_cache_key(token))
    
    if not isinstance(metadata, dict):
        return False  # Token not found
        
    if metadata.get("state") == "REVOKED":
        return False  # Token revoked
        
    if metadata.get("form_id") != self._form_id():
        return False  # Wrong form
        
    return True  # Valid and not expired (cache handles TTL)
```

### API Endpoint

The token is obtained via AJAX call to:

```
POST/GET {context}/@@trusted-access-token
```

Response:
```json
{
    "isSuccess": true,
    "token": "abc123...",
    "url": "https://example.com/survey?access_token=abc123...",
    "expires_at": "2026-04-03T10:30:00+00:00"
}
```

## Configuration

### Registry Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `trusted_access_ttl_hours` | 168 (7 days) | How long tokens remain valid |

### Per-Survey Settings

Set via survey Metadata form:

- **Access Mode**: Must be `trusted`
- **Trusted Access TTL (hours)**: Override default TTL

## Security Considerations

### Token Properties

- **Length**: 22 characters URL-safe base64 (16 bytes entropy)
- **Cryptography**: `secrets.token_urlsafe(16)` - CSPRNG
- **Uniqueness**: High entropy prevents guessing

### Cache Security

- **Storage**: Local filesystem only (not distributed)
- **Permissions**: Follows filesystem permissions
- **No network exposure**: Cache file not served by web server

### Token Validity

- **Time-bound**: Automatic expiration via cache TTL
- **Form-scoped**: Token only valid for specific survey
- **Revocable**: Can be marked as REVOKED before TTL expires

### Protection Against

| Attack Vector | Protection |
|---------------|------------|
| **Token reuse** | Intentional - token reusable within TTL |
| **Token sharing** | Link can be shared (by design for this mode) |
| **Brute force** | High entropy tokens, cache lookups are fast |
| **Replay attacks** | Token remains valid (no one-time use) |
| **Tampering** | Cache integrity via diskcache library |

## Comparison with Trusted-Tokens (Single-Use)

| Feature | Trusted (Cached) | Trusted-Tokens |
|---------|-----------------|---------------|
| **Use count** | Multiple uses within TTL | Single use only |
| **Storage** | Diskcache (temporary) | ZODB (permanent) |
| **Management** | Auto-generated, single panel | Generate many, full token store UI |
| **Best for** | Team access, time windows | Controlled distribution, single submissions |
| **Revocation** | Supported (state=REVOKED) | Implicit (mark as used) |
| **Audit trail** | Limited (cache only) | Full (permanent storage) |

## Error States

Same expressive error UI as trusted-tokens mode:

| Error | Meaning |
|-------|---------|
| **Missing Token** | No access_token parameter |
| **Invalid Token** | Token not in cache or expired |
| **Revoked Token** | Token was manually revoked |
| **Form Mismatch** | Token for different survey |
| **Service Unavailable** | Diskcache cannot be accessed |

## Troubleshooting

### "Trusted access service is temporarily unavailable"

- Diskcache cannot open/create cache file
- Check permissions on `var/` directory
- Verify disk space available

### Token expires too quickly

- Check survey's **Trusted Access TTL** setting
- Verify system clock is correct
- Cache may have been cleared/restarted

### Cannot see Trusted access panel

- Verify survey access_mode is `trusted` (not `trusted-tokens`)
- Must have Manager or Modify portal content permission

### Link works for some users but not others

- Token is scoped to the specific survey URL
- Check for URL variations (http vs https, different domains)

## Migration Between Modes

### From Public to Trusted

1. Change access_mode to `trusted`
2. Generate and distribute trusted access link
3. Previous direct URLs will no longer work

### From Trusted to Trusted-Tokens

1. Change access_mode to `trusted-tokens`
2. Go to **Tokens** view
3. Generate new single-use tokens
4. Existing cached tokens become invalid

### From Trusted to Public

1. Change access_mode to `public`
2. All access restrictions removed
3. Existing tokens become irrelevant

## Future Enhancements

Potential improvements:

1. **Multiple active tokens**: Support several concurrent access links
2. **Usage limits**: Max uses per token before auto-expiration
3. **IP restrictions**: Limit token validity to specific IP ranges
4. **Audit logging**: Log all token usage to persistent storage
5. **Token refresh**: Allow extending TTL for active tokens
