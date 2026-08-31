# -*- coding: utf-8 -*-
"""Key-value store facade mirroring the diskcache API used by zopyx.surveyjs.

Two families of interchangeable implementations of the six-method
:class:`KVStore` interface:

* :class:`DiskCacheStore` — a thin pass-through wrapper over
  ``diskcache.Cache`` preserving its behavior (including an explicit zero
  lock timeout).
* :class:`SQLKVStore` — an SQLAlchemy-backed store on a single
  ``survey_kv_store`` table, supporting the SQLite, DuckDB, PostgreSQL and
  MySQL dialects. Expiry is stored as a UTC epoch float (no
  timezone-aware/naive datetime comparisons) and writes use atomic
  single-statement DML (see "Write semantics" below).

The production call sites (``browser/services/auth.py``,
``browser/embed_security.py``, ``monitoring.py``) use the configured
``get_configured_kv_store(...)`` factory. The selected backend and location
come from registry settings; the SQL implementations are therefore available
for production deployments, not only tests.

Supported API methods: ``set``, ``add``, ``get``, ``iterkeys``, ``delete``,
``close`` — with TTL via the ``expire`` parameter (seconds; ``None`` means
no expiry).

Write semantics
---------------
``set()`` uses a dialect-native atomic upsert: ``ON CONFLICT DO UPDATE``
for SQLite/PostgreSQL/DuckDB and ``ON DUPLICATE KEY UPDATE`` for MySQL. It
never performs a read-then-write sequence, so concurrent writers cannot lose
the value. ``add()`` is the security-sensitive primitive: it returns ``True``
exactly once for concurrent attempts on an absent or expired key. It runs the
INSERT first; on the unique-key conflict it performs a conditional UPDATE that
only matches an expired row (``expires_at IS NOT NULL AND expires_at <= now``).
The success signal is dialect-appropriate: the UPDATE...RETURNING row presence
for SQLite/PostgreSQL (DuckDB uses its parameterized ON CONFLICT statement),
while MySQL uses rowcount. A live existing row fails the WHERE clause, so
``add()`` returns False for it.

Deliberate deviations from raw diskcache (pinned by tests):

1. SQL values are JSON encoded with orjson, not pickled; only
   JSON-compatible values are supported (``TypeError`` for anything else).
2. SQL ``iterkeys()`` excludes already-expired rows; the diskcache wrapper
   preserves diskcache's own (culling-dependent) behavior.
3. SQL ``get()`` may delete an expired row it encounters (conditional lazy
   purge); diskcache owns its own culling behavior.
4. SQL keys longer than 255 Unicode code points raise ``ValueError`` from
   every method; diskcache accepts arbitrary string keys.
5. ``SQLKVStore.close()`` is a no-op because sessions are operation-scoped
   and the engine is shared/cached. A closed ``DiskCacheStore`` preserves
   diskcache's post-close behavior.
"""

from __future__ import annotations

import abc
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterator, Optional

