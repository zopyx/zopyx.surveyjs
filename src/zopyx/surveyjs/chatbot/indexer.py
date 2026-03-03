"""Documentation indexing for local project files and remote SurveyJS pages."""

from __future__ import annotations

import html
import logging
import re
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from .vector_store import ChatDocumentStore

logger = logging.getLogger(__name__)


DEFAULT_SURVEYJS_URLS = [
    "https://surveyjs.io/form-library/documentation/overview",
    "https://surveyjs.io/survey-creator/documentation/overview",
    "https://surveyjs.io/form-library/documentation/design-survey/create-a-simple-survey",
    "https://surveyjs.io/form-library/documentation/design-survey/question-types",
    "https://surveyjs.io/form-library/documentation/design-survey/conditional-logic",
    "https://surveyjs.io/form-library/documentation/design-survey/validate-input",
]


def _strip_html(raw: str) -> str:
    cleaned = re.sub(
        r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", " ", raw, flags=re.I
    )
    cleaned = re.sub(
        r"<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>", " ", cleaned, flags=re.I
    )
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 220) -> list[str]:
    if not text:
        return []
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        boundary = text.rfind(". ", start, end)
        if boundary <= start + int(chunk_size * 0.5):
            boundary = text.rfind(" ", start, end)
        if boundary > start:
            end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


class DocumentationIndexer:
    """Indexes project and SurveyJS docs into the store."""

    def __init__(self, store: ChatDocumentStore):
        self.store = store

    def _detect_project_root(self) -> Path:
        start = Path(__file__).resolve()
        for parent in start.parents:
            if (parent / "buildout.cfg").exists() and (parent / "src").exists():
                return parent
        return Path.cwd()

    def _local_doc_files(self, project_root: Path) -> list[Path]:
        candidates = [
            project_root / "README.md",
            project_root / "DEVELOP.rst",
            project_root / "AI.md",
            project_root / "EMBEDDING.md",
            project_root / "chatbot.md",
            project_root / "chatbot2.md",
        ]
        files = [p for p in candidates if p.exists()]

        docs_dir = project_root / "docs"
        if docs_dir.exists():
            files.extend(sorted(docs_dir.rglob("*.md")))
            files.extend(sorted(docs_dir.rglob("*.rst")))

        src_dir = project_root / "src" / "zopyx" / "surveyjs"
        if src_dir.exists():
            for path in sorted(src_dir.rglob("*.py")):
                if "/tests/" in str(path).replace("\\", "/"):
                    continue
                if "/static/" in str(path).replace("\\", "/"):
                    continue
                files.append(path)

        deduped = []
        seen = set()
        for path in files:
            key = str(path.resolve())
            if key in seen:
                continue
            deduped.append(path)
            seen.add(key)
        return deduped

    def _build_documents(self, texts: list[dict], source_type: str) -> list[dict]:
        documents = []
        for item in texts:
            source = item["source"]
            title = item.get("title") or Path(source).name
            chunks = _chunk_text(item.get("content", ""))
            total = len(chunks)
            for index, chunk in enumerate(chunks):
                documents.append(
                    {
                        "content": chunk,
                        "metadata": {
                            "source": source,
                            "source_type": source_type,
                            "title": title,
                            "chunk_index": index,
                            "total_chunks": total,
                        },
                    }
                )
        return documents

    def index_project_docs(self, project_root: Path | None = None) -> dict:
        root = project_root or self._detect_project_root()
        files = self._local_doc_files(root)
        texts = []
        for path in files:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if not content.strip():
                continue
            try:
                source = str(path.relative_to(root))
            except ValueError:
                source = str(path)
            title = path.stem
            first_line = next(
                (line.strip() for line in content.splitlines() if line.strip()), ""
            )
            if first_line.startswith("#"):
                title = first_line.lstrip("# ").strip() or title
            texts.append({"source": source, "title": title, "content": content})

        documents = self._build_documents(texts, "project_docs")
        existing = self.store.load()
        remote_docs = [
            d
            for d in existing.get("documents", [])
            if d.get("metadata", {}).get("source_type") == "surveyjs_docs"
        ]
        final_docs = documents + remote_docs
        sources = [d.get("metadata", {}).get("source") for d in final_docs]
        payload = self.store.set_documents(final_docs, [s for s in sources if s])
        return {
            "indexed_documents": len(documents),
            "total_documents": len(payload.get("documents", [])),
            "project_root": str(root),
            "files_indexed": len(texts),
        }

    def fetch_remote_text(self, url: str, timeout: int = 20) -> str:
        req = Request(url, headers={"User-Agent": "zopyx.surveyjs-chatbot/1.0"})
        with urlopen(req, timeout=timeout) as response:
            data = response.read().decode("utf-8", errors="ignore")
        return _strip_html(data)

    def index_remote_docs(self, urls: list[str] | None = None) -> dict:
        selected_urls = urls or DEFAULT_SURVEYJS_URLS
        texts = []
        failures = []
        for url in selected_urls:
            try:
                content = self.fetch_remote_text(url)
                if not content:
                    continue
                texts.append({"source": url, "title": url, "content": content})
            except URLError as exc:
                failures.append({"url": url, "error": str(exc)})
            except Exception as exc:
                failures.append({"url": url, "error": str(exc)})

        documents = self._build_documents(texts, "surveyjs_docs")
        existing = self.store.load()
        local_docs = [
            d
            for d in existing.get("documents", [])
            if d.get("metadata", {}).get("source_type") == "project_docs"
        ]
        final_docs = local_docs + documents
        sources = [d.get("metadata", {}).get("source") for d in final_docs]
        payload = self.store.set_documents(final_docs, [s for s in sources if s])
        result = {
            "indexed_documents": len(documents),
            "total_documents": len(payload.get("documents", [])),
            "urls_indexed": len(texts),
            "failures": failures,
        }
        if failures:
            logger.warning("Chatbot remote indexing failures: %s", failures)
        return result
