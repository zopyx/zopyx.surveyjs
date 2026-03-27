# Concept: SQL-Based Token Storage for SurveyJS

## Executive Summary

This document proposes an alternative SQL-based implementation of the `ITokenStore` interface to complement the existing ZODB/BTree storage. The SQL backend would leverage the existing SQLModel/SQLAlchemy infrastructure already in place for survey result storage, providing:

- **Scalability**: Better performance for large token sets (10,000+ tokens)
- **Cross-instance sharing**: Tokens accessible across multiple Plone instances
- **External integration**: Direct SQL access for reporting and analytics
- **Backup/restore**: Standard database backup procedures
- **Optional coexistence**: Selectable per-survey or global configuration

## Current State Analysis

### Existing ZODB Token Store

```python
# Current implementation
class TokenStore:
    storage = OOBTree()  # In-ZODB annotation
    # Pros: Transactional, no external dependencies
    # Cons: ZODB bloat, no external access, single-instance only
```

**Characteristics:**
- Storage: ZODB annotation (per-survey OOBTree)
- Transaction boundary: Zope transaction
- Access pattern: Dictionary-like key lookup
- Scoping: Per-survey object

### Existing SQL Result Storage

```python
# Pattern to follow
class SurveyResult(SQLModel, table=True):
    poll_id: str = Field(primary_key=True)
    site_id: str = Field(index=True)
    survey_id: str = Field(index=True)
    created: datetime = Field(index=True)
    entry_json: str = Field(sa_column=Column(Text))
```

**Characteristics:**
- Storage: SQL via SQLModel
- Transaction boundary: SQLModel session
- Database: Same connection pool as results
- Scoping: site_id + survey_id composite

## Proposed Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           ITokenStore Interface                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
        ┌───────────────────────┐       ┌───────────────────────┐
        │  ZODBTokenStore       │       │  SQLTokenStore        │
        │  (Existing)           │       │  (Proposed)           │
        │                       │       │                       │
        │  • OOBTree            │       │  • SQLModel table     │
        │  • Annotations        │       │  • Same DB as results │
        │  • ZODB transactions  │       │  • SQL transactions   │
        └───────────────────────┘       └───────────────────────┘
                    │                               │
                    ▼                               ▼
        ┌───────────────────────┐       ┌───────────────────────┐
        │  ZODB / Data.fs       │       │  PostgreSQL/SQLite    │
        │  (local to instance)  │       │  (shared/external)    │
        └───────────────────────┘       └───────────────────────┘
```

### Configuration Strategy

**Option 1: Global Switch (Recommended for MVP)**

```python
# Registry setting
token_storage_backend = "zodb" | "rdbms"

# Same pattern as result_storage_backend
# All surveys use the same backend
```

**Option 2: Per-Survey Override (Future Enhancement)**

```python
# Survey schema field
token_storage_mode = "default" | "zodb" | "rdbms"

# "default" uses global setting
# Allows migration on a per-survey basis
```

## Database Schema Design

### Token Table (SQLModel)

```python
class SurveyToken(SQLModel, table=True):
    """SQL table for survey access tokens with full audit trail."""
    
    __tablename__ = "survey_tokens"
    
    # Primary key: the token itself
    token: str = Field(primary_key=True, max_length=32)
    
    # Scoping fields (composite index)
    site_id: str = Field(index=True, max_length=64)
    survey_id: str = Field(index=True, max_length=256)
    
    # Token state
    created: datetime = Field(index=True)
    used: Optional[datetime] = Field(default=None, index=True)
    
    # Optional: track usage context
    used_by: Optional[str] = Field(default=None, max_length=64)  # username/ip
    used_from: Optional[str] = Field(default=None, max_length=45)  # IP address
    
    # Optional: token metadata
    batch_id: Optional[str] = Field(default=None, index=True)  # generation batch
    notes: Optional[str] = Field(default=None, max_length=500)
```

### Index Strategy

```sql
-- Primary lookups
CREATE INDEX idx_survey_tokens_lookup 
    ON survey_tokens(site_id, survey_id, token);

-- Valid token queries (most common)
CREATE INDEX idx_survey_tokens_valid 
    ON survey_tokens(site_id, survey_id, used) 
    WHERE used IS NULL;

-- Usage statistics
CREATE INDEX idx_survey_tokens_usage 
    ON survey_tokens(site_id, survey_id, created, used);
