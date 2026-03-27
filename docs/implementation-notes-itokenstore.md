# ITokenStore Implementation Notes

## Overview

`ITokenStore` is an adapter interface for managing single-use access tokens in SurveyJS. This document provides implementation details, design decisions, and guidelines for developers implementing or extending token storage backends.

## Interface Contract

### Method Signatures and Semantics

```python
class ITokenStore(Interface):
    def generate_tokens(number: int) -> list:
        """Generate N tokens, return list of token strings."""
        
    def has_token(token: str) -> bool:
        """Check existence AND validity (unused). Returns False if used."""
        
    def invalidate(token: str) -> bool:
        """Mark as used. Idempotent - returns True even if already used."""
        
    def get_token_info(token: str) -> dict:
        """Return full token info or None if not found."""
        
    def list_tokens() -> list:
        """Return ALL tokens, both used and unused."""
        
    def clear() -> None:
        """Delete all tokens. Irreversible."""
```

### Critical Design Constraints

#### 1. Single-Use Semantics

The `has_token()` method implements the single-use guarantee:

```python
# Pseudocode for has_token
def has_token(token):
    if token not in storage:
        return False
    if storage[token].used is not None:
        return False  # Already used!
    return True
```

**Important**: `has_token()` returns `False` for used tokens, even though they exist in storage.

#### 2. Token Invalidation is Permanent

Once `invalidate()` is called, the token can never be used again:

```python
# Token lifecycle
generate_tokens() -> has_token() == True -> invalidate() -> has_token() == False
```

**No undo operation** is provided by design.

#### 3. Idempotent Operations

- `invalidate()` on already-used token: returns `True` (success), no error
- `clear()` on empty store: silently succeeds
- `generate_tokens(0)`: returns empty list

## Data Model

### Token Info Dictionary Structure

All implementations MUST return token info with these exact keys:

```python
{
    "token": "abc123...xyz",           # str: the token string itself
    "created": "2026-03-27T10:30:00+00:00",  # str: ISO 8601 datetime
    "used": None | "2026-03-27T11:15:00+00:00"  # None or ISO 8601 datetime
}
```

### Timestamp Format

- **Timezone**: Always UTC
- **Format**: ISO 8601 with timezone offset (`+00:00`)
- **Precision**: Microseconds optional, but recommended

```python
from datetime import datetime, timezone

# Correct
created = datetime.now(timezone.utc).isoformat()
# "2026-03-27T10:30:00.123456+00:00"

# Wrong - no timezone
created = datetime.utcnow().isoformat()
# "2026-03-27T10:30:00" - REJECTED
```

## Reference Implementation (ZODB/BTree)

### Storage Structure

```python
# Key: TOKEN_STORE_KEY = 'zopyx.surveyjs.token-store'
# Value: OOBTree mapping token_string -> token_info_dict

annotations[survey] = {
    'zopyx.surveyjs.token-store': OOBTree({
        'token1...': {'token': 'token1...', 'created': '...', 'used': None},
        'token2...': {'token': 'token2...', 'created': '...', 'used': '...'},
    })
}
```

### Implementation Pattern

```python
@implementer(ITokenStore)
class TokenStore:
    def __init__(self, survey):
        self.survey = survey
        self._annotations = IAnnotations(survey)
    
    def _get_storage(self) -> OOBTree:
        """Lazy initialization pattern - create on first access."""
        if TOKEN_STORE_KEY not in self._annotations:
            self._annotations[TOKEN_STORE_KEY] = OOBTree()
        return self._annotations[TOKEN_STORE_KEY]
```

### Transaction Safety

ZODB provides ACID guarantees:

```python
# All operations within Zope transaction
with transaction.manager:
    store.generate_tokens(10)
    # If error occurs, all tokens rolled back
    store.invalidate(token)
```

## Implementation Guidelines

### New Backend Checklist

When implementing `ITokenStore` for a new backend (e.g., SQL, Redis, Filesystem):

#### Required

- [ ] Implement all 6 interface methods
- [ ] Return correct token info dict structure
- [ ] Use UTC ISO 8601 timestamps
- [ ] Make `has_token()` return False for used tokens
- [ ] Ensure atomic `invalidate()` operation
- [ ] Handle non-existent tokens gracefully
- [ ] Implement proper scoping (per-survey isolation)

#### Recommended

- [ ] Lazy initialization of storage
- [ ] Connection pooling/reuse
- [ ] Batch operations for `generate_tokens()`
- [ ] Index on `used` field for efficient queries
- [ ] Audit logging for security events

### Thread Safety

Implementations must be thread-safe:

