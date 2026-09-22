"""Coverage tests for the token store view, the auth service and the chatbot view.

These tests target the statement coverage of
``zopyx.surveyjs.browser.token_store``, ``zopyx.surveyjs.browser.services.auth``
and ``zopyx.surveyjs.browser.chatbot``.
"""

from __future__ import annotations

import csv
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import orjson
from AccessControl import Unauthorized
from AccessControl.SecurityManagement import getSecurityManager
from plone import api
from plone.app.testing import TEST_USER_ID, login, logout, setRoles
from plone.registry.interfaces import IRegistry
from zope.component import getAdapter, getUtility

from zopyx.surveyjs.browser.chatbot import SurveyChatbot
from zopyx.surveyjs.browser.services.auth import AuthService
from zopyx.surveyjs.interfaces import IFormsSettings, ITokenStore
from zopyx.surveyjs.security import build_auth_token
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING


class _MockUpload:
    """Minimal stand-in for a Zope file upload object."""

    def __init__(self, content, filename="tokens.csv", content_type="text/csv"):
        self._content = content
        self.filename = filename
        self.contentType = content_type

    def read(self):
        if isinstance(self._content, Exception):
            raise self._content
        if isinstance(self._content, str):
            return self._content.encode("utf-8")
        return self._content


class TokenStoreViewCoverageTests(unittest.TestCase):
    """Drive every branch of ``browser/token_store.py``."""

    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.request = self.layer["request"]
        self.request.form.clear()
        self.request.other.pop("REQUEST_METHOD", None)
        self.survey = api.content.create(
            container=self.portal,
            type="Survey",
            id="coverage-token-survey",
            title="Coverage Token Survey",
        )
        self.token_store = getAdapter(self.survey, ITokenStore)
        self.view = api.content.get_view(
            name="token-store",
            context=self.survey,
            request=self.request,
        )
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        self.request.form.clear()
        self.request.other.pop("REQUEST_METHOD", None)
        if "coverage-token-survey" in self.portal.objectIds():
            api.content.delete(obj=self.survey)

    def _logout_for_permission_denial(self) -> None:
        """Become an unprivileged user and restore the previous one afterwards."""
        current_login = getSecurityManager().getUser().getUserName()
        logout()
        self.addCleanup(login, self.portal, current_login)

    def _set_upload(self, upload) -> None:
        self.request.form["csv_file"] = upload
        self.request.form["import_csv"] = "Import"

    def test_check_permission_raises_unauthorized_for_unprivileged_user(self) -> None:
        # The manager passes the permission check ...
        self.assertTrue(self.view._check_permission())

        # ... an unprivileged visitor gets an Unauthorized error instead.
        self._logout_for_permission_denial()
        with self.assertRaises(Unauthorized) as ctx:
            self.view()
        self.assertEqual(
            str(ctx.exception),
            "You are not allowed to manage tokens for this survey.",
        )
        # The permission check runs before any token operation.
        self.assertEqual(self.token_store.list_tokens(), [])

    def test_post_request_validates_csrf_authenticator(self) -> None:
        self.token_store.generate_tokens(2)
        self.request.other["REQUEST_METHOD"] = "POST"
        self.request.form["download_valid_tokens"] = "Download"
        with patch("plone.protect.CheckAuthenticator") as authenticator:
            result = self.view()
        authenticator.assert_called_once_with(self.request)
        lines = result.strip().replace("\r\n", "\n").split("\n")
        self.assertEqual(lines[0], "token,url")
        self.assertEqual(len(lines), 3)

    def test_generate_tokens_action_creates_tokens(self) -> None:
        self.request.form["generate_tokens"] = "Generate"
        self.request.form["num_tokens"] = "3"
        with patch("plone.api.portal.show_message") as show_message:
            self.view()
        show_message.assert_called_once()
        self.assertEqual(show_message.call_args[0][0], "Generated 3 new token(s).")
        self.assertEqual(show_message.call_args[1]["type"], "info")
        stats = self.view.get_stats()
        self.assertEqual((stats["total"], stats["used"], stats["unused"]), (3, 0, 3))

    def test_generate_tokens_rejects_non_positive_count(self) -> None:
        self.request.form["generate_tokens"] = "Generate"
        self.request.form["num_tokens"] = "0"
        with patch("plone.api.portal.show_message") as show_message:
            self.view()
        self.assertEqual(
            show_message.call_args[0][0], "Please enter a positive number."
        )
        self.assertEqual(show_message.call_args[1]["type"], "error")
        self.assertEqual(self.token_store.list_tokens(), [])

    def test_generate_tokens_rejects_non_numeric_count(self) -> None:
        self.request.form["generate_tokens"] = "Generate"
        self.request.form["num_tokens"] = "many"
        with patch("plone.api.portal.show_message") as show_message:
            self.view()
        self.assertEqual(show_message.call_args[0][0], "Invalid number entered.")
        self.assertEqual(show_message.call_args[1]["type"], "error")
        self.assertEqual(self.token_store.list_tokens(), [])

    def test_download_all_tokens_action_from_form(self) -> None:
        tokens = self.token_store.generate_tokens(2)
        self.token_store.invalidate(tokens[0], reason="admin_revoked")
        self.request.form["download_all_tokens"] = "Download all"
        csv_content = self.view()
        lines = csv_content.strip().replace("\r\n", "\n").split("\n")
        self.assertEqual(lines[0], "token,url,created,used,status")
        self.assertEqual(len(lines), 3)
        statuses = {line.split(",")[0]: line.split(",")[4] for line in lines[1:]}
        self.assertEqual(statuses[tokens[0]], "used")
        self.assertEqual(statuses[tokens[1]], "unused")

    def test_clear_tokens_action_from_form(self) -> None:
        self.token_store.generate_tokens(4)
        self.request.form["clear_tokens"] = "Clear"
        with patch("plone.api.portal.show_message") as show_message:
            self.view()
        show_message.assert_called_once()
        self.assertEqual(show_message.call_args[0][0], "All tokens have been cleared.")
        self.assertEqual(show_message.call_args[1]["type"], "info")
        self.assertEqual(self.token_store.list_tokens(), [])

    def test_call_without_action_renders_template(self) -> None:
        rendered = self.view()
        self.assertIsInstance(rendered, str)
        self.assertIn("No tokens generated yet", rendered)
        self.assertIn("tv-action-box", rendered)

    def test_csv_import_without_file_reports_error(self) -> None:
        self.request.form["import_csv"] = "Import"
        with patch("plone.api.portal.show_message") as show_message:
            self.view()
        self.assertEqual(show_message.call_args[0][0], "No file uploaded.")
        self.assertEqual(show_message.call_args[1]["type"], "error")
        self.assertEqual(self.token_store.list_tokens(), [])

    def test_csv_import_rejects_invalid_file_type(self) -> None:
        self._set_upload(
            _MockUpload(
                "token\nabcdefgh", filename="tokens.pdf", content_type="application/pdf"
            )
        )
        with patch("plone.api.portal.show_message") as show_message:
            self.view()
        self.assertEqual(
            show_message.call_args[0][0],
            "Invalid file type. Please upload a CSV file.",
        )
        self.assertEqual(self.token_store.list_tokens(), [])

    def test_csv_import_rejects_empty_file(self) -> None:
        self._set_upload(_MockUpload("   \n", filename="empty.csv"))
        with patch("plone.api.portal.show_message") as show_message:
            self.view()
        self.assertEqual(show_message.call_args[0][0], "CSV file is empty.")
        self.assertEqual(self.token_store.list_tokens(), [])

    def test_csv_import_skips_blank_rows_and_reports_no_tokens(self) -> None:
        self._set_upload(_MockUpload("token,note\n,first\n,second\n"))
        with patch("plone.api.portal.show_message") as show_message:
            self.view()
        self.assertEqual(show_message.call_args[0][0], "No valid tokens found in CSV.")
        self.assertEqual(self.token_store.list_tokens(), [])

    def test_csv_import_truncates_more_than_three_errors(self) -> None:
        self._set_upload(_MockUpload("token\nab\ncd\nef\ngh\nij"))
        with patch("plone.api.portal.show_message") as show_message:
            self.view()
        message = show_message.call_args[0][0]
        self.assertTrue(
            message.startswith("Validation errors: Row 2: token is too short")
        )
        self.assertIn("(and 2 more)", message)
        self.assertNotIn("Row 6", message)
        self.assertEqual(self.token_store.list_tokens(), [])

    def test_csv_import_handles_csv_parse_error(self) -> None:
        self._set_upload(_MockUpload("token\nvalidtoken123"))
        with (
            patch(
                "zopyx.surveyjs.browser.token_store.csv.DictReader",
                side_effect=csv.Error("boom"),
            ),
            patch("plone.api.portal.show_message") as show_message,
        ):
            self.view()
        self.assertEqual(show_message.call_args[0][0], "CSV parsing error: boom")
        self.assertEqual(show_message.call_args[1]["type"], "error")
        self.assertEqual(self.token_store.list_tokens(), [])

    def test_csv_import_handles_unexpected_error(self) -> None:
        self._set_upload(_MockUpload(RuntimeError("disk exploded")))
        with patch("plone.api.portal.show_message") as show_message:
            self.view()
        self.assertEqual(
            show_message.call_args[0][0], "Error importing tokens: disk exploded"
        )
        self.assertEqual(show_message.call_args[1]["type"], "error")
        self.assertEqual(self.token_store.list_tokens(), [])