```

### Comparison with ZODB Schema

| Aspect | ZODB | SQL |
|--------|------|-----|
| **Storage** | OOBTree key-value | Relational table |
| **Token lookup** | `storage[token]` | `SELECT * WHERE token=?` |
| **List all** | `storage.values()` | `SELECT * WHERE survey_id=?` |
| **Stats query** | Python iteration | `SELECT COUNT(*), used IS NULL` |
| **Cross-site** | No (ZODB local) | Yes (shared DB) |

## Implementation Design

### SQLTokenStore Class

```python
@implementer(ITokenStore)
class SQLTokenStore:
    """SQL-backed token store adapter.
    
    Mirrors the ZODB TokenStore interface while providing
    SQL persistence and query capabilities.
    """
    
    def __init__(self, survey, database_uri: Optional[str] = None):
        self.survey = survey
        self._site_id = _get_site_id(survey)
        self._survey_id = _survey_storage_key(survey)
        self._database_uri = database_uri or _get_database_uri()
        self._engine = _get_engine(self._database_uri)
    
    def _session(self) -> Session:
        """Create SQLModel session."""
        return Session(self._engine)
    
    def generate_tokens(self, number: int) -> list:
        """Generate N tokens with batch tracking."""
        batch_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc)
        generated = []
        
        with self._session() as session:
            for _ in range(number):
                token = secrets.token_urlsafe(24)
                session.add(SurveyToken(
                    token=token,
                    site_id=self._site_id,
                    survey_id=self._survey_id,
                    created=now,
                    batch_id=batch_id,
                ))
                generated.append(token)
            session.commit()
        return generated
    
    def has_token(self, token: str) -> bool:
        """Check if token exists and is unused."""
        with self._session() as session:
            row = session.get(SurveyToken, token)
            return (
                row is not None and
                row.site_id == self._site_id and
                row.survey_id == self._survey_id and
                row.used is None
            )
    
    def invalidate(self, token: str, user_info: Optional[dict] = None) -> bool:
        """Mark token as used with optional context."""
        with self._session() as session:
            row = session.get(SurveyToken, token)
            if not row or row.survey_id != self._survey_id:
                return False
            
            row.used = datetime.now(timezone.utc)
            if user_info:
                row.used_by = user_info.get('user')
                row.used_from = user_info.get('ip')
            
            session.commit()
            return True
    
    def list_tokens(self, unused_only: bool = False) -> list:
        """List tokens with optional filtering."""
        with self._session() as session:
            stmt = select(SurveyToken).where(
                SurveyToken.site_id == self._site_id,
                SurveyToken.survey_id == self._survey_id,
            )
            if unused_only:
                stmt = stmt.where(SurveyToken.used.is_(None))
            
            rows = session.exec(stmt).all()
            return [self._row_to_dict(row) for row in rows]
    
    def get_stats(self) -> dict:
        """Get token statistics via SQL aggregation."""
        with self._session() as session:
            # Single query for all stats
            stmt = """
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN used IS NULL THEN 1 END) as unused,
                    COUNT(CASE WHEN used IS NOT NULL THEN 1 END) as used
                FROM survey_tokens
                WHERE site_id = :site_id AND survey_id = :survey_id
            """
            result = session.exec(
                text(stmt),
                {"site_id": self._site_id, "survey_id": self._survey_id}
            ).first()
            
            return {
                "total": result.total,
                "unused": result.unused,
                "used": result.used,
            }
    
    def clear(self) -> None:
        """Delete all tokens for this survey."""
        with self._session() as session:
            stmt = delete(SurveyToken).where(
                SurveyToken.site_id == self._site_id,
                SurveyToken.survey_id == self._survey_id,
            )
            session.exec(stmt)
            session.commit()
```

### Factory and Registration

```python
def get_token_storage(survey) -> ITokenStore:
    """Return configured token storage backend."""
    backend = _get_token_backend_name()  # registry lookup
    
    if backend == "rdbms":
        return SQLTokenStore(survey)
    return TokenStore(survey)  # ZODB default


# ZCML registration
<adapter
    factory=".adapters.token_store.get_token_storage"
    for="zopyx.surveyjs.content.survey.ISurvey"
    provides=".interfaces.ITokenStore"
    />
```

## Migration Strategy

### Phase 1: Schema Preparation

```sql
-- Create table alongside existing results table
CREATE TABLE survey_tokens (
    token VARCHAR(32) PRIMARY KEY,
    site_id VARCHAR(64) NOT NULL,
    survey_id VARCHAR(256) NOT NULL,
    created TIMESTAMP NOT NULL,
    used TIMESTAMP NULL,
    used_by VARCHAR(64) NULL,
    used_from VARCHAR(45) NULL,
    batch_id VARCHAR(8) NULL,
    notes VARCHAR(500) NULL
);