```python
# ZODB: OOBTree is thread-safe (MVCC)
# SQL: Use proper transaction isolation
# Redis: Use atomic operations

# Example: SQL with proper locking
class SQLTokenStore:
    def invalidate(self, token):
        with self._session() as session:
            # SELECT FOR UPDATE prevents race conditions
            row = session.exec(
                select(SurveyToken)
                .where(SurveyToken.token == token)
                .with_for_update()
            ).first()
            if row:
                row.used = datetime.now(timezone.utc)
                session.commit()
                return True
            return False
```

### Error Handling

| Scenario | Behavior | Return Value |
|----------|----------|--------------|
| Token not found | Silent | `has_token()`: False, `invalidate()`: False, `get_token_info()`: None |
| Token already used | Normal operation | `invalidate()`: True |
| Storage unavailable | Raise exception | Let caller handle |
| Invalid token format | Silent rejection | `has_token()`: False |

## Security Considerations

### Token Generation

**MUST** use cryptographically secure random:

```python
# Correct
import secrets
token = secrets.token_urlsafe(24)  # 32 chars

# Wrong - predictable!
import random
token = ''.join(random.choices(string.ascii_letters, k=32))
```

### Timing Attack Prevention

`has_token()` should execute in constant time regardless of:
- Whether token exists
- Whether token is used

```python
# Vulnerable - different code paths
def has_token(self, token):
    if token not in storage:  # Fast path
        return False
    info = storage[token]     # Slow path (cache miss)
    return info['used'] is None

# Better - consistent operations
def has_token(self, token):
    info = storage.get(token)  # Always fetch
    if info is None:
        return False
    return info.get('used') is None
```

### Scope Isolation

Tokens MUST be scoped to prevent cross-survey access:

```python
# Survey A tokens should not work for Survey B
token_store_a = ITokenStore(survey_a)
token_store_b = ITokenStore(survey_b)

tokens = token_store_a.generate_tokens(1)
token_store_b.has_token(tokens[0])  # Must return False!
```

## Performance Optimization

### Query Patterns

Common operations ranked by frequency:

1. **`has_token()`** - Most frequent (every form access)
2. **`invalidate()`** - Frequent (every submission)
3. **`get_stats()`** - Moderate (token store view)
4. **`list_tokens()`** - Rare (CSV export)
5. **`generate_tokens()`** - Rare (admin action)
6. **`clear()`** - Very rare (admin action)

### Optimization Strategies

```python
# For high-frequency has_token():
# - Use hash-based lookup (dict/OOBTree/Redis)
# - Cache hot tokens in memory
# - Use database index on token column

# For stats queries:
# - Maintain counters (total/unused/used)
# - Use SQL COUNT with WHERE clauses
# - Avoid Python iteration

# For list_tokens():
# - Implement pagination
# - Use streaming for large datasets
# - Consider background export
```

## Testing Requirements

### Unit Test Suite

Every implementation must pass:

```python
class TokenStoreTestMixin:
    """Mixin for testing any ITokenStore implementation."""
    
    def test_generate_creates_valid_tokens(self):
        tokens = self.store.generate_tokens(5)
        assert len(tokens) == 5
        for t in tokens:
            assert len(t) == 32  # token_urlsafe(24) -> 32 chars
            assert self.store.has_token(t)
    
    def test_has_token_returns_false_for_used(self):
        tokens = self.store.generate_tokens(1)
        self.store.invalidate(tokens[0])
        assert not self.store.has_token(tokens[0])
    
    def test_has_token_returns_false_for_nonexistent(self):
        assert not self.store.has_token('nonexistent-token-string-12345')
    
    def test_invalidate_is_idempotent(self):
        tokens = self.store.generate_tokens(1)
        assert self.store.invalidate(tokens[0])  # First time
        assert self.store.invalidate(tokens[0])  # Second time - still True
    
    def test_get_token_info_returns_correct_structure(self):
        tokens = self.store.generate_tokens(1)
        info = self.store.get_token_info(tokens[0])
        assert 'token' in info
        assert 'created' in info
        assert 'used' in info
        assert info['used'] is None
    
    def test_get_token_info_returns_none_for_missing(self):
        assert self.store.get_token_info('missing') is None
    
    def test_list_tokens_includes_all(self):
        tokens = self.store.generate_tokens(3)
        self.store.invalidate(tokens[0])
        all_tokens = self.store.list_tokens()
        assert len(all_tokens) == 3
    
    def test_clear_removes_all(self):
        self.store.generate_tokens(10)
        self.store.clear()
        assert len(self.store.list_tokens()) == 0
    
    def test_scoping_isolation(self):
        # Two stores for different surveys
        store_a = self.create_store(survey_a)
        store_b = self.create_store(survey_b)
        
        tokens = store_a.generate_tokens(1)
        assert store_a.has_token(tokens[0])
        assert not store_b.has_token(tokens[0])
```

### Concurrency Tests