import diskcache
import orjson
from sqlalchemy import (
    Column,
    Double,
    Index,
    String,
    Text,
    delete,
    insert,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.mysql import LONGTEXT, insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Field, SQLModel

from .storage import _get_engine

MAX_KEY_LENGTH = 255

#: SQL dialects SQLKVStore is implemented and tested against.
SUPPORTED_BACKENDS = frozenset({"sqlite", "duckdb", "postgresql", "mysql"})
KV_METRICS = Counter()

_LOCKED_ERROR_FRAGMENTS = (
    "database is locked",
    "database is busy",
    "duplicate key",
    "unique constraint violation",
    "primary key or unique constraint violation",
)


def _metric(name: str, amount: int = 1) -> None:
    KV_METRICS[name] += amount


def get_kv_metrics() -> dict[str, int]:
    """Return process-local, credential-free KV operational counters."""
    return dict(KV_METRICS)


def validate_kv_database_uri(database_uri: str):
    """Validate a supported KV URI and return its parsed SQLAlchemy URL.

    Remote PostgreSQL/MySQL connections must explicitly opt into TLS. Driver
    names are checked here so configuration errors are reported before the
    first request attempts to use the store.
    """
    try:
        url = make_url(str(database_uri).strip())
    except Exception as exc:
        raise ValueError("invalid KV database URI") from exc
    backend = url.get_backend_name()
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(f"unsupported KV database backend: {backend!r}")
    driver = url.drivername.partition("+")[2]
    allowed_drivers = {
        "postgresql": {"", "psycopg", "psycopg2"},
        "mysql": {"", "pymysql", "mysqlconnector"},
    }
    if backend in allowed_drivers and driver not in allowed_drivers[backend]:
        raise ValueError(f"unsupported {backend} KV database driver: {driver!r}")

    host = (url.host or "").lower()
    remote = host not in {"", "localhost", "127.0.0.1", "::1"}
    if remote and backend in {"postgresql", "mysql"}:
        query = {key.lower() for key in url.query}
        if backend == "postgresql":
            sslmode = str(url.query.get("sslmode", "")).lower()
            if sslmode not in {"require", "verify-ca", "verify-full"}:
                raise ValueError(
                    "remote PostgreSQL KV connections require sslmode=require "
                    "or stronger"
                )
        elif not query.intersection({"ssl", "ssl_ca", "ssl_cert", "ssl_key"}):
            raise ValueError("remote MySQL KV connections require explicit TLS options")
    return url


def get_kv_store_diagnostics(settings: Any, namespace: str) -> dict[str, Any]:
    """Return safe configuration diagnostics without credentials or values."""
    backend = str(getattr(settings, "kv_cache_backend", "diskcache") or "diskcache")
    backend = backend.strip().lower()
    result: dict[str, Any] = {"backend": backend, "namespace": namespace}
    if backend == "diskcache":
        path = _resolve_diskcache_path(
            str(getattr(settings, "kv_cache_directory", "var/surveyjs-cache")),
            namespace,
        )
        result.update({"path": path, "configured": True})
        return result
    uri = str(getattr(settings, "kv_cache_database_uri", "") or "").strip()
    url = validate_kv_database_uri(uri)
    result.update(
        {
            "backend": "rdbms",
            "sql_backend": url.get_backend_name(),
            "driver": url.drivername,
            "host": url.host or "localhost",
            "port": url.port,
            "database": url.database,
            "tls": "sslmode" in url.query or any(
                key in url.query for key in ("ssl", "ssl_ca", "ssl_cert", "ssl_key")
            ),
            "configured": True,
        }
    )
    return result


class KVStore(abc.ABC):
    """Interface mirroring the diskcache calls used in this codebase."""

    @abc.abstractmethod
    def set(self, key: str, value: Any, expire: Optional[float] = None) -> Any:
        """Store ``value`` under ``key``, expiring after ``expire`` seconds
        (``None`` = no expiry). Returns a truthy result on success."""

    @abc.abstractmethod
    def add(self, key: str, value: Any, expire: Optional[float] = None) -> bool:
        """Store only if ``key`` is absent or expired; return True exactly
        once for concurrent attempts on the same key."""

    @abc.abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for ``key``, or ``default`` when missing or
        expired."""

    @abc.abstractmethod
    def iterkeys(self) -> Iterator[str]:
        """Yield the live (non-expired) keys."""

    @abc.abstractmethod
    def delete(self, key: str) -> Any:
        """Remove ``key`` if present; return a truthy result when a key was
        removed."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release resources."""

    @abc.abstractmethod
    def cleanup_expired(
        self, limit: int = 1000, prefix: Optional[str] = None
    ) -> int:
        """Remove up to ``limit`` expired entries."""


class DiskCacheStore(KVStore):
    """Pass-through facade over ``diskcache.Cache`` (identical behavior)."""

    def __init__(self, path: str, timeout: Optional[float] = None):
        if timeout is not None:
            # Preserve an explicit zero instead of falling back to
            # diskcache's default lock timeout.
            self._cache = diskcache.Cache(path, timeout=timeout)
        else:
            self._cache = diskcache.Cache(path)
        _metric("stores_opened.diskcache")

    def set(self, key: str, value: Any, expire: Optional[float] = None) -> Any:
        return self._cache.set(key, value, expire=expire)

    def add(self, key: str, value: Any, expire: Optional[float] = None) -> bool:
        return bool(self._cache.add(key, value, expire=expire))

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default=default)

    def iterkeys(self) -> Iterator[str]:
        return iter(self._cache.iterkeys())

    def delete(self, key: str) -> Any:
        return self._cache.delete(key)

    def close(self) -> None:
        self._cache.close()

    def cleanup_expired(
        self, limit: int = 1000, prefix: Optional[str] = None
    ) -> int:
        del limit, prefix  # diskcache controls its own culling batch size
        removed = int(self._cache.expire())
        _metric("expired_entries_removed", removed)
        return removed