-- Create indexes
CREATE INDEX idx_tokens_survey ON survey_tokens(site_id, survey_id);
CREATE INDEX idx_tokens_valid ON survey_tokens(site_id, survey_id, used);
```

### Phase 2: Data Migration (Optional)

```python
def migrate_survey_tokens(survey, dry_run=True):
    """Migrate tokens from ZODB to SQL for a specific survey."""
    zodb_store = TokenStore(survey)
    sql_store = SQLTokenStore(survey)
    
    tokens = zodb_store.list_tokens()
    
    if dry_run:
        return {"would_migrate": len(tokens)}
    
    # Insert into SQL
    for token_info in tokens:
        # ... insert logic
        pass
    
    # Clear ZODB (optional - can keep as backup)
    # zodb_store.clear()
    
    return {"migrated": len(tokens)}
```

### Phase 3: Gradual Rollout

1. **Development**: Implement and test SQL backend
2. **Staging**: Deploy with both backends, test migrations
3. **Production**: 
   - Default to ZODB (backward compatible)
   - Opt-in specific surveys to SQL via registry
   - Monitor and validate
4. **Full Migration** (future): Switch default to SQL

## Test Concept

### Unit Tests

```python
class TestSQLTokenStore(unittest.TestCase):
    """Test SQL token store implementation."""
    
    layer = SQL_TOKEN_STORE_INTEGRATION_TESTING
    
    def setUp(self):
        self.survey = create_test_survey()
        self.store = SQLTokenStore(self.survey, database_uri=":memory:")
    
    def test_generate_tokens(self):
        """Token generation creates SQL rows."""
        tokens = self.store.generate_tokens(5)
        
        self.assertEqual(len(tokens), 5)
        # Verify in DB
        with self.store._session() as session:
            count = session.exec(
                select(func.count()).select_from(SurveyToken)
            ).one()
            self.assertEqual(count, 5)
    
    def test_has_token_valid(self):
        """Unused token returns True."""
        tokens = self.store.generate_tokens(1)
        
        self.assertTrue(self.store.has_token(tokens[0]))
    
    def test_has_token_used(self):
        """Used token returns False."""
        tokens = self.store.generate_tokens(1)
        self.store.invalidate(tokens[0])
        
        self.assertFalse(self.store.has_token(tokens[0]))
    
    def test_has_token_wrong_survey(self):
        """Token from different survey returns False."""
        tokens = self.store.generate_tokens(1)
        
        other_survey = create_test_survey()
        other_store = SQLTokenStore(other_survey, database_uri=":memory:")
        
        self.assertFalse(other_store.has_token(tokens[0]))
    
    def test_invalidate_records_usage(self):
        """Invalidation records timestamp and context."""
        tokens = self.store.generate_tokens(1)
        
        self.store.invalidate(tokens[0], {
            'user': 'testuser',
            'ip': '192.168.1.1'
        })
        
        info = self.store.get_token_info(tokens[0])
        self.assertIsNotNone(info['used'])
        self.assertEqual(info['used_by'], 'testuser')
    
    def test_get_stats_aggregation(self):
        """Stats use SQL aggregation, not Python iteration."""
        self.store.generate_tokens(10)
        for i, token in enumerate(self.store.list_tokens()[:3]):
            self.store.invalidate(token)
        
        stats = self.store.get_stats()
        
        self.assertEqual(stats['total'], 10)
        self.assertEqual(stats['unused'], 7)
        self.assertEqual(stats['used'], 3)
    
    def test_list_tokens_filtering(self):
        """List tokens supports unused_only filter."""
        self.store.generate_tokens(5)
        tokens = self.store.list_tokens()
        self.store.invalidate(tokens[0])
        
        unused = self.store.list_tokens(unused_only=True)
        
        self.assertEqual(len(unused), 4)
    
    def test_clear_removes_all(self):
        """Clear deletes all survey tokens."""
        self.store.generate_tokens(10)
        
        self.store.clear()
        
        self.assertEqual(self.store.get_stats()['total'], 0)


