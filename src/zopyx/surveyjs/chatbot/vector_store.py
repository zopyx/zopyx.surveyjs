"""Persistent on-disk document store for chatbot retrieval."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import orjson


class ChatDocumentStore:
    """Simple JSON-backed store used by the chatbot retriever."""

    def __init__(self, persist_directory: str | None = None):
        if persist_directory:
            self.persist_directory = Path(persist_directory)
        else:
            self.persist_directory = self._default_persist_directory()
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.index_file = self.persist_directory / "index.json"

    def _default_persist_directory(self) -> Path:
        client_home = os.environ.get("CLIENT_HOME") or os.environ.get("INSTANCE_HOME")
        if client_home:
            return Path(client_home) / "surveyjs_chatbot"
        return Path("var") / "surveyjs_chatbot"

    def load(self) -> dict:
        if not self.index_file.exists():
            return {
                "version": 1,
                "updated": None,
                "documents": [],
                "sources": [],
            }
        try:
            raw = self.index_file.read_bytes()
            data = orjson.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Invalid index format")
            data.setdefault("documents", [])
            data.setdefault("sources", [])
            data.setdefault("updated", None)
            data.setdefault("version", 1)
            return data
        except Exception:
            return {
                "version": 1,
                "updated": None,
                "documents": [],
                "sources": [],
            }

    def save(self, payload: dict) -> None:
        payload = dict(payload)
        payload["updated"] = datetime.now(timezone.utc).isoformat()
        with NamedTemporaryFile(
            "wb", delete=False, dir=str(self.persist_directory)
        ) as tmp:
            tmp.write(orjson.dumps(payload))
            tmp_path = Path(tmp.name)
        tmp_path.replace(self.index_file)

    def set_documents(self, documents: list[dict], sources: list[str]) -> dict:
        payload = {
            "version": 1,
            "documents": documents,
            "sources": sorted(set(sources)),
        }
        self.save(payload)
        return payload

    def reset(self) -> None:
        if self.index_file.exists():
            self.index_file.unlink()

    def stats(self) -> dict:
        payload = self.load()
        docs = payload.get("documents", [])
        local_count = len(
            [
                d
                for d in docs
                if d.get("metadata", {}).get("source_type") == "project_docs"
            ]
        )
        remote_count = len(
            [
                d
                for d in docs
                if d.get("metadata", {}).get("source_type") == "surveyjs_docs"
            ]
        )
        return {
            "document_count": len(docs),
            "source_count": len(payload.get("sources", [])),
            "local_chunk_count": local_count,
            "remote_chunk_count": remote_count,
            "updated": payload.get("updated"),
            "persist_directory": str(self.persist_directory),
            "index_file": str(self.index_file),
        }
