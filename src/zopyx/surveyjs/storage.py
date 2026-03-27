"""Storage backends for SurveyJS form submissions.

This module provides a small abstraction for persisting survey results either
in ZODB annotations (default/legacy behavior) or in an SQL database via
SQLModel. The active backend is selected from Plone registry settings.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import orjson
from BTrees.OOBTree import OOBTree
from sqlmodel import Field, SQLModel, Session, create_engine, select
from sqlalchemy import Column, Text
from sqlalchemy.engine import make_url
from zope.annotation.interfaces import IAnnotations
from zope.component import getUtility
from zope.component.hooks import getSite
from plone.registry.interfaces import IRegistry

from .constants import RESULTS_KEY
from .interfaces import IFormsSettings
from .utils import ensure_timezone_aware

_ENGINE_CACHE: Dict[str, object] = {}

# Module logger
logger = logging.getLogger(__name__)


def _normalize_datetime(value: object) -> datetime:
    """Return a timezone-aware datetime from a datetime or ISO string.

    Invalid or missing values fall back to the current UTC time.
    """
    if isinstance(value, datetime):
        return ensure_timezone_aware(value)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return ensure_timezone_aware(datetime.fromisoformat(text))
        except ValueError:
            return ensure_timezone_aware(datetime.now(timezone.utc))
    return ensure_timezone_aware(datetime.now(timezone.utc))


def _survey_storage_key(context) -> str:
    """Build a stable survey identifier for the given content context."""
    uid = getattr(context, "UID", None)
    if callable(uid):
        uid_value = uid()
        if uid_value:
            return uid_value
    try:
        return "/".join(context.getPhysicalPath())
    except Exception:
        return repr(context)


def _get_site_id(context) -> str:
    """Resolve the current Plone site id for multi-site result isolation."""
    try:
        site = getSite()
        if site is not None:
            return site.getId()
    except Exception:
        pass
    try:
        site = context.getSite()
        if site is not None:
            return site.getId()
    except Exception:
        pass
    try:
        return context.getId()
    except Exception:
        return ""


def _get_database_uri() -> str:
    """Read the configured database URI from the Plone registry."""
    try:
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        database_uri = getattr(settings, "database_uri", None)
        if database_uri:
            return database_uri.strip()
        return "sqlite:///var/surveyjs-results.db"
    except Exception:
        return "sqlite:///var/surveyjs-results.db"


def _get_backend_name() -> str:
    """Return the configured storage backend name."""
    try:
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        backend = getattr(settings, "result_storage_backend", None) or "zodb"
        return backend.strip().lower()
    except Exception:
        return "zodb"


def _get_storage_location() -> str:
    """Return a human-readable storage location for diagnostics/UI use."""
    backend = _get_backend_name()
    if backend == "rdbms":
        return _get_database_uri()
    return "zodb"


def _sqlite_path_to_uri(sqlite_path: str) -> str:
    """Convert a filesystem SQLite path into a SQLAlchemy SQLite URI."""
    sqlite_path = sqlite_path.strip()
    if sqlite_path in (":memory:", "file::memory:?cache=shared"):
        return "sqlite:///" + sqlite_path
    expanded = os.path.expanduser(sqlite_path)
    if os.path.isabs(expanded):
        return f"sqlite:////{expanded.lstrip('/')}"
    return f"sqlite:///{expanded}"


def _get_engine(db_uri: str):
    """Get or create a cached SQLModel engine for the configured database."""
    db_uri = db_uri.strip()
    if db_uri in _ENGINE_CACHE:
        return _ENGINE_CACHE[db_uri]

    url = make_url(db_uri)
    connect_args = {}
    if url.get_backend_name() == "sqlite":
        if url.database and url.database not in (":memory:", ""):
            db_path = os.path.expanduser(url.database)
            if not os.path.isabs(db_path):
                db_path = os.path.abspath(db_path)
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False}

    engine = create_engine(db_uri, connect_args=connect_args)
    SQLModel.metadata.create_all(engine)
    if url.get_backend_name() == "sqlite":
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL;")
            connection.exec_driver_sql("PRAGMA busy_timeout=5000;")
    _ENGINE_CACHE[db_uri] = engine
    return engine


class ResultStorage:
    """Abstract interface for survey result persistence backends."""

    def store_result(self, context, form_data: dict) -> str:
        """Store a single result entry and return its poll id."""
        raise NotImplementedError

    def get_result(self, context, poll_id: str) -> Optional[dict]:
        """Return one stored result for this context, or ``None``."""
        raise NotImplementedError

    def list_results(self, context) -> List[dict]:
        """Return all results for this context, newest first."""
        raise NotImplementedError

    def delete_results(self, context, poll_ids: Iterable[str]) -> Dict[str, List[str]]:
        """Delete selected results and report deleted/missing ids."""
        raise NotImplementedError

    def clear_results(self, context) -> None:
        """Delete all results for the given context."""
        raise NotImplementedError

    def count_results(self, context) -> int:
        """Return the number of stored results for the given context."""
        raise NotImplementedError


class ZODBResultStorage(ResultStorage):
    """Store survey results in a ZODB annotation tree on the survey object."""

    def _results_tree(self, context):
        """Return the annotation mapping used to store result entries."""
        annos = IAnnotations(context)
        annos.setdefault(RESULTS_KEY, OOBTree())
        return annos[RESULTS_KEY]

    def store_result(self, context, form_data: dict) -> str:
        """Persist one result entry in the annotation tree for this context."""
        results = self._results_tree(context)
        poll_id = form_data.get("poll_id") or str(uuid.uuid1())
        created = _normalize_datetime(form_data.get("created"))
        entry = dict(
            form_data, poll_id=poll_id, created=created, site_id=_get_site_id(context)
        )
        results[poll_id] = entry
        return poll_id

    def get_result(self, context, poll_id: str) -> Optional[dict]:
        """Fetch one stored annotation entry by poll id."""
        results = self._results_tree(context)
        return results.get(poll_id)

    def list_results(self, context) -> List[dict]:
        """List all annotation-backed results sorted by creation time."""
        results = list(self._results_tree(context).values())
        return sorted(
            results, key=lambda x: ensure_timezone_aware(x["created"]), reverse=True
        )

    def delete_results(self, context, poll_ids: Iterable[str]) -> Dict[str, List[str]]:
        """Delete selected annotation entries and return deletion status."""
        results = self._results_tree(context)
        deleted: List[str] = []
        missing: List[str] = []
        for pid in poll_ids:
            if pid in results:
                del results[pid]
                deleted.append(pid)
            else:
                missing.append(pid)
        return {"deleted": deleted, "missing": missing}

    def clear_results(self, context) -> None:
        """Replace the annotation result tree with a new empty tree."""
        annos = IAnnotations(context)
        annos[RESULTS_KEY] = OOBTree()

    def count_results(self, context) -> int:
        """Count annotation-backed results stored for this context."""
        return len(self._results_tree(context))


class SurveyResult(SQLModel, table=True):
    """SQLModel table storing normalized metadata and the original JSON entry."""

    __tablename__ = "survey_results"
    __table_args__ = {'extend_existing': True}

    poll_id: str = Field(primary_key=True)
    site_id: str = Field(index=True)
    survey_id: str = Field(index=True)
    created: datetime = Field(index=True)
    payload_size: int = Field(default=0)
    entry_json: str = Field(sa_column=Column(Text, nullable=False))


class SQLResultStorage(ResultStorage):
    """Store survey results in an SQL database using SQLModel."""

    def __init__(self, database_uri: str):
        """Initialize a storage backend for the given database URI."""
        self._database_uri = database_uri
        self._engine = _get_engine(database_uri)

    def _session(self) -> Session:
        """Create a new SQLModel session for the configured engine."""
        return Session(self._engine)

    def store_result(self, context, form_data: dict) -> str:
        """Insert or update one SQL-backed result entry for this context."""
        poll_id = form_data.get("poll_id") or str(uuid.uuid1())
        created = _normalize_datetime(form_data.get("created"))
        site_id = _get_site_id(context)
        entry = dict(form_data, poll_id=poll_id, created=created, site_id=site_id)
        survey_id = _survey_storage_key(context)
        payload_bytes = orjson.dumps(entry.get("result") or {})
        entry_payload = dict(entry)
        entry_payload["created"] = created.isoformat()
        entry_json = orjson.dumps(entry_payload).decode("utf-8")

        with self._session() as session:
            existing = session.get(SurveyResult, poll_id)
            if existing:
                existing.site_id = site_id
                existing.survey_id = survey_id
                existing.created = created
                existing.payload_size = len(payload_bytes)
                existing.entry_json = entry_json
            else:
                session.add(
                    SurveyResult(
                        poll_id=poll_id,
                        site_id=site_id,
                        survey_id=survey_id,
                        created=created,
                        payload_size=len(payload_bytes),
                        entry_json=entry_json,
                    )
                )
            session.commit()
        return poll_id

    def get_result(self, context, poll_id: str) -> Optional[dict]:
        """Fetch one SQL-backed result scoped to the current site and survey."""
        site_id = _get_site_id(context)
        survey_id = _survey_storage_key(context)
        with self._session() as session:
            row = session.get(SurveyResult, poll_id)
            if not row or row.survey_id != survey_id or row.site_id != site_id:
                return None
            return self._row_to_entry(row)

    def list_results(self, context) -> List[dict]:
        """List SQL-backed results for this context ordered by newest first."""
        site_id = _get_site_id(context)
        survey_id = _survey_storage_key(context)
        with self._session() as session:
            stmt = (
                select(SurveyResult)
                .where(
                    SurveyResult.survey_id == survey_id,
                    SurveyResult.site_id == site_id,
                )
                .order_by(SurveyResult.created.desc())
            )
            rows = session.exec(stmt).all()
        return [self._row_to_entry(row) for row in rows]

    def delete_results(self, context, poll_ids: Iterable[str]) -> Dict[str, List[str]]:
        """Delete SQL-backed results for this context and report outcomes."""
        site_id = _get_site_id(context)
        survey_id = _survey_storage_key(context)
        deleted: List[str] = []
        missing: List[str] = []
        with self._session() as session:
            for pid in poll_ids:
                row = session.get(SurveyResult, pid)
                if row and row.survey_id == survey_id and row.site_id == site_id:
                    session.delete(row)
                    deleted.append(pid)
                else:
                    missing.append(pid)
            session.commit()
        return {"deleted": deleted, "missing": missing}

    def clear_results(self, context) -> None:
        """Delete all SQL-backed results belonging to this context."""
        site_id = _get_site_id(context)
        survey_id = _survey_storage_key(context)
        with self._session() as session:
            stmt = select(SurveyResult).where(
                SurveyResult.survey_id == survey_id,
                SurveyResult.site_id == site_id,
            )
            rows = session.exec(stmt).all()
            for row in rows:
                session.delete(row)
            session.commit()

    def count_results(self, context) -> int:
        """Count SQL-backed results belonging to this context."""
        site_id = _get_site_id(context)
        survey_id = _survey_storage_key(context)
        with self._session() as session:
            stmt = select(SurveyResult).where(
                SurveyResult.survey_id == survey_id,
                SurveyResult.site_id == site_id,
            )
            rows = session.exec(stmt).all()
        return len(rows)

    def _row_to_entry(self, row: SurveyResult) -> dict:
        """Convert a database row back into the expected result entry dict."""
        try:
            entry = orjson.loads(row.entry_json)
        except orjson.JSONDecodeError:
            entry = {}
        entry["poll_id"] = row.poll_id
        entry["site_id"] = row.site_id
        entry["created"] = ensure_timezone_aware(row.created)
        return entry


def get_result_storage(context) -> ResultStorage:
    """Return the configured result storage backend instance."""
    backend = _get_backend_name()
    if backend == "rdbms":
        return SQLResultStorage(_get_database_uri())
    return ZODBResultStorage()


class SQLiteResultStorage(SQLResultStorage):
    """Backward-compatible alias for the SQLModel storage backend."""

    pass


# ============================================================================
# SQL TOKEN STORAGE
# ============================================================================

from sqlalchemy import func, delete
from sqlalchemy.orm import declared_attr
from zope.interface import implementer
from .interfaces import ITokenStore
from .constants import TOKEN_STORE_KEY
import secrets


class SurveyToken(SQLModel, table=True):
    """SQL table for survey access tokens with full audit trail."""
    
    __tablename__ = "survey_tokens"
    __table_args__ = {'extend_existing': True}
    
    # Primary key: the token itself
    token: str = Field(primary_key=True, max_length=32)
    
    # Scoping fields (composite index)
    site_id: str = Field(index=True, max_length=64)
    survey_id: str = Field(index=True, max_length=256)
    
    # Token state
    created: datetime = Field(index=True)
    used: Optional[datetime] = Field(default=None, index=True)
    
    # Optional: track usage context
    used_by: Optional[str] = Field(default=None, max_length=64)  # username
    used_from: Optional[str] = Field(default=None, max_length=45)  # IP address
    
    # Optional: token metadata
    batch_id: Optional[str] = Field(default=None, index=True, max_length=8)  # generation batch


@implementer(ITokenStore)
class SQLTokenStore:
    """SQL-backed token store adapter.
    
    Mirrors the ZODB TokenStore interface while providing
    SQL persistence and query capabilities.
    """
    
    def __init__(self, survey, database_uri: Optional[str] = None):
        """Initialize the SQL token store adapter.
        
        :param survey: The survey object being adapted
        :param database_uri: Optional database URI override
        """
        self.survey = survey
        self._site_id = _get_site_id(survey)
        self._survey_id = _survey_storage_key(survey)
        self._database_uri = database_uri or _get_database_uri()
        self._engine = _get_engine(self._database_uri)
        self._backend = "SQL"
        logger.debug("[SQLTokenStore:%s] Initialized for survey %s, DB: %s", 
                    self._backend, self._survey_id, self._database_uri[:50])
    
    def _session(self) -> Session:
        """Create SQLModel session."""
        return Session(self._engine)
    
    def _row_to_dict(self, row: SurveyToken) -> dict:
        """Convert database row to token info dict."""
        return {
            "token": row.token,
            "created": row.created.isoformat() if row.created else None,
            "used": row.used.isoformat() if row.used else None,
        }
    
    def generate_tokens(self, number: int) -> list:
        """Generate a specified number of new tokens.
        
        :param number: Number of tokens to generate
        :return: List of generated token strings (32-char URL-safe)
        """
        batch_id = secrets.token_hex(4)  # 8 chars
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
        logger.info("[SQLTokenStore:%s] Generated %d tokens (batch: %s) for survey %s", 
                    self._backend, number, batch_id, self._survey_id)
        return generated
    
    def has_token(self, token: str) -> bool:
        """Check if a token exists and is valid (not used).
        
        :param token: Token string to check
        :return: True if token exists and is unused, False otherwise
        """
        with self._session() as session:
            row = session.get(SurveyToken, token)
            if row is None:
                logger.debug("[SQLTokenStore:%s] Token not found: %s...", self._backend, token[:8])
                return False
            if row.site_id != self._site_id or row.survey_id != self._survey_id:
                logger.debug("[SQLTokenStore:%s] Token scope mismatch: %s...", self._backend, token[:8])
                return False
            is_valid = row.used is None
            logger.debug("[SQLTokenStore:%s] Token check: %s... valid=%s", 
                        self._backend, token[:8], is_valid)
            return is_valid
    
    def invalidate(self, token: str) -> bool:
        """Invalidate a token (mark as used).
        
        :param token: Token string to invalidate
        :return: True if token was found and invalidated, False otherwise
        """
        with self._session() as session:
            row = session.get(SurveyToken, token)
            if not row or row.survey_id != self._survey_id:
                logger.warning("[SQLTokenStore:%s] Invalidate failed - token not found: %s...", 
                              self._backend, token[:8])
                return False
            
            row.used = datetime.now(timezone.utc)
            session.commit()
            logger.info("[SQLTokenStore:%s] Token invalidated: %s...", self._backend, token[:8])
            return True
    
    def get_token_info(self, token: str) -> Optional[dict]:
        """Get information about a specific token.
        
        :param token: Token string to look up
        :return: Token info dict with keys: token, created, used (or None if not found)
        """
        with self._session() as session:
            row = session.get(SurveyToken, token)
            if not row or row.survey_id != self._survey_id:
                return None
            return self._row_to_dict(row)
    
    def list_tokens(self) -> list:
        """List all tokens and their information.
        
        :return: List of token info dicts
        """
        with self._session() as session:
            stmt = select(SurveyToken).where(
                SurveyToken.site_id == self._site_id,
                SurveyToken.survey_id == self._survey_id,
            )
            rows = session.exec(stmt).all()
            return [self._row_to_dict(row) for row in rows]
    
    def get_stats(self) -> dict:
        """Get token statistics.
        
        :return: Dict with total, used, and unused token counts
        """
        with self._session() as session:
            # Single query for all stats using SQL aggregation
            from sqlalchemy import text
            stmt = text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN used IS NULL THEN 1 END) as unused,
                    COUNT(CASE WHEN used IS NOT NULL THEN 1 END) as used
                FROM survey_tokens
                WHERE site_id = :site_id AND survey_id = :survey_id
            """)
            result = session.exec(
                stmt,
                params={"site_id": self._site_id, "survey_id": self._survey_id}
            ).first()
            
            return {
                "total": result.total,
                "used": result.used,
                "unused": result.unused,
            }
    
    def clear(self) -> None:
        """Clear all tokens from the store."""
        with self._session() as session:
            stmt = delete(SurveyToken).where(
                SurveyToken.site_id == self._site_id,
                SurveyToken.survey_id == self._survey_id,
            )
            session.exec(stmt)
            session.commit()


# ============================================================================
# TOKEN STORAGE FACTORY
# ============================================================================

def _get_token_backend_name() -> str:
    """Return the configured token storage backend name."""
    try:
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        backend = getattr(settings, "token_storage_backend", None) or "zodb"
        result = backend.strip().lower()
        logger.debug("Token storage backend from registry: %s", result)
        return result
    except Exception as e:
        logger.warning("Failed to get token storage backend from registry: %s", e)
        return "zodb"


def _get_survey_path(survey) -> str:
    """Get physical path of survey for logging."""
    try:
        return "/".join(survey.getPhysicalPath())
    except Exception:
        return str(survey)


def get_token_storage(survey) -> ITokenStore:
    """Return the configured token storage backend instance.
    
    :param survey: The survey object
    :return: ITokenStore implementation
    """
    backend = _get_token_backend_name()
    survey_path = _get_survey_path(survey)
    
    logger.info("get_token_storage called for survey %s, backend=%s", survey_path, backend)
    
    if backend == "rdbms":
        logger.info("Using SQLTokenStore for survey %s", survey_path)
        return SQLTokenStore(survey)
    
    # Import here to avoid circular imports
    from .adapters.token_store import TokenStore
    return TokenStore(survey)