class TestTokenStoreParity(unittest.TestCase):
    """Ensure SQL and ZODB implementations behave identically."""
    
    def test_interface_compliance(self):
        """Both stores implement ITokenStore."""
        from zope.interface.verify import verifyClass
        
        verifyClass(ITokenStore, TokenStore)
        verifyClass(ITokenStore, SQLTokenStore)
    
    def test_same_behavior(self):
        """Both stores produce same results for same operations."""
        # Create identical scenarios
        zodb_store = TokenStore(create_test_survey())
        sql_store = SQLTokenStore(create_test_survey(), ":memory:")
        
        # Perform operations
        z_tokens = zodb_store.generate_tokens(10)
        s_tokens = sql_store.generate_tokens(10)
        
        # Validate parity
        self.assertEqual(len(z_tokens), len(s_tokens))
        self.assertEqual(zodb_store.get_stats(), sql_store.get_stats())
```

### Integration Tests

```python
class TestSQLTokenStoreIntegration(unittest.TestCase):
    """Integration tests with actual database."""
    
    layer = POSTGRESQL_TOKEN_STORE_INTEGRATION_TESTING
    
    def test_concurrent_access(self):
        """Multiple threads can safely check/invalidate tokens."""
        # PostgreSQL with proper isolation
        pass
    
    def test_transaction_rollback(self):
        """Failed transactions don't leave partial state."""
        pass
    
    def test_cross_instance_sharing(self):
        """Tokens visible across different Plone instances."""
        pass


class TestMigration(unittest.TestCase):
    """Migration from ZODB to SQL."""
    
    def test_migration_preserves_state(self):
        """Migrated tokens retain used/unused status."""
        pass
    
    def test_migration_preserves_timestamps(self):
        """Created/used timestamps maintained."""
        pass
    
    def test_migration_idempotent(self):
        """Running migration twice is safe."""
        pass
```

### Performance Tests

```python
class TestSQLTokenStorePerformance(unittest.TestCase):
    """Performance comparison between backends."""
    
    def test_bulk_generation_speed(self):
        """SQL bulk insert vs ZODB bulk insert."""
        # Generate 10,000 tokens
        # Measure time
        pass
    
    def test_lookup_performance(self):
        """Token lookup speed at scale."""
        # With 100,000 tokens
        # Random lookup performance
        pass
    
    def test_stats_query_performance(self):
        """SQL aggregation vs ZODB iteration."""
        # Large token sets
        # Stats calculation comparison
        pass
```

## Risk Analysis

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Data inconsistency** | Low | High | ACID transactions, same patterns as result storage |
| **Performance regression** | Low | Medium | Benchmark before rollout, index optimization |
| **Migration failure** | Medium | High | Dry-run mode, backup ZODB data, rollback plan |
| **Concurrent access bugs** | Medium | High | Extensive testing, use existing SQL patterns |
| **Database connection issues** | Low | High | Fallback to ZODB, graceful degradation |

## Decision Matrix

### When to Use ZODB (Current)

| Criteria | Preference |
|----------|------------|
| Small token sets (< 1,000) | ✓ ZODB |
| Single-instance deployment | ✓ ZODB |
| No external reporting needed | ✓ ZODB |
| Simplicity priority | ✓ ZODB |
| Existing ZODB backup procedures | ✓ ZODB |

### When to Use SQL (Proposed)

| Criteria | Preference |
|----------|------------|
| Large token sets (> 10,000) | ✓ SQL |
| Multi-instance/load-balanced | ✓ SQL |
| External analytics/reporting | ✓ SQL |
| Already using SQL for results | ✓ SQL |
| Need usage tracking (IP, user) | ✓ SQL |
| Cross-system integration | ✓ SQL |

## Conclusion

The SQL-based token store provides a scalable, feature-rich alternative to the current ZODB implementation while maintaining full interface compatibility. The implementation follows established patterns from the existing SQL result storage, minimizing risk and leveraging proven infrastructure.

### Recommended Next Steps

1. **Proof of Concept**: Implement `SQLTokenStore` with basic CRUD operations
2. **Benchmark**: Performance test with realistic token volumes (1K, 10K, 100K)
3. **Migration Tool**: Build and test migration utilities
4. **Integration Test**: Multi-instance scenario validation
5. **Documentation**: Update admin docs with SQL backend instructions
6. **Gradual Rollout**: Registry-based opt-in for specific surveys

### Estimated Effort

| Phase | Effort | Complexity |
|-------|--------|------------|
| Implementation | 2-3 days | Medium |
| Unit Tests | 1-2 days | Low |
| Integration Tests | 2-3 days | Medium |
| Migration Tools | 1-2 days | Medium |
| Documentation | 1 day | Low |
| **Total** | **8-12 days** | **Medium** |
