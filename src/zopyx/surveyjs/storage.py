from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import orjson
from BTrees.OOBTree import OOBTree
from sqlmodel import Field, SQLModel, Session, create_engine, select
from sqlalchemy import Column, Text
from zope.annotation.interfaces import IAnnotations
from zope.component import getUtility
from plone.registry.interfaces import IRegistry

from .constants import RESULTS_KEY
from .interfaces import IFormsSettings
from .utils import ensure_timezone_aware

_ENGINE_CACHE: Dict[str, object] = {}


def _normalize_datetime(value: object) -> datetime:
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
    uid = getattr(context, "UID", None)
    if callable(uid):
        uid_value = uid()
        if uid_value:
            return uid_value
    try:
        return "/".join(context.getPhysicalPath())
    except Exception:
        return repr(context)


def _get_sqlite_path() -> str:
    try:
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        sqlite_path = getattr(settings, "sqlite_path", None) or "var/surveyjs-results.db"
        sqlite_path = sqlite_path.strip()
        return sqlite_path
    except Exception:
        return "var/surveyjs-results.db"


def _get_backend_name() -> str:
    try:
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        backend = getattr(settings, "result_storage_backend", None) or "zodb"
        return backend.strip().lower()
    except Exception:
        return "zodb"


def _get_sqlite_engine(db_path: str):
    db_path = os.path.expanduser(db_path)
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(db_path)
    if db_path in _ENGINE_CACHE:
        return _ENGINE_CACHE[db_path]

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL;")
        connection.exec_driver_sql("PRAGMA busy_timeout=5000;")
    _ENGINE_CACHE[db_path] = engine
    return engine


class ResultStorage:
    def store_result(self, context, form_data: dict) -> str:
        raise NotImplementedError

    def get_result(self, context, poll_id: str) -> Optional[dict]:
        raise NotImplementedError

    def list_results(self, context) -> List[dict]:
        raise NotImplementedError

    def delete_results(self, context, poll_ids: Iterable[str]) -> Dict[str, List[str]]:
        raise NotImplementedError

    def clear_results(self, context) -> None:
        raise NotImplementedError

    def count_results(self, context) -> int:
        raise NotImplementedError


class ZODBResultStorage(ResultStorage):
    def _results_tree(self, context):
        annos = IAnnotations(context)
        annos.setdefault(RESULTS_KEY, OOBTree())
        return annos[RESULTS_KEY]

    def store_result(self, context, form_data: dict) -> str:
        results = self._results_tree(context)
        poll_id = form_data.get("poll_id") or str(uuid.uuid1())
        created = _normalize_datetime(form_data.get("created"))
        entry = dict(form_data, poll_id=poll_id, created=created)
        results[poll_id] = entry
        return poll_id

    def get_result(self, context, poll_id: str) -> Optional[dict]:
        results = self._results_tree(context)
        return results.get(poll_id)

    def list_results(self, context) -> List[dict]:
        results = list(self._results_tree(context).values())
        return sorted(
            results, key=lambda x: ensure_timezone_aware(x["created"]), reverse=True
        )

    def delete_results(self, context, poll_ids: Iterable[str]) -> Dict[str, List[str]]:
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
        annos = IAnnotations(context)
        annos[RESULTS_KEY] = OOBTree()

    def count_results(self, context) -> int:
        return len(self._results_tree(context))


class SurveyResult(SQLModel, table=True):
    __tablename__ = "survey_results"

    poll_id: str = Field(primary_key=True)
    survey_id: str = Field(index=True)
    created: datetime = Field(index=True)
    payload_size: int = Field(default=0)
    entry_json: str = Field(sa_column=Column(Text, nullable=False))


class SQLiteResultStorage(ResultStorage):
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._engine = _get_sqlite_engine(db_path)

    def _session(self) -> Session:
        return Session(self._engine)

    def store_result(self, context, form_data: dict) -> str:
        poll_id = form_data.get("poll_id") or str(uuid.uuid1())
        created = _normalize_datetime(form_data.get("created"))
        entry = dict(form_data, poll_id=poll_id, created=created)
        survey_id = _survey_storage_key(context)
        payload_bytes = orjson.dumps(entry.get("result") or {})
        entry_payload = dict(entry)
        entry_payload["created"] = created.isoformat()
        entry_json = orjson.dumps(entry_payload).decode("utf-8")

        with self._session() as session:
            existing = session.get(SurveyResult, poll_id)
            if existing:
                existing.survey_id = survey_id
                existing.created = created
                existing.payload_size = len(payload_bytes)
                existing.entry_json = entry_json
            else:
                session.add(
                    SurveyResult(
                        poll_id=poll_id,
                        survey_id=survey_id,
                        created=created,
                        payload_size=len(payload_bytes),
                        entry_json=entry_json,
                    )
                )
            session.commit()
        return poll_id

    def get_result(self, context, poll_id: str) -> Optional[dict]:
        survey_id = _survey_storage_key(context)
        with self._session() as session:
            row = session.get(SurveyResult, poll_id)
            if not row or row.survey_id != survey_id:
                return None
            return self._row_to_entry(row)

    def list_results(self, context) -> List[dict]:
        survey_id = _survey_storage_key(context)
        with self._session() as session:
            stmt = (
                select(SurveyResult)
                .where(SurveyResult.survey_id == survey_id)
                .order_by(SurveyResult.created.desc())
            )
            rows = session.exec(stmt).all()
        return [self._row_to_entry(row) for row in rows]

    def delete_results(self, context, poll_ids: Iterable[str]) -> Dict[str, List[str]]:
        survey_id = _survey_storage_key(context)
        deleted: List[str] = []
        missing: List[str] = []
        with self._session() as session:
            for pid in poll_ids:
                row = session.get(SurveyResult, pid)
                if row and row.survey_id == survey_id:
                    session.delete(row)
                    deleted.append(pid)
                else:
                    missing.append(pid)
            session.commit()
        return {"deleted": deleted, "missing": missing}

    def clear_results(self, context) -> None:
        survey_id = _survey_storage_key(context)
        with self._session() as session:
            stmt = select(SurveyResult).where(SurveyResult.survey_id == survey_id)
            rows = session.exec(stmt).all()
            for row in rows:
                session.delete(row)
            session.commit()

    def count_results(self, context) -> int:
        survey_id = _survey_storage_key(context)
        with self._session() as session:
            stmt = select(SurveyResult).where(SurveyResult.survey_id == survey_id)
            rows = session.exec(stmt).all()
        return len(rows)

    def _row_to_entry(self, row: SurveyResult) -> dict:
        try:
            entry = orjson.loads(row.entry_json)
        except orjson.JSONDecodeError:
            entry = {}
        entry["poll_id"] = row.poll_id
        entry["created"] = row.created
        return entry


def get_result_storage(context) -> ResultStorage:
    backend = _get_backend_name()
    if backend == "sqlite":
        return SQLiteResultStorage(_get_sqlite_path())
    return ZODBResultStorage()