```python
import threading

def test_concurrent_invalidation(self):
    """Only one invalidate should succeed in race."""
    tokens = self.store.generate_tokens(1)
    results = []
    
    def try_invalidate():
        results.append(self.store.invalidate(tokens[0]))
    
    threads = [threading.Thread(target=try_invalidate) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # All should report success, but only first actually wrote
    assert all(results)
    # Token should be used
    assert not self.store.has_token(tokens[0])
```

## Integration with Survey Access Flow

### Authentication Service

```python
# From browser/services/auth.py
class AuthService:
    def _require_trusted_access_tokens(self, token, logger=None):
        """Validate token using ITokenStore."""
        try:
            token_store = getAdapter(self.context, ITokenStore)
        except Exception:
            return False  # Store unavailable
        
        if not token_store.has_token(token):
            # Could be: doesn't exist, already used, wrong survey
            return False
        
        return True
    
    def consume_trusted_access_token(self, logger=None):
        """Invalidate after successful submission."""
        token = self._get_token_from_request()
        token_store = getAdapter(self.context, ITokenStore)
        
        if not token_store.invalidate(token):
            return False
        
        logger.info(f"Token consumed: {token}")
        return True
```

### View Layer

```python
# Token store browser view
def __call__(self):
    if 'generate_tokens' in form:
        count = int(form.get('num_tokens', 0))
        self.token_store.generate_tokens(count)
        return redirect()
    
    if 'download_valid_tokens' in form:
        tokens = [
            t for t in self.token_store.list_tokens()
            if t['used'] is None  # Filter unused
        ]
        return generate_csv(tokens)
```

## Migration Between Backends

### Zero-Downtime Migration Strategy

```python
def migrate_tokens_zodb_to_sql(survey, batch_size=100):
    """Migrate tokens while preserving all state."""
    zodb_store = TokenStore(survey)
    sql_store = SQLTokenStore(survey)
    
    tokens = zodb_store.list_tokens()
    
    for i in range(0, len(tokens), batch_size):
        batch = tokens[i:i + batch_size]
        
        for token_info in batch:
            sql_store._insert_token(
                token=token_info['token'],
                created=token_info['created'],
                used=token_info['used'],
            )
        
        # Commit batch
        sql_store._commit()
    
    # Verify counts match
    assert zodb_store.get_stats() == sql_store.get_stats()
    
    # Switch active backend (registry change)
    # Clear ZODB (optional)
```

## Debugging and Monitoring

### Log Events

```python
# Recommended logging
logger.info("Tokens generated", extra={
    "survey": survey.UID(),
    "count": 10,
    "batch_id": batch_id,
})

logger.info("Token validated", extra={
    "survey": survey.UID(),
    "token": token[:8] + "...",  # Partial for privacy
})

logger.info("Token consumed", extra={
    "survey": survey.UID(),
    "token": token[:8] + "...",
    "user": user_id,
})
```

### Metrics

Track these metrics for operational insight:

| Metric | Description |
|--------|-------------|
| `tokens_generated_total` | Counter of tokens created |
| `tokens_consumed_total` | Counter of tokens used |
| `token_validation_duration` | Histogram of has_token() latency |
| `token_store_size` | Gauge of tokens per survey |

## Common Pitfalls

### 1. Naive Stats Implementation

```python
# Bad - O(n) iteration
def get_stats(self):
    tokens = self.list_tokens()
    total = len(tokens)
    used = sum(1 for t in tokens if t['used'])
    return {'total': total, 'used': used, 'unused': total - used}

# Good - O(1) or database aggregation
def get_stats(self):
    return self._storage.get_stats()  # Backend-optimized
```

### 2. Mutable Default Arguments

```python
# Dangerous
def generate_tokens(self, number, metadata={}):
    # metadata dict shared across calls!
    
# Safe
def generate_tokens(self, number, metadata=None):
    metadata = metadata or {}
```

### 3. Timezone-Naive Datetimes

```python
# Wrong - no timezone
'created': datetime.utcnow().isoformat()

# Correct - explicit UTC
'created': datetime.now(timezone.utc).isoformat()
```

### 4. Race Condition in invalidate

```python
# Vulnerable - check-then-act
def invalidate(self, token):
    if self.has_token(token):  # Check
        self._mark_used(token)   # Act - might have changed!
        return True
    return False

# Safe - atomic operation
def invalidate(self, token):
    return self._atomic_mark_used(token)
```

## Summary

`ITokenStore` provides a clean abstraction for single-use token management. Key takeaways:

1. **Single-use guarantee** is the core responsibility
2. **Token info structure** must be consistent across implementations
3. **UTC timestamps** are mandatory
4. **Thread-safety** is critical for production use
5. **Idempotent operations** prevent errors on retries
6. **Scope isolation** prevents cross-survey token leakage

For new implementations, follow the reference ZODB/BTree implementation patterns and ensure full test coverage using the provided test mixin.