class AuthServiceCoverageTests(unittest.TestCase):
    """Drive the remaining branches of ``browser/services/auth.py``."""

    def setUp(self) -> None:
        self.context = SimpleNamespace(
            access_mode="public",
            trusted_access_ttl_hours=2,
        )
        self.request = MagicMock()
        self.request.form = {}
        self.request.get.return_value = None
        self.service = AuthService(self.context, self.request, lambda: "form-1")
        self.settings = SimpleNamespace(
            authenticity_token_enabled=False,
            authenticity_token_secret="",
            authenticity_token_issuer="issuer",
            authenticity_token_audience="audience",
            authenticity_token_ttl_seconds=600,
        )

    def test_auth_token_ttl_falls_back_to_default(self) -> None:
        self.settings.authenticity_token_ttl_seconds = "not-a-number"
        self.assertEqual(self.service._auth_token_ttl(self.settings), 600)
        self.settings.authenticity_token_ttl_seconds = None
        self.assertEqual(self.service._auth_token_ttl(self.settings), 600)
        self.settings.authenticity_token_ttl_seconds = 900
        self.assertEqual(self.service._auth_token_ttl(self.settings), 900)

    def test_token_cache_returns_none_when_backend_raises(self) -> None:
        with patch(
            "zopyx.surveyjs.browser.services.auth.get_configured_kv_store",
            side_effect=RuntimeError("no kv store"),
        ) as factory:
            self.assertIsNone(self.service._token_cache(self.settings))
        factory.assert_called_once_with(self.settings, "auth")

    def test_issue_trusted_access_token_without_cache(self) -> None:
        with (
            patch.object(self.service, "_auth_settings", return_value=self.settings),
            patch.object(self.service, "_token_cache", return_value=None),
        ):
            self.assertEqual(
                self.service.issue_trusted_access_token("v7"), (None, None)
            )

    def test_issue_trusted_access_token_persists_metadata(self) -> None:
        cache = MagicMock()
        with (
            patch.object(self.service, "_auth_settings", return_value=self.settings),
            patch.object(self.service, "_token_cache", return_value=cache),
        ):
            token, metadata = self.service.issue_trusted_access_token("v7")

        self.assertIsInstance(token, str)
        self.assertGreaterEqual(len(token), 20)
        self.assertEqual(metadata["form_id"], "form-1")
        self.assertEqual(metadata["form_version"], "v7")
        self.assertEqual(metadata["state"], "ISSUED")
        cache.set.assert_called_once_with(f"trusted:{token}", metadata, expire=2 * 3600)
        cache.close.assert_called_once_with()
        ttl = datetime.fromisoformat(metadata["expires_at"]) - datetime.fromisoformat(
            metadata["issued_at"]
        )
        self.assertAlmostEqual(ttl.total_seconds(), 2 * 3600, delta=1)

    def test_cached_trusted_access_with_logger_reports_reasons(self) -> None:
        self.context.access_mode = "trusted"
        self.request.form = {"tt": "token"}
        cache = MagicMock()
        logger = MagicMock()
        with (
            patch.object(self.service, "_auth_settings", return_value=self.settings),
            patch.object(self.service, "_token_cache", return_value=cache),
        ):
            cache.get.return_value = None
            self.assertFalse(self.service.require_trusted_access(logger=logger))
            self.request.response.setStatus.assert_called_with(403)

            cache.get.return_value = {"state": "REVOKED", "form_id": "form-1"}
            self.assertFalse(self.service.require_trusted_access(logger=logger))

            cache.get.return_value = {"state": "ISSUED", "form_id": "other-form"}
            self.assertFalse(self.service.require_trusted_access(logger=logger))

            self.request.response.setStatus.reset_mock()
            cache.get.return_value = {"state": "ISSUED", "form_id": "form-1"}
            self.assertTrue(self.service.require_trusted_access(logger=logger))
            self.request.response.setStatus.assert_not_called()

        logged = [call.args[0] for call in logger.info.call_args_list]
        self.assertEqual(
            logged,
            [
                "Survey trusted access denied: reason=invalid_token",
                "Survey trusted access denied: reason=revoked_token",
                "Survey trusted access denied: reason=form_mismatch",
            ],
        )

    def test_cached_trusted_access_without_cache_reports_unavailable(self) -> None:
        self.context.access_mode = "trusted"
        self.request.form = {"tt": "token"}
        logger = MagicMock()
        with (
            patch.object(self.service, "_auth_settings", return_value=self.settings),
            patch.object(self.service, "_token_cache", return_value=None),
        ):
            self.assertFalse(self.service.require_trusted_access(logger=logger))
        logger.info.assert_called_once_with(
            "Survey trusted access denied: reason=cache_unavailable"
        )
        self.request.response.setStatus.assert_called_with(503)

    def test_trusted_tokens_access_without_token_store(self) -> None:
        self.context.access_mode = "trusted-tokens"
        self.request.form = {"tt": "token"}
        logger = MagicMock()
        with patch(
            "zopyx.surveyjs.browser.services.auth.getAdapter",
            side_effect=RuntimeError("no adapter"),
        ):
            self.assertFalse(self.service.require_trusted_access(logger=logger))
        logger.info.assert_called_once_with(
            "Survey trusted-tokens access denied: reason=token_store_unavailable"
        )
        self.request.response.setStatus.assert_called_with(503)

    def test_trusted_tokens_access_rejects_unknown_token(self) -> None:
        self.context.access_mode = "trusted-tokens"
        self.request.form = {"tt": "token"}
        store = MagicMock()
        store.has_token.return_value = False
        logger = MagicMock()
        with patch(
            "zopyx.surveyjs.browser.services.auth.getAdapter", return_value=store
        ):
            self.assertFalse(self.service.require_trusted_access(logger=logger))
        store.has_token.assert_called_once_with("token")
        logger.info.assert_called_once_with(
            "Survey trusted-tokens access denied: reason=invalid_or_used_token"
        )
        self.request.response.setStatus.assert_called_with(403)

    def test_trusted_access_denies_missing_token_with_logger(self) -> None:
        self.context.access_mode = "trusted"
        logger = MagicMock()
        self.assertFalse(self.service.require_trusted_access(logger=logger))
        logger.info.assert_called_once_with(
            "Survey trusted access denied: reason=missing_token"
        )
        self.request.response.setStatus.assert_called_with(403)

    def test_consume_trusted_token_is_a_noop_outside_trusted_tokens_mode(self) -> None:
        self.request.form = {"tt": "token"}
        self.assertTrue(self.service.consume_trusted_access_token())
        self.request.response.setStatus.assert_not_called()

    def test_consume_trusted_token_without_token_reports_missing(self) -> None:
        self.context.access_mode = "trusted-tokens"
        logger = MagicMock()
        self.assertFalse(self.service.consume_trusted_access_token(logger=logger))
        logger.info.assert_called_once_with(
            "Survey trusted-tokens consume denied: reason=missing_token"
        )
        self.request.response.setStatus.assert_called_with(403)

    def test_consume_trusted_token_without_store(self) -> None:
        self.context.access_mode = "trusted-tokens"
        self.request.form = {"tt": "token"}
        logger = MagicMock()
        with patch(
            "zopyx.surveyjs.browser.services.auth.getAdapter",
            side_effect=RuntimeError("no adapter"),
        ):
            self.assertFalse(self.service.consume_trusted_access_token(logger=logger))
        logger.info.assert_called_once_with(
            "Survey trusted-tokens consume denied: reason=token_store_unavailable"
        )
        self.request.response.setStatus.assert_called_with(503)

    def test_consume_trusted_token_reports_invalid_token(self) -> None:
        self.context.access_mode = "trusted-tokens"
        self.request.form = {"tt": "token"}
        store = MagicMock()
        store.consume_token.return_value = False
        logger = MagicMock()
        with patch(
            "zopyx.surveyjs.browser.services.auth.getAdapter", return_value=store
        ):
            self.assertFalse(self.service.consume_trusted_access_token(logger=logger))
        store.consume_token.assert_called_once_with("token", reason="user_submission")
        logger.info.assert_called_once_with(
            "Survey trusted-tokens consume denied: reason=invalid_or_used_token"
        )
        self.request.response.setStatus.assert_called_with(403)

    def test_consume_trusted_token_logs_success(self) -> None:
        self.context.access_mode = "trusted-tokens"
        self.request.form = {"tt": "token"}
        store = MagicMock()
        store.consume_token.return_value = True
        logger = MagicMock()
        with patch(
            "zopyx.surveyjs.browser.services.auth.getAdapter", return_value=store
        ):
            self.assertTrue(self.service.consume_trusted_access_token(logger=logger))
        logger.info.assert_called_once_with(
            "Survey trusted-tokens access: token_consumed"
        )
        self.request.response.setStatus.assert_not_called()

    def test_require_auth_token_fails_closed_without_cache(self) -> None:
        self.settings.authenticity_token_enabled = True
        self.settings.authenticity_token_secret = "secret"
        token = build_auth_token(
            form_id="form-1",
            form_version="v1",
            issuer="issuer",
            audience="audience",
            ttl_seconds=600,
            secret="secret",
        )
        self.request.form = {"auth_token": token}
        logger = MagicMock()
        with (
            patch.object(self.service, "_auth_settings", return_value=self.settings),
            patch.object(self.service, "_token_cache", return_value=None),
        ):
            self.assertFalse(self.service.require_auth_token("v1", logger=logger))
        logger.error.assert_called_once_with(
            "Survey auth token cache unavailable - rejecting request"
        )
        self.request.response.setStatus.assert_called_with(503)


