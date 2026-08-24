from __future__ import annotations

import logging

import orjson
import plone.api
from AccessControl import Unauthorized

from ..chatbot.engine import ChatContext, ChatEngine
from ..chatbot.indexer import DEFAULT_SURVEYJS_URLS, DocumentationIndexer
from ..chatbot.vector_store import ChatDocumentStore
from .services import ai as ai_service
from .services.http import json_error, json_response, parse_json_body
from .views import Views

logger = logging.getLogger(__name__)


class SurveyChatbot(Views):
    """Dedicated chatbot views and API endpoints."""

    def _chatbot_enabled(self) -> bool:
        return self.feature_enabled("chatbot")

    def _store(self) -> ChatDocumentStore:
        return ChatDocumentStore()

    def _indexer(self) -> DocumentationIndexer:
        return DocumentationIndexer(self._store())

    def _engine(self) -> ChatEngine:
        return ChatEngine(
            store=self._store(),
            settings=ai_service.load_ai_settings(),
        )

    def _ensure_local_index(self) -> None:
        store = self._store()
        stats = store.stats()
        if stats.get("local_chunk_count", 0) > 0:
            return
        self._indexer().index_project_docs()

    def _request_payload(self) -> dict:
        payload = parse_json_body(self.request)
        if isinstance(payload, dict):
            return payload
        form = self.request.form
        if not form:
            return {}
        out = {}
        for key in (
            "message",
            "current_view",
            "survey_title",
            "user_role",
            "stream",
            "history",
            "survey_json",
            "top_k",
        ):
            if key in form:
                out[key] = form.get(key)
        return out

    def _coerce_json_field(self, value, default):
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="ignore")
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return default
            try:
                return orjson.loads(text)
            except orjson.JSONDecodeError:
                return default
        return default

    def _build_context(self, payload: dict) -> ChatContext:
        survey_json = self._coerce_json_field(payload.get("survey_json"), None)
        history = self._coerce_json_field(payload.get("history"), [])
        if not isinstance(history, list):
            history = []

        user_roles = plone.api.user.get_roles(obj=self.context)
        fallback_role = "Viewer"
        if "Manager" in user_roles:
            fallback_role = "Manager"
        elif "Editor" in user_roles:
            fallback_role = "Editor"

        return ChatContext(
            current_view=(payload.get("current_view") or "@@chatbot").strip(),
            survey_title=(
                payload.get("survey_title") or self.context.Title() or ""
            ).strip(),
            survey_json=survey_json if isinstance(survey_json, dict) else None,
            user_role=(payload.get("user_role") or fallback_role).strip(),
            history=history,
        )

    def chatbot_api(self):
        self._check_post_authenticator()
        if not self._chatbot_enabled():
            return json_error(
                self.request.response,
                403,
                "feature_disabled",
                "Chatbot feature is disabled.",
            )
        if not self.can_manage_portal_content:
            raise Unauthorized("Not allowed")

        payload = self._request_payload()
        message = (payload.get("message") or "").strip()
        if not message:
            return json_error(
                self.request.response,
                400,
                "missing_message",
                "Please provide a message.",
            )

        top_k_raw = payload.get("top_k", 6)
        try:
            top_k = int(top_k_raw)
        except (TypeError, ValueError):
            top_k = 6
        top_k = min(max(top_k, 1), 12)

        stream_flag = str(payload.get("stream", "")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        try:
            self._ensure_local_index()
            context = self._build_context(payload)
            engine = self._engine()
            if stream_flag:
                response = self.request.response
                response.setHeader("content-type", "text/event-stream")
                response.setHeader("cache-control", "no-cache")
                for event in engine.stream_chat(message, context=context, top_k=top_k):
                    line = b"data: " + orjson.dumps(event) + b"\n\n"
                    response.write(line)
                return

            result = engine.chat(message, context=context, top_k=top_k)
            return json_response(self.request.response, result, status=200)
        except Exception as exc:
            logger.exception("Chatbot API failed")
            return json_error(
                self.request.response,
                500,
                "chat_failed",
                str(exc),
            )

    def chatbot_api_stats(self):
        if not self._chatbot_enabled():
            return json_error(
                self.request.response,
                403,
                "feature_disabled",
                "Chatbot feature is disabled.",
            )
        if not self.can_manage_portal_content:
            raise Unauthorized("Not allowed")
        return json_response(self.request.response, self._store().stats(), status=200)

    def chatbot_mgmt(self):
        if not self._chatbot_enabled():
            return json_error(
                self.request.response,
                403,
                "feature_disabled",
                "Chatbot feature is disabled.",
            )
        if not self.is_manager:
            raise Unauthorized("Manager role required")
        data = {
            "endpoints": {
                "stats": f"{self.context.absolute_url()}/@@chatbot-stats",
                "index_local": f"{self.context.absolute_url()}/@@chatbot-index-local",
                "index_remote": f"{self.context.absolute_url()}/@@chatbot-index-remote",
                "reset": f"{self.context.absolute_url()}/@@chatbot-reset",
            },
            "surveyjs_allowlist": DEFAULT_SURVEYJS_URLS,
            "stats": self._store().stats(),
        }
        return json_response(self.request.response, data, status=200)

    def chatbot_index_local(self):
        self._check_post_authenticator()
        if not self._chatbot_enabled():
            return json_error(
                self.request.response,
                403,
                "feature_disabled",
                "Chatbot feature is disabled.",
            )
        if not self.is_manager:
            raise Unauthorized("Manager role required")
        result = self._indexer().index_project_docs()
        return json_response(self.request.response, result, status=200)

    def chatbot_index_remote(self):
        self._check_post_authenticator()
        if not self._chatbot_enabled():
            return json_error(
                self.request.response,
                403,
                "feature_disabled",
                "Chatbot feature is disabled.",
            )
        if not self.is_manager:
            raise Unauthorized("Manager role required")
        payload = self._request_payload()
        urls = payload.get("urls")
        if isinstance(urls, str):
            urls = [line.strip() for line in urls.splitlines() if line.strip()]
        if not isinstance(urls, list):
            urls = None
        result = self._indexer().index_remote_docs(urls=urls)
        return json_response(self.request.response, result, status=200)

    def chatbot_reset(self):
        self._check_post_authenticator()
        if not self._chatbot_enabled():
            return json_error(
                self.request.response,
                403,
                "feature_disabled",
                "Chatbot feature is disabled.",
            )
        if not self.is_manager:
            raise Unauthorized("Manager role required")
        self._store().reset()
        return json_response(self.request.response, {"success": True}, status=200)