class KVEntry(SQLModel, table=True):
    """SQL table backing :class:`SQLKVStore` (one row per key)."""

    __tablename__ = "survey_kv_store"
    __table_args__ = (
        Index("ix_survey_kv_store_expires_at", "expires_at"),
        {"extend_existing": True},
    )

    key: str = Field(
        sa_column=Column(String(MAX_KEY_LENGTH), primary_key=True, nullable=False)
    )
    value: str = Field(
        sa_column=Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    )
    # UTC epoch seconds; NULL means "no expiry". Double (64-bit) on every
    # dialect: Float would compile to 32-bit FLOAT on DuckDB/MySQL and lose
    # epoch precision.
    expires_at: Optional[float] = Field(
        default=None, sa_column=Column(Double, nullable=True)
    )


def _validate_key(key: Any) -> str:
    """Validate a key against the facade contract.

    SQLite does not enforce VARCHAR length, so the limit is enforced here.
    """
    if not isinstance(key, str):
        raise TypeError(f"key must be str, got {type(key).__name__}")
    if len(key) > MAX_KEY_LENGTH:
        raise ValueError(
            f"key longer than {MAX_KEY_LENGTH} characters: {len(key)}"
        )
    return key


def _encode(value: Any) -> str:
    """JSON-encode a value; unsupported values raise TypeError."""
    return orjson.dumps(value).decode("utf-8")


def _decode(raw: str) -> Any:
    return orjson.loads(raw)


def _deadline(expire: Optional[float]) -> Optional[float]:
    """UTC epoch deadline for ``expire`` seconds from now (None = never)."""
    if expire is None:
        return None
    return time.time() + expire


def _is_locked_error(exc: OperationalError) -> bool:
    message = str(exc).lower()
    return any(fragment in message for fragment in _LOCKED_ERROR_FRAGMENTS)


def _retry_locked(operation, attempts: int = 5, base_delay: float = 0.02):
    """Run ``operation`` (which opens its own session) retrying transient
    SQLite lock errors with bounded exponential backoff.

    Each retry reruns the whole statement in a fresh session; the failed
    session is closed by its context manager. Non-lock operational errors
    and all other errors propagate immediately.
    """
    last_exc = None
    for attempt in range(attempts):
        try:
            return operation()
        except OperationalError as exc:
            last_exc = exc
            if not _is_locked_error(exc):
                raise
            _metric("sql_retries")
            time.sleep(base_delay * (2**attempt))
    raise last_exc


