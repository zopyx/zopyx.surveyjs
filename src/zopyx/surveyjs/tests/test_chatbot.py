from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from zopyx.surveyjs.chatbot.engine import ChatContext, ChatEngine
from zopyx.surveyjs.chatbot.indexer import DocumentationIndexer
from zopyx.surveyjs.chatbot.vector_store import ChatDocumentStore


class ChatbotIndexerTests(unittest.TestCase):
    def test_index_project_docs_collects_chunks(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "README.md").write_text("# Hello\nThis is docs.", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "usage.rst").write_text(
                "Usage\n=====\nConfigure SurveyJS add-on.", encoding="utf-8"
            )
            (root / "src" / "zopyx" / "surveyjs").mkdir(parents=True)
            (root / "src" / "zopyx" / "surveyjs" / "views.py").write_text(
                "def helper():\n    return 'ok'\n", encoding="utf-8"
            )

            store = ChatDocumentStore(str(root / "var" / "chatbot"))
            indexer = DocumentationIndexer(store)
            result = indexer.index_project_docs(project_root=root)

            self.assertGreater(result["indexed_documents"], 0)
            stats = store.stats()
            self.assertGreater(stats["document_count"], 0)
            self.assertGreater(stats["local_chunk_count"], 0)

    def test_index_remote_docs_uses_allowlist(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = ChatDocumentStore(str(root / "var" / "chatbot"))
            indexer = DocumentationIndexer(store)

            with patch.object(
                DocumentationIndexer,
                "fetch_remote_text",
                return_value="SurveyJS docs content about question types and logic.",
            ):
                result = indexer.index_remote_docs(
                    urls=["https://surveyjs.io/form-library/documentation/overview"]
                )

            self.assertEqual(result["urls_indexed"], 1)
            stats = store.stats()
            self.assertGreater(stats["remote_chunk_count"], 0)


class ChatbotEngineTests(unittest.TestCase):
    def _store_with_docs(self) -> ChatDocumentStore:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = ChatDocumentStore(str(Path(tmp.name) / "chatbot"))
        store.set_documents(
            documents=[
                {
                    "content": "Use @@results to inspect submissions and export data.",
                    "metadata": {
                        "source": "README.md",
                        "source_type": "project_docs",
                        "title": "README",
                        "chunk_index": 0,
                        "total_chunks": 1,
                    },
                },
                {
                    "content": "SurveyJS supports conditional logic with visibleIf expressions.",
                    "metadata": {
                        "source": "https://surveyjs.io/form-library/documentation/overview",
                        "source_type": "surveyjs_docs",
                        "title": "SurveyJS Docs",
                        "chunk_index": 0,
                        "total_chunks": 1,
                    },
                },
            ],
            sources=[
                "README.md",
                "https://surveyjs.io/form-library/documentation/overview",
            ],
        )
        return store

    def test_chat_returns_sources_confidence_and_followups(self) -> None:
        store = self._store_with_docs()
        engine = ChatEngine(store, model_name="gpt-test", api_key=None, ollama_url=None)
        context = ChatContext(
            current_view="@@chatbot", survey_title="T", user_role="Editor"
        )

        with patch.object(
            ChatEngine, "_generate_response", return_value="Use @@results."
        ):
            result = engine.chat("How do I view results?", context=context, top_k=4)

        self.assertIn("response", result)
        self.assertTrue(result["sources"])
        self.assertIn(result["confidence"], {"low", "medium", "high"})
        self.assertEqual(len(result["followups"]), 3)

    def test_stream_chat_emits_done_event(self) -> None:
        store = self._store_with_docs()
        engine = ChatEngine(store, model_name="gpt-test", api_key=None, ollama_url=None)
        context = ChatContext()

        with patch.object(ChatEngine, "_generate_response", return_value="A" * 330):
            events = list(engine.stream_chat("question", context=context, top_k=2))

        self.assertTrue(events)
        self.assertTrue(events[-1].get("done"))
        self.assertIn("response", events[-1])


if __name__ == "__main__":
    unittest.main()
