import json
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from AccessControl import Unauthorized

from zopyx.surveyjs.browser.chatbot import SurveyChatbot
from zopyx.surveyjs.browser.embed_direct import (
    EmbedConfigView,
    EmbedDirectTokenView,
    EmbedLoaderView,
    EmbedSurveyJSView,
)
from zopyx.surveyjs.browser.psf import PFSView
from zopyx.surveyjs.browser.survey_monitor import SurveyMonitorView
from zopyx.surveyjs.browser import chatbot as chatbot_module
from zopyx.surveyjs.browser import embed_direct as embed_module

from zopyx.surveyjs.browser import survey_monitor as monitor_module


class BrowserCoverageViewTests(unittest.TestCase):
    def make_view(self, cls):
        view = cls.__new__(cls)
        view.context = MagicMock()
        view.context.absolute_url.return_value = "http://nohost/survey"
        view.request = MagicMock()
        view.request.form = {}
        view.request.response = MagicMock()
        view.request.get.return_value = "GET"
        return view

    def test_chatbot_payload_context_and_json_field_coercion(self):
        view = self.make_view(SurveyChatbot)
        view.context.Title.return_value = "Survey"
        view.request.form = {"message": "hello", "top_k": "4", "history": "[]"}
        with patch.object(chatbot_module, "parse_json_body", return_value=None), patch(
            "plone.api.user.get_roles", return_value=["Editor"]
        ):
            payload = view._request_payload()
            context = view._build_context(payload)
        self.assertEqual(payload["message"], "hello")
        self.assertEqual(context.user_role, "Editor")
        self.assertEqual(view._coerce_json_field(b'{"x": 1}', {}), {"x": 1})
        self.assertEqual(view._coerce_json_field("invalid", {"fallback": True}), {"fallback": True})
        self.assertEqual(view._coerce_json_field("", []), [])

    def test_chatbot_api_guards_stream_success_and_failure(self):
        view = self.make_view(SurveyChatbot)
        with patch.object(view, "_check_post_authenticator"), patch.object(
            view, "_chatbot_enabled", return_value=False
        ), patch.object(chatbot_module, "json_error") as error:
            view.chatbot_api()
            error.assert_called_once()
        with patch.object(view, "_check_post_authenticator"), patch.object(
            view, "_chatbot_enabled", return_value=True
        ), patch.object(
            type(view), "can_manage_portal_content", new_callable=PropertyMock, return_value=False
        ), self.assertRaises(Unauthorized):
            view.chatbot_api()

        with patch.object(view, "_check_post_authenticator"), patch.object(
            view, "_chatbot_enabled", return_value=True
        ), patch.object(
            type(view), "can_manage_portal_content", new_callable=PropertyMock, return_value=True
        ), patch.object(view, "_request_payload", return_value={}), patch.object(
            chatbot_module, "json_error"
        ) as error:
            view.chatbot_api()
            self.assertEqual(error.call_args.args[1], 400)

        engine = MagicMock()
        engine.stream_chat.return_value = [{"delta": "ok"}, {"done": True}]
        with patch.object(view, "_check_post_authenticator"), patch.object(
            view, "_chatbot_enabled", return_value=True
        ), patch.object(
            type(view), "can_manage_portal_content", new_callable=PropertyMock, return_value=True
        ), patch.object(view, "_request_payload", return_value={"message": "hi", "stream": "true"}), patch.object(
            view, "_ensure_local_index"
        ), patch.object(view, "_build_context"), patch.object(view, "_engine", return_value=engine):
            view.chatbot_api()
        self.assertEqual(view.request.response.write.call_count, 2)

        engine.chat.side_effect = RuntimeError("engine down")
        with patch.object(view, "_check_post_authenticator"), patch.object(
            view, "_chatbot_enabled", return_value=True
        ), patch.object(
            type(view), "can_manage_portal_content", new_callable=PropertyMock, return_value=True
        ), patch.object(view, "_request_payload", return_value={"message": "hi"}), patch.object(
            view, "_ensure_local_index"
        ), patch.object(view, "_build_context"), patch.object(view, "_engine", return_value=engine), patch.object(
            chatbot_module, "json_error"
        ) as error:
            view.chatbot_api()
            self.assertEqual(error.call_args.args[1], 500)

    def test_chatbot_management_index_remote_and_reset(self):
        view = self.make_view(SurveyChatbot)
        with patch.object(view, "_chatbot_enabled", return_value=True), patch.object(
            type(view), "is_manager", new_callable=PropertyMock, return_value=True
        ), patch.object(view, "_store") as store, patch.object(
            chatbot_module, "json_response"
        ) as response:
            store.return_value.stats.return_value = {"local_chunk_count": 2}
            view.chatbot_api_stats()
            view.chatbot_mgmt()
            view.chatbot_reset()
            store.return_value.reset.assert_called_once()
            self.assertGreaterEqual(response.call_count, 3)

        with patch.object(view, "_check_post_authenticator"), patch.object(
            view, "_chatbot_enabled", return_value=True
        ), patch.object(type(view), "is_manager", new_callable=PropertyMock, return_value=True), patch.object(
            view, "_request_payload", return_value={"urls": "https://a.example\nhttps://b.example"}
        ), patch.object(view, "_indexer") as indexer, patch.object(chatbot_module, "json_response"):
            view.chatbot_index_remote()
        indexer.return_value.index_remote_docs.assert_called_once_with(
            urls=["https://a.example", "https://b.example"]
        )

    def test_monitor_json_cleanup_chart_and_empty_data(self):
        view = self.make_view(SurveyMonitorView)
        view.time_window = "1h"
        view.request.form = {"format": "json", "window": "24h"}
        view.index = MagicMock(return_value="html")
        stats = {
            "time_series": {"a": 2, "b": 3},
            "form_time_series": [{"title": "Form", "path": "/f", "count": 5, "series": {"a": 1}}],
            "duration_series": {"a": {"avg": 0.1, "max": 0.2}},
        }
        with patch.object(monitor_module, "get_submission_stats", return_value=stats):
            result = view()
            chart = view.get_chart_data()
        self.assertEqual(view.time_window, "24h")
        self.assertEqual(json.loads(result)["time_series"]["a"], 2)
        self.assertEqual(chart["cumulative"], [2, 5])
        self.assertEqual(chart["duration"]["avg"], [100, None])
        view.request.form = {"action": "cleanup"}
        with patch.object(monitor_module, "cleanup_old_data", return_value=7):
            view()
        view.request.form = {}
        with patch.object(monitor_module, "get_submission_stats", return_value={}):
            self.assertEqual(view.get_chart_data()["labels"], [])
        self.assertEqual(len(view.available_windows), len(monitor_module.TIME_WINDOWS))

    def test_monitor_helpers_rate_limit_and_json_safe(self):
        view = self.make_view(SurveyMonitorView)
        view.time_window = "1h"
        with patch.object(monitor_module, "check_rate_limit", return_value=(False, {"allowed": False})):
            self.assertEqual(view.get_rate_limit_status()["allowed"], False)
        with patch.object(monitor_module, "get_submission_stats", return_value={"time_series": {}}), patch(
            "zopyx.surveyjs.browser.survey_monitor.html_safe_json", return_value="{}"
        ) as safe:
            self.assertEqual(view.get_chart_data_json(), "{}")
            safe.assert_called_once()
        self.assertIn("UTC", view.get_current_time())

    def test_psf_properties_templates_and_creation_errors(self):
        view = self.make_view(PFSView)
        view.context.getPhysicalPath.return_value = ("", "folder")
        with patch("plone.api.user.is_anonymous", return_value=True):
            self.assertFalse(view.can_add_survey)
            self.assertEqual(view.template_options, [])
            self.assertEqual(view.cards, [])
        brain = MagicMock(UID="uid", Title="Template", Description="Desc")
        brain.getURL.return_value = "http://nohost/template"
        catalog = MagicMock()
        catalog.searchResults.return_value = [brain]
        with patch("plone.api.user.is_anonymous", return_value=False), patch(
            "plone.api.portal.get_tool", return_value=catalog
        ):
            self.assertEqual(view.template_options[0]["uid"], "uid")
            self.assertTrue(view.has_templates)
        with patch.object(type(view), "can_add_survey", new_callable=PropertyMock, return_value=False), patch.object(
            view, "_handle_create_from_template", return_value="x"
        ):
            with patch.object(view, "index", return_value="html"):
                self.assertEqual(view(), "html")

        view.request.form = {"template_uid": ""}
        with patch.object(type(view), "can_add_survey", new_callable=PropertyMock, return_value=True), patch(
            "plone.api.portal.show_message"
        ):
            view._handle_create_from_template()
        self.assertTrue(view.request.response.redirect.called)

    def test_embed_token_and_asset_views_cover_guards(self):
        view = self.make_view(EmbedDirectTokenView)
        view.context.embedding_mode = "direct"
        view.context.embed_direct_origins = ["https://app.example"]
        view.context.UID.return_value = "survey-1"
        with patch("plone.api.user.has_permission", return_value=False), patch.object(embed_module, "json_error") as error:
            view()
            self.assertEqual(error.call_args.args[1], 403)
        view.request.get.return_value = "POST"
        view.request.form = {}
        with patch("plone.api.user.has_permission", return_value=True), patch.object(
            embed_module, "CheckAuthenticator"
        ), patch.object(embed_module, "is_embed_direct_globally_enabled", return_value=True), patch.object(
            embed_module, "parse_json_body", return_value={"origin": "https://bad.example"}
        ), patch.object(embed_module, "json_error") as error:
            view()
            self.assertEqual(error.call_args.args[1], 403)

        asset = self.make_view(EmbedSurveyJSView)
        asset.request.get.side_effect = lambda key, default="": "wrong.js" if key == "name" else default
        self.assertEqual(asset(), "Not found")
        loader = self.make_view(EmbedLoaderView)
        loader.request.get_header.return_value = "https://app.example"
        with patch.object(loader, "_get_embed_js", return_value="bundle"):
            self.assertEqual(loader(), "bundle")
        self.assertEqual(loader.request.response.setHeader.call_count, 5)

    def test_embed_config_rejects_disabled_origin_missing_and_bad_token(self):
        view = self.make_view(EmbedConfigView)
        view.context.embed_direct_origins = ["https://app.example"]
        with patch.object(embed_module, "is_embed_direct_globally_enabled", return_value=False), patch.object(
            embed_module, "json_error"
        ) as error:
            view()
            self.assertEqual(error.call_args.args[1], 403)
        with patch.object(embed_module, "is_embed_direct_globally_enabled", return_value=True), patch.object(
            embed_module, "handle_cors_preflight", return_value=False
        ), patch.object(view.request, "get_header", side_effect=lambda name: "https://app.example" if name == "Origin" else None), patch.object(
            embed_module, "validate_origin", return_value=(True, "https://app.example", "")
        ), patch.object(embed_module, "json_error") as error:
            view()
            self.assertEqual(error.call_args.args[2], "token_required")
        view.request.get_header.side_effect = lambda name: "https://app.example" if name == "Origin" else "token"
        with patch.object(embed_module, "is_embed_direct_globally_enabled", return_value=True), patch.object(
            embed_module, "handle_cors_preflight", return_value=False
        ), patch.object(embed_module, "validate_origin", return_value=(True, "https://app.example", "")), patch.object(
            embed_module, "validate_embed_token", side_effect=embed_module.TokenInvalidError("bad")
        ), patch.object(embed_module, "json_error") as error:
            view()
            self.assertEqual(error.call_args.args[2], "token_invalid")


if __name__ == "__main__":
    unittest.main()