class SQLKVStore(KVStore):
    """SQLAlchemy-backed KV store with atomic write semantics.

    Supported URI schemes: ``sqlite``, ``duckdb``, ``postgresql``, ``mysql``
    (anything else raises ``ValueError``). Expiry is stored as a UTC epoch
    float, avoiding timezone-aware/naive datetime differences between
    dialects.
    """

    def __init__(self, database_uri: str):
        url = validate_kv_database_uri(database_uri)
        backend = url.get_backend_name()
        if backend not in SUPPORTED_BACKENDS:
            raise ValueError(
                f"SQLKVStore supports {sorted(SUPPORTED_BACKENDS)} URIs, "
                f"got backend {backend!r}"
            )
        self._uri = database_uri
        self._backend = backend
        # MySQL has no UPDATE ... RETURNING; rowcount is the success signal.
        self._uses_rowcount = backend == "mysql"
        self._engine = _get_engine(database_uri)
        # Explicit create_all: the engine may already be cached from an
        # earlier construction (e.g. by SQLResultStorage) before this table
        # class was registered, in which case _get_engine will not create it.
        SQLModel.metadata.create_all(self._engine)
        _metric(f"stores_opened.{backend}")

    def _session(self):
        from sqlmodel import Session

        return Session(self._engine)

    def _upsert_statement(self, key: str, value: str, expires_at: Optional[float]):
        values = {"key": key, "value": value, "expires_at": expires_at}
        if self._backend == "mysql":
            statement = mysql_insert(KVEntry).values(**values)
            return statement.on_duplicate_key_update(
                value=statement.inserted.value,
                expires_at=statement.inserted.expires_at,
            )
        if self._backend == "duckdb":
            return text(
                'INSERT INTO survey_kv_store ("key", value, expires_at) '
                'VALUES (:key, :value, :expires_at) '
                'ON CONFLICT ("key") DO UPDATE SET '
                'value = excluded.value, expires_at = excluded.expires_at'
            )
        insert_factory = (
            postgresql_insert if self._backend == "postgresql" else sqlite_insert
        )
        statement = insert_factory(KVEntry).values(**values)
        return statement.on_conflict_do_update(
            index_elements=[KVEntry.key],
            set_={"value": statement.excluded.value, "expires_at": statement.excluded.expires_at},
        )

    def set(self, key: str, value: Any, expire: Optional[float] = None) -> Any:
        """Insert or replace unconditionally in one atomic statement."""
        key = _validate_key(key)
        encoded = _encode(value)
        deadline = _deadline(expire)

        def _op():
            with self._session() as session:
                statement = self._upsert_statement(key, encoded, deadline)
                if self._backend == "duckdb":
                    session.execute(
                        statement,
                        {"key": key, "value": encoded, "expires_at": deadline},
                    )
                else:
                    session.execute(statement)
                session.commit()
            return True

        return _retry_locked(_op)

    def add(self, key: str, value: Any, expire: Optional[float] = None) -> bool:
        """Insert only if absent or expired; atomic test-and-set.

        The INSERT succeeds exactly once for concurrent callers. A unique
        conflict is resolved by a conditional UPDATE that only matches an
        expired row (``expires_at <= now``); a live row leaves the value
        untouched and reports False.
        """
        key = _validate_key(key)
        encoded = _encode(value)
        deadline = _deadline(expire)
        now = time.time()

        def _op():
            with self._session() as session:
                try:
                    session.execute(
                        insert(KVEntry).values(
                            key=key, value=encoded, expires_at=deadline
                        )
                    )
                    session.commit()
                    return True
                except IntegrityError:
                    session.rollback()
                    conflict_stmt = (
                        update(KVEntry)
                        .where(
                            KVEntry.key == key,
                            KVEntry.expires_at.isnot(None),
                            KVEntry.expires_at <= now,
                        )
                        .values(value=encoded, expires_at=deadline)
                    )
                    if self._uses_rowcount:
                        result = session.execute(conflict_stmt)
                        replaced = result.rowcount == 1
                    else:
                        result = session.execute(
                            conflict_stmt.returning(KVEntry.key)
                        )
                        replaced = result.first() is not None
                    session.commit()
                    return replaced

        return _retry_locked(_op)

    def get(self, key: str, default: Any = None) -> Any:
        key = _validate_key(key)
        now = time.time()
        with self._session() as session:
            row = session.get(KVEntry, key)
            if row is None:
                return default
            if row.expires_at is not None and row.expires_at <= now:
                # Conditional lazy purge: never delete a row that a
                # concurrent writer refreshed after our observed `now`.
                session.execute(
                    delete(KVEntry).where(
                        KVEntry.key == key, KVEntry.expires_at <= now
                    )
                )
                session.commit()
                return default
            try:
                return _decode(row.value)
            except orjson.JSONDecodeError:
                return default

    def iterkeys(self) -> Iterator[str]:
        now = time.time()
        with self._session() as session:
            stmt = select(KVEntry.key).where(
                or_(KVEntry.expires_at.is_(None), KVEntry.expires_at > now)
            )
            # Materialize while the session is open; do not hand out a
            # session-backed generator.
            keys = list(session.execute(stmt).scalars())
        return iter(keys)

    def delete(self, key: str) -> Any:
        key = _validate_key(key)

        def _op():
            with self._session() as session:
                result = session.execute(delete(KVEntry).where(KVEntry.key == key))
                session.commit()
                # DuckDB reports -1; the return value is informational.
                return result.rowcount > 0 if result.rowcount is not None else False

        return _retry_locked(_op)

    def cleanup_expired(
        self, limit: int = 1000, prefix: Optional[str] = None
    ) -> int:
        """Delete up to ``limit`` expired rows, optionally by key prefix."""
        if limit < 1:
            return 0
        now = time.time()
        conditions = [
            KVEntry.expires_at.isnot(None),
            KVEntry.expires_at <= now,
        ]
        if prefix is not None:
            conditions.append(KVEntry.key.startswith(prefix))
        with self._session() as session:
            keys = list(
                session.execute(
                    select(KVEntry.key).where(*conditions).limit(limit)
                ).scalars()
            )
            if not keys:
                return 0
            result = session.execute(delete(KVEntry).where(KVEntry.key.in_(keys)))
            session.commit()
            removed = max(result.rowcount or 0, 0)
            _metric("expired_entries_removed", removed)
            return removed

    def close(self) -> None:
        """No-op: sessions are operation-scoped and the engine is shared."""