class SurveyChatbotViewCoverageTests(unittest.TestCase):
    """Drive every endpoint of the ``browser/chatbot.py`` view."""

    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.survey = api.content.create(
            container=self.portal,
            type="Survey",
            id="coverage-chatbot-survey",
            title="Chatbot Coverage Survey",
        )
        registry = getUtility(IRegistry)
        self.settings = registry.forInterface(IFormsSettings, check=False)
        self._original_features = list(
            getattr(self.settings, "features_enabled", []) or []
        )
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        self.settings.features_enabled = list(self._original_features)
        if "coverage-chatbot-survey" in self.portal.objectIds():
            api.content.delete(obj=self.survey)

    def _set_features(self, values) -> None:
        self.settings.features_enabled = list(values)

    def _logout_for_permission_denial(self) -> None:
        current_login = getSecurityManager().getUser().getUserName()
        logout()
        self.addCleanup(login, self.portal, current_login)

    def _make_view(self):
        request = MagicMock()
        request.form = {}
        request.method = "GET"
        request.get.return_value = None
        return SurveyChatbot(self.survey, request), request

    @staticmethod
    def _body(request):
        return orjson.loads(request.response.setResult.call_args[0][0])

    def test_factories_build_store_indexer_and_engine(self) -> None:
        view, _request = self._make_view()
        with (
            patch("zopyx.surveyjs.browser.chatbot.ChatDocumentStore") as store_cls,
            patch("zopyx.surveyjs.browser.chatbot.DocumentationIndexer") as indexer_cls,
            patch("zopyx.surveyjs.browser.chatbot.ChatEngine") as engine_cls,
            patch(
                "zopyx.surveyjs.browser.chatbot.ai_service.load_ai_settings",
                return_value={"provider": "installed"},
            ),
        ):
            store = view._store()
            indexer = view._indexer()
            engine = view._engine()

        self.assertIs(store, store_cls.return_value)
        self.assertIs(indexer, indexer_cls.return_value)
        indexer_cls.assert_called_once_with(store)
        engine_cls.assert_called_once_with(
            store=store, settings={"provider": "installed"}
        )
        self.assertIs(engine, engine_cls.return_value)

    def test_ensure_local_index_only_indexes_when_empty(self) -> None:
        view, _request = self._make_view()
        with (
            patch("zopyx.surveyjs.browser.chatbot.ChatDocumentStore") as store_cls,
            patch("zopyx.surveyjs.browser.chatbot.DocumentationIndexer") as indexer_cls,
        ):
            store_cls.return_value.stats.return_value = {"local_chunk_count": 4}
            view._ensure_local_index()
            indexer_cls.return_value.index_project_docs.assert_not_called()

            store_cls.return_value.stats.return_value = {"local_chunk_count": 0}
            view._ensure_local_index()
            indexer_cls.return_value.index_project_docs.assert_called_once_with()

    def test_request_payload_prefers_json_body_and_empty_form(self) -> None:
        view, request = self._make_view()
        payload = {"message": "from body"}
        with patch(
            "zopyx.surveyjs.browser.chatbot.parse_json_body", return_value=payload
        ) as parse:
            self.assertIs(view._request_payload(), payload)
        parse.assert_called_once_with(request)

        with patch("zopyx.surveyjs.browser.chatbot.parse_json_body", return_value=None):
            self.assertEqual(view._request_payload(), {})

    def test_coerce_json_field_passthrough_and_default(self) -> None:
        view, _request = self._make_view()
        payload = {"pages": []}
        given = ["a"]
        self.assertIs(view._coerce_json_field(payload, None), payload)
        self.assertIs(view._coerce_json_field(given, []), given)
        self.assertEqual(view._coerce_json_field(b'{"a": 1}', None), {"a": 1})
        self.assertEqual(view._coerce_json_field(5, "fallback"), "fallback")
        self.assertEqual(view._coerce_json_field("not json", "fallback"), "fallback")
        self.assertIsNone(view._coerce_json_field(None, None))

    def test_build_context_normalises_payload(self) -> None:
        view, _request = self._make_view()
        context = view._build_context(
            {
                "current_view": "  @@chatbot  ",
                "survey_title": "  Title  ",
                "history": '{"role": "user"}',
                "survey_json": '{"pages": []}',
            }
        )
        self.assertEqual(context.current_view, "@@chatbot")
        self.assertEqual(context.survey_title, "Title")
        self.assertEqual(context.history, [])
        self.assertEqual(context.survey_json, {"pages": []})
        self.assertEqual(context.user_role, "Manager")

        fallback = view._build_context({})
        self.assertEqual(fallback.survey_title, "Chatbot Coverage Survey")
        self.assertEqual(fallback.user_role, "Manager")

    def test_chatbot_api_disabled_returns_403(self) -> None:
        self._set_features([])
        view, request = self._make_view()
        request.form = {"message": "hello"}
        view.chatbot_api()
        request.response.setStatus.assert_called_with(403)
        self.assertEqual(self._body(request)["error"], "feature_disabled")

    def test_chatbot_api_requires_permission(self) -> None:
        self._set_features(["chatbot"])
        self._logout_for_permission_denial()
        view, request = self._make_view()
        request.form = {"message": "hello"}
        with self.assertRaises(Unauthorized):
            view.chatbot_api()

    def test_chatbot_api_requires_message(self) -> None:
        self._set_features(["chatbot"])
        view, request = self._make_view()
        request.form = {"message": "   "}
        view.chatbot_api()
        request.response.setStatus.assert_called_with(400)
        self.assertEqual(self._body(request)["error"], "missing_message")

    def test_chatbot_api_returns_answer_and_clamps_top_k(self) -> None:
        self._set_features(["chatbot"])
        view, request = self._make_view()
        request.form = {
            "message": "How do I export results?",
            "top_k": "many",
            "history": "{}",
            "survey_json": '{"pages": []}',
        }
        store = MagicMock()
        store.stats.return_value = {"local_chunk_count": 12}
        indexer = MagicMock()
        engine = MagicMock()
        engine.chat.return_value = {"response": "Use @@results.", "sources": []}
        with (
            patch(
                "zopyx.surveyjs.browser.chatbot.ChatDocumentStore", return_value=store
            ),
            patch(
                "zopyx.surveyjs.browser.chatbot.DocumentationIndexer",
                return_value=indexer,
            ),
            patch("zopyx.surveyjs.browser.chatbot.ChatEngine", return_value=engine),
        ):
            view.chatbot_api()

        engine.chat.assert_called_once()
        self.assertEqual(engine.chat.call_args[0][0], "How do I export results?")
        self.assertEqual(engine.chat.call_args[1]["top_k"], 6)
        chat_context = engine.chat.call_args[1]["context"]
        self.assertEqual(chat_context.history, [])
        self.assertEqual(chat_context.user_role, "Manager")
        self.assertEqual(chat_context.survey_json, {"pages": []})
        indexer.index_project_docs.assert_not_called()
        request.response.setStatus.assert_called_with(200)
        self.assertEqual(
            self._body(request), {"response": "Use @@results.", "sources": []}
        )

    def test_chatbot_api_clamps_out_of_range_top_k(self) -> None:
        self._set_features(["chatbot"])
        view, request = self._make_view()
        request.form = {"message": "hello", "top_k": "99"}
        store = MagicMock()
        store.stats.return_value = {"local_chunk_count": 1}
        engine = MagicMock()
        engine.chat.return_value = {"response": "ok"}
        with (
            patch(
                "zopyx.surveyjs.browser.chatbot.ChatDocumentStore", return_value=store
            ),
            patch("zopyx.surveyjs.browser.chatbot.ChatEngine", return_value=engine),
        ):
            view.chatbot_api()
        self.assertEqual(engine.chat.call_args[1]["top_k"], 12)

    def test_chatbot_api_reports_failure(self) -> None:
        self._set_features(["chatbot"])
        view, request = self._make_view()
        request.form = {"message": "hello", "top_k": 3}
        store = MagicMock()
        store.stats.return_value = {"local_chunk_count": 1}
        engine = MagicMock()
        engine.chat.side_effect = RuntimeError("engine down")
        with (
            patch(
                "zopyx.surveyjs.browser.chatbot.ChatDocumentStore", return_value=store
            ),
            patch("zopyx.surveyjs.browser.chatbot.ChatEngine", return_value=engine),
        ):
            view.chatbot_api()
        request.response.setStatus.assert_called_with(500)
        self.assertEqual(self._body(request)["error"], "chat_failed")
        self.assertEqual(engine.chat.call_args[1]["top_k"], 3)

    def test_chatbot_api_streams_events(self) -> None:
        self._set_features(["chatbot"])
        view, request = self._make_view()
        request.form = {"message": "hello", "stream": "true"}
        store = MagicMock()
        store.stats.return_value = {"local_chunk_count": 1}
        engine = MagicMock()
        engine.stream_chat.return_value = iter([{"delta": "hi", "done": False}])
        with (
            patch(
                "zopyx.surveyjs.browser.chatbot.ChatDocumentStore", return_value=store
            ),
            patch("zopyx.surveyjs.browser.chatbot.ChatEngine", return_value=engine),
        ):
            view.chatbot_api()
        written = b"".join(
            call.args[0] for call in request.response.write.call_args_list
        )
        self.assertEqual(
            orjson.loads(written[len(b"data: ") : -2]), {"delta": "hi", "done": False}
        )

    def test_chatbot_api_stats_disabled_and_allowed(self) -> None:
        self._set_features([])
        view, request = self._make_view()
        view.chatbot_api_stats()
        request.response.setStatus.assert_called_with(403)
        self.assertEqual(self._body(request)["error"], "feature_disabled")

        self._set_features(["chatbot"])
        view, request = self._make_view()
        store = MagicMock()
        store.stats.return_value = {"document_count": 2}
        with patch(
            "zopyx.surveyjs.browser.chatbot.ChatDocumentStore", return_value=store
        ):
            view.chatbot_api_stats()
        request.response.setStatus.assert_called_with(200)
        self.assertEqual(self._body(request), {"document_count": 2})

    def test_chatbot_api_stats_requires_permission(self) -> None:
        self._set_features(["chatbot"])
        self._logout_for_permission_denial()
        view, _request = self._make_view()
        with self.assertRaises(Unauthorized):
            view.chatbot_api_stats()

    def test_chatbot_mgmt_disabled_and_unauthorized(self) -> None:
        self._set_features([])
        view, request = self._make_view()
        view.chatbot_mgmt()
        request.response.setStatus.assert_called_with(403)
        self.assertEqual(self._body(request)["error"], "feature_disabled")

        self._set_features(["chatbot"])
        self._logout_for_permission_denial()
        view, _request = self._make_view()
        with self.assertRaises(Unauthorized) as ctx:
            view.chatbot_mgmt()
        self.assertEqual(str(ctx.exception), "Manager role required")

    def test_chatbot_mgmt_returns_endpoint_map(self) -> None:
        self._set_features(["chatbot"])
        view, request = self._make_view()
        store = MagicMock()
        store.stats.return_value = {"document_count": 0}
        with patch(
            "zopyx.surveyjs.browser.chatbot.ChatDocumentStore", return_value=store
        ):
            view.chatbot_mgmt()
        body = self._body(request)
        self.assertEqual(
            body["endpoints"]["stats"],
            f"{self.survey.absolute_url()}/@@chatbot-stats",
        )
        self.assertTrue(body["surveyjs_allowlist"])
        self.assertEqual(body["stats"], {"document_count": 0})

    def test_chatbot_index_local_disabled_and_unauthorized(self) -> None:
        self._set_features([])
        view, request = self._make_view()
        view.chatbot_index_local()
        request.response.setStatus.assert_called_with(403)
        self.assertEqual(self._body(request)["error"], "feature_disabled")

        self._set_features(["chatbot"])
        self._logout_for_permission_denial()
        view, _request = self._make_view()
        with self.assertRaises(Unauthorized) as ctx:
            view.chatbot_index_local()
        self.assertEqual(str(ctx.exception), "Manager role required")

    def test_chatbot_index_local_indexes_project_docs(self) -> None:
        self._set_features(["chatbot"])
        view, request = self._make_view()
        indexer = MagicMock()
        indexer.index_project_docs.return_value = {"indexed_documents": 3}
        with (
            patch("zopyx.surveyjs.browser.chatbot.ChatDocumentStore"),
            patch(
                "zopyx.surveyjs.browser.chatbot.DocumentationIndexer",
                return_value=indexer,
            ),
        ):
            view.chatbot_index_local()
        indexer.index_project_docs.assert_called_once_with()
        request.response.setStatus.assert_called_with(200)
        self.assertEqual(self._body(request), {"indexed_documents": 3})

    def test_chatbot_index_remote_disabled_and_unauthorized(self) -> None:
        self._set_features([])
        view, request = self._make_view()
        view.chatbot_index_remote()
        request.response.setStatus.assert_called_with(403)
        self.assertEqual(self._body(request)["error"], "feature_disabled")

        self._set_features(["chatbot"])
        self._logout_for_permission_denial()
        view, _request = self._make_view()
        with self.assertRaises(Unauthorized) as ctx:
            view.chatbot_index_remote()
        self.assertEqual(str(ctx.exception), "Manager role required")

    def test_chatbot_index_remote_normalises_urls(self) -> None:
        self._set_features(["chatbot"])
        view, request = self._make_view()
        indexer = MagicMock()
        indexer.index_remote_docs.return_value = {"urls_indexed": 2}
        with (
            patch(
                "zopyx.surveyjs.browser.chatbot.parse_json_body",
                return_value={"urls": "https://a.example\n\nhttps://b.example"},
            ),
            patch("zopyx.surveyjs.browser.chatbot.ChatDocumentStore"),
            patch(
                "zopyx.surveyjs.browser.chatbot.DocumentationIndexer",
                return_value=indexer,
            ),
        ):
            view.chatbot_index_remote()
        indexer.index_remote_docs.assert_called_once_with(
            urls=["https://a.example", "https://b.example"]
        )
        self.assertEqual(self._body(request), {"urls_indexed": 2})

    def test_chatbot_index_remote_ignores_non_list_urls(self) -> None:
        self._set_features(["chatbot"])
        view, request = self._make_view()
        indexer = MagicMock()
        indexer.index_remote_docs.return_value = {"urls_indexed": 0}
        with (
            patch(
                "zopyx.surveyjs.browser.chatbot.parse_json_body",
                return_value={"urls": 5},
            ),
            patch("zopyx.surveyjs.browser.chatbot.ChatDocumentStore"),
            patch(
                "zopyx.surveyjs.browser.chatbot.DocumentationIndexer",
                return_value=indexer,
            ),
        ):
            view.chatbot_index_remote()
        indexer.index_remote_docs.assert_called_once_with(urls=None)

    def test_chatbot_reset_disabled_and_unauthorized(self) -> None:
        self._set_features([])
        view, request = self._make_view()
        view.chatbot_reset()
        request.response.setStatus.assert_called_with(403)
        self.assertEqual(self._body(request)["error"], "feature_disabled")

        self._set_features(["chatbot"])
        self._logout_for_permission_denial()
        view, _request = self._make_view()
        with self.assertRaises(Unauthorized) as ctx:
            view.chatbot_reset()
        self.assertEqual(str(ctx.exception), "Manager role required")

    def test_chatbot_reset_clears_store(self) -> None:
        self._set_features(["chatbot"])
        view, request = self._make_view()
        store = MagicMock()
        with patch(
            "zopyx.surveyjs.browser.chatbot.ChatDocumentStore", return_value=store
        ):
            view.chatbot_reset()
        store.reset.assert_called_once_with()
        request.response.setStatus.assert_called_with(200)
        self.assertEqual(self._body(request), {"success": True})


if __name__ == "__main__":
    unittest.main()
