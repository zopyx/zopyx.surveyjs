"""RAG chat engine for zopyx.surveyjs chatbot."""

from __future__ import annotations

from dataclasses import dataclass, field

from .retriever import Retriever
from .vector_store import ChatDocumentStore


@dataclass
class ChatContext:
    current_view: str | None = None
    survey_title: str | None = None
    survey_json: dict | None = None
    user_role: str | None = None
    history: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        lines = []
        if self.current_view:
            lines.append(f"Current view: {self.current_view}")
        if self.survey_title:
            lines.append(f"Survey title: {self.survey_title}")
        if self.user_role:
            lines.append(f"User role: {self.user_role}")
        if self.survey_json and isinstance(self.survey_json, dict):
            pages = self.survey_json.get("pages")
            if isinstance(pages, list):
                q_count = 0
                for page in pages:
                    elements = (
                        (page or {}).get("elements", [])
                        if isinstance(page, dict)
                        else []
                    )
                    if isinstance(elements, list):
                        q_count += len(elements)
                lines.append(
                    f"Current form has {len(pages)} pages and about {q_count} elements"
                )
        if not lines:
            return "No additional context provided"
        return "\n".join(lines)


class ChatEngine:
    def __init__(
        self,
        store: ChatDocumentStore,
        settings: dict,
    ):
        self.store = store
        self.settings = settings

    def _confidence(self, retrieved: list[dict]) -> str:
        if not retrieved:
            return "low"
        top = float(retrieved[0].get("score", 0.0))
        if top >= 1.2:
            return "high"
        if top >= 0.5:
            return "medium"
        return "low"

    def _build_prompt(
        self, message: str, context: ChatContext, retrieved: list[dict]
    ) -> str:
        chunks = []
        for item in retrieved:
            source = item.get("metadata", {}).get("source", "unknown")
            excerpt = (item.get("content") or "")[:900]
            chunks.append(f"Source: {source}\n{excerpt}")

        history_lines = []
        for item in (context.history or [])[-6:]:
            role = item.get("role", "user")
            content = item.get("content", "")
            if not content:
                continue
            history_lines.append(f"{role}: {content}")

        docs_block = (
            "\n\n".join(chunks) if chunks else "No relevant documentation chunks found."
        )
        history_block = (
            "\n".join(history_lines)
            if history_lines
            else "No prior conversation history."
        )

        return (
            "You are the zopyx.surveyjs assistant.\n"
            "Answer questions about this add-on, configuration, usage, and SurveyJS docs.\n"
            "Rules:\n"
            "- Ground answers in the provided documentation context.\n"
            "- If uncertain, explicitly say what is uncertain.\n"
            "- Do not invent endpoint names, settings, or behaviors.\n"
            "- Be concise and practical.\n"
            "- End with a short 'Sources:' line listing source names.\n\n"
            f"Context:\n{context.summary()}\n\n"
            f"Relevant Documentation:\n{docs_block}\n\n"
            f"Conversation History:\n{history_block}\n\n"
            f"User Question:\n{message}\n"
        )

    def _generate_response(self, prompt: str) -> str:
        try:
            from zopyx.surveyjs.browser.services.ai import build_llm_model
        except ImportError:
            raise ImportError(
                "The 'zopyx.surveyjs' service helpers are not available."
            )
        model = build_llm_model(self.settings)
        response = model.prompt(prompt)
        text = response.text() if callable(response.text) else response.text
        return text or ""

    def chat(self, message: str, context: ChatContext, top_k: int = 6) -> dict:
        payload = self.store.load()
        documents = payload.get("documents", [])
        retriever = Retriever(documents)
        retrieved = retriever.retrieve(message, top_k=top_k)

        prompt = self._build_prompt(message, context, retrieved)
        answer = self._generate_response(prompt)

        sources = []
        seen = set()
        for item in retrieved:
            meta = item.get("metadata", {})
            source = meta.get("source")
            if not source or source in seen:
                continue
            seen.add(source)
            sources.append(
                {
                    "source": source,
                    "source_type": meta.get("source_type"),
                    "title": meta.get("title"),
                    "score": item.get("score"),
                }
            )

        followups = self.suggest_followups(message, sources)
        return {
            "response": answer,
            "sources": sources,
            "confidence": self._confidence(retrieved),
            "followups": followups,
            "context_used": {
                "docs_retrieved": len(retrieved),
                "view": context.current_view,
            },
        }

    def stream_chat(self, message: str, context: ChatContext, top_k: int = 6):
        result = self.chat(message, context=context, top_k=top_k)
        text = result.get("response", "")
        chunk_size = 160
        for idx in range(0, len(text), chunk_size):
            yield {"chunk": text[idx : idx + chunk_size]}
        yield {
            "done": True,
            "response": text,
            "sources": result.get("sources", []),
            "confidence": result.get("confidence", "low"),
            "followups": result.get("followups", []),
            "context_used": result.get("context_used", {}),
        }

    def suggest_followups(self, message: str, sources: list[dict]) -> list[str]:
        source_types = {item.get("source_type") for item in sources}
        base = [
            "Which view should I use for editing, viewing, and results?",
            "Which settings are global in Site Setup > Forms?",
        ]
        if "surveyjs_docs" in source_types:
            base.append("Which SurveyJS feature is best for conditional logic?")
        else:
            base.append("How do I configure survey actions like mail, post, and store?")

        msg = (message or "").lower()
        if "validation" in msg:
            base[0] = "How do experimental and external server-side validation differ?"
        if "ai" in msg:
            base[1] = "How do I configure local Ollama versus hosted AI providers?"
        return base[:3]