class NamespacedKVStore(KVStore):
    """Expose an isolated key namespace over another KV store."""

    def __init__(self, store: KVStore, namespace: str):
        self._store = store
        self._prefix = f"{namespace}:"

    def _key(self, key: str) -> str:
        return self._prefix + key

    def set(self, key: str, value: Any, expire: Optional[float] = None) -> Any:
        return self._store.set(self._key(key), value, expire=expire)

    def add(self, key: str, value: Any, expire: Optional[float] = None) -> bool:
        return self._store.add(self._key(key), value, expire=expire)

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(self._key(key), default=default)

    def iterkeys(self) -> Iterator[str]:
        prefix_length = len(self._prefix)
        return (
            key[prefix_length:]
            for key in self._store.iterkeys()
            if key.startswith(self._prefix)
        )

    def delete(self, key: str) -> Any:
        return self._store.delete(self._key(key))

    def cleanup_expired(
        self, limit: int = 1000, prefix: Optional[str] = None
    ) -> int:
        physical_prefix = self._prefix + prefix if prefix is not None else self._prefix
        return self._store.cleanup_expired(limit=limit, prefix=physical_prefix)

    def close(self) -> None:
        self._store.close()


def _resolve_diskcache_path(directory: str, namespace: str) -> str:
    """Resolve a namespace directory relative to INSTANCE_HOME."""
    path = Path(os.path.expanduser(directory))
    if not path.is_absolute():
        instance_home = os.environ.get("INSTANCE_HOME")
        path = Path(instance_home) / path if instance_home else Path.cwd() / path
    return str(path / namespace)


def _resolve_legacy_diskcache_path(path: str) -> str:
    """Resolve a customized legacy cache path consistently."""
    resolved = Path(os.path.expanduser(path))
    if not resolved.is_absolute():
        instance_home = os.environ.get("INSTANCE_HOME")
        resolved = Path(instance_home) / resolved if instance_home else Path.cwd() / resolved
    return str(resolved)


def get_configured_kv_store(
    settings: Any,
    namespace: str,
    *,
    legacy_diskcache_path: Optional[str] = None,
    timeout: Optional[float] = None,
) -> KVStore:
    """Create a configured, namespaced KV store.

    ``kv_cache_backend`` selects ``diskcache`` or ``rdbms``. For diskcache,
    the configured base directory is resolved against ``INSTANCE_HOME``. The
    legacy auth cache path remains supported when it is explicitly customized.
    For RDBMS, ``kv_cache_database_uri`` is required and is never inferred
    from the result-storage database URI.
    """
    backend = str(getattr(settings, "kv_cache_backend", "diskcache") or "diskcache")
    backend = backend.strip().lower()
    if backend == "diskcache":
        if legacy_diskcache_path and legacy_diskcache_path != "var/token_cache.db":
            location = _resolve_legacy_diskcache_path(legacy_diskcache_path)
        else:
            directory = getattr(settings, "kv_cache_directory", "var/surveyjs-cache")
            location = _resolve_diskcache_path(str(directory), namespace)
        if timeout is None:
            timeout = getattr(settings, "kv_cache_lock_timeout_seconds", 5.0)
        store = get_kv_store("diskcache", location, timeout=float(timeout))
    elif backend == "rdbms":
        uri = str(getattr(settings, "kv_cache_database_uri", "") or "").strip()
        if not uri:
            raise ValueError("kv_cache_database_uri is required for the rdbms backend")
        sql_backend = validate_kv_database_uri(uri).get_backend_name()
        store = get_kv_store(sql_backend, uri)
    else:
        raise ValueError(f"unknown KV cache backend: {backend!r}")
    return NamespacedKVStore(store, namespace)


def get_kv_store(
    backend: str, path_or_uri: str, timeout: Optional[float] = None
) -> KVStore:
    """Construct a KV store implementation.

    :param backend: one of ``diskcache``, ``sqlite``, ``duckdb``,
        ``postgresql``, ``mysql``.
    :param path_or_uri: filesystem path (diskcache) or SQLAlchemy URI.
        Required — there is no implicit cwd-relative default.
    :param timeout: diskcache lock timeout (diskcache backend only).
    """
    if not path_or_uri:
        raise ValueError("path_or_uri is required")
    backend_name = (backend or "").strip().lower()
    if backend_name == "diskcache":
        return DiskCacheStore(path_or_uri, timeout=timeout)
    if backend_name in SUPPORTED_BACKENDS:
        return SQLKVStore(path_or_uri)
    raise ValueError(
        f"unknown backend {backend_name!r}; expected one of "
        f"'diskcache', {sorted(SUPPORTED_BACKENDS)}"
    )
