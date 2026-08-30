# -*- coding: utf-8 -*-
"""Key-value store facade mirroring the diskcache API used by zopyx.surveyjs.

Two interchangeable implementations of the six-method :class:`KVStore`
interface:

* :class:`DiskCacheStore` — a thin pass-through wrapper over
  ``diskcache.Cache`` preserving its behavior (including an explicit zero
  lock timeout).
* :class:`SQLKVStore` — a SQLite-only backend backed by a single
  ``survey_kv_store`` table, using SQLite dialect upsert statements with
  atomic ``add()`` semantics and epoch-based expiry.

The production call sites (``browser/services/auth.py``,
``browser/embed_security.py``, ``monitoring.py``) are unchanged in this
phase; this module only provides the facade they will later be wired to.

Supported API methods: ``set``, ``add``, ``get``, ``iterkeys``, ``delete``,
``close`` — with TTL via the ``expire`` parameter (seconds; ``None`` means
no expiry).

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
import time
from typing import Any, Iterator, Optional

import diskcache
import orjson
from sqlalchemy import Column, Float, String, Text, and_, delete, or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlmodel import Field, SQLModel

from .storage import _get_engine

MAX_KEY_LENGTH = 255

_LOCKED_ERROR_FRAGMENTS = ("database is locked", "database is busy")


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


class DiskCacheStore(KVStore):
    """Pass-through facade over ``diskcache.Cache`` (identical behavior)."""

    def __init__(self, path: str, timeout: Optional[float] = None):
        if timeout is not None:
            # Preserve an explicit zero instead of falling back to
            # diskcache's default lock timeout.
            self._cache = diskcache.Cache(path, timeout=timeout)
        else:
            self._cache = diskcache.Cache(path)

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


class KVEntry(SQLModel, table=True):
    """SQL table backing :class:`SQLKVStore` (one row per key)."""

    __tablename__ = "survey_kv_store"
    __table_args__ = {"extend_existing": True}

    key: str = Field(
        sa_column=Column(String(MAX_KEY_LENGTH), primary_key=True, nullable=False)
    )
    value: str = Field(sa_column=Column(Text, nullable=False))
    # UTC epoch seconds; NULL means "no expiry".
    expires_at: Optional[float] = Field(
        default=None, sa_column=Column(Float, nullable=True)
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
            time.sleep(base_delay * (2**attempt))
    raise last_exc


class SQLKVStore(KVStore):
    """SQLite-backed KV store with atomic write semantics.

    Supported URI scheme: ``sqlite`` only. Expiry is stored as a UTC epoch
    float, avoiding timezone-aware/naive datetime differences between
    SQLite and SQLAlchemy.
    """

    def __init__(self, database_uri: str):
        url = make_url(database_uri)
        if url.get_backend_name() != "sqlite":
            raise ValueError(
                "SQLKVStore supports SQLite URIs only, got backend "
                f"{url.get_backend_name()!r}"
            )
        self._uri = database_uri
        self._engine = _get_engine(database_uri)
        # Explicit create_all: the engine may already be cached from an
        # earlier construction (e.g. by SQLResultStorage) before this table
        # class was registered, in which case _get_engine will not create it.
        SQLModel.metadata.create_all(self._engine)

    def _session(self):
        from sqlmodel import Session

        return Session(self._engine)

    def set(self, key: str, value: Any, expire: Optional[float] = None) -> Any:
        """Insert or replace unconditionally (atomic upsert)."""
        key = _validate_key(key)
        encoded = _encode(value)
        deadline = _deadline(expire)

        def _op():
            stmt = sqlite_insert(KVEntry).values(
                key=key, value=encoded, expires_at=deadline
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[KVEntry.key],
                set_={"value": encoded, "expires_at": deadline},
            )
            with self._session() as session:
                session.execute(stmt)
                session.commit()
            return True

        return _retry_locked(_op)

    def add(self, key: str, value: Any, expire: Optional[float] = None) -> bool:
        """Insert only if absent or expired; atomic via a single statement.

        ``INSERT ... ON CONFLICT(key) DO UPDATE ... WHERE expires_at <= now``
        returns a row only when the insert succeeded or an expired row was
        replaced. A live existing row fails the WHERE clause, so no row is
        returned and the caller sees False.
        """
        key = _validate_key(key)
        encoded = _encode(value)
        deadline = _deadline(expire)
        now = time.time()

        def _op():
            stmt = sqlite_insert(KVEntry).values(
                key=key, value=encoded, expires_at=deadline
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[KVEntry.key],
                set_={"value": encoded, "expires_at": deadline},
                where=and_(
                    KVEntry.expires_at.isnot(None), KVEntry.expires_at <= now
                ),
            ).returning(KVEntry.key)
            with self._session() as session:
                row = session.execute(stmt).first()
                session.commit()
            return row is not None

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
                return result.rowcount > 0

        return _retry_locked(_op)

    def close(self) -> None:
        """No-op: sessions are operation-scoped and the engine is shared."""


def get_kv_store(
    backend: str, path_or_uri: str, timeout: Optional[float] = None
) -> KVStore:
    """Construct a KV store implementation.

    :param backend: exactly ``diskcache`` or ``sqlite``.
    :param path_or_uri: filesystem path (diskcache) or SQLAlchemy SQLite URI.
        Required — there is no implicit cwd-relative default.
    :param timeout: diskcache lock timeout (diskcache backend only).
    """
    if not path_or_uri:
        raise ValueError("path_or_uri is required")
    backend_name = (backend or "").strip().lower()
    if backend_name == "diskcache":
        return DiskCacheStore(path_or_uri, timeout=timeout)
    if backend_name == "sqlite":
        return SQLKVStore(path_or_uri)
    raise ValueError(
        f"unknown backend {backend_name!r}; expected 'diskcache' or 'sqlite'"
    )
