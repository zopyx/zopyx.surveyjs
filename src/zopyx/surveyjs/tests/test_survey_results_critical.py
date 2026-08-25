from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

from zopyx.surveyjs.browser.survey_results import SurveyResults


class SurveyResultsCriticalMethodTests(unittest.TestCase):
    def setUp(self):
        self.view = SurveyResults.__new__(SurveyResults)
        self.view.context = MagicMock()
        self.view.context.absolute_url.return_value = "http://nohost/survey"
        self.view.context.actions = {"post"}
        self.view.context.post_endpoint_url = "https://receiver.example/api"
        self.view.request = MagicMock()
        self.view.request.form = {"poll_id": "poll-1"}
        self.view.request.response.redirect.return_value = None
        self._show_message = patch(
            "plone.api.portal.show_message"
        ).start()
        self._annotations = patch(
            "zopyx.surveyjs.browser.survey_results.IAnnotations",
            return_value={},
        ).start()
        self.addCleanup(patch.stopall)

    def patch_auth(self):
        return patch.object(self.view, "_check_post_authenticator")

    def test_post_result_rejects_missing_id_disabled_action_endpoint_result_and_form(self):
        with self.patch_auth():
            self.view.request.form = {}
            self.assertIsNone(self.view.post_result())
            self.view.context.actions = set()
            self.view.request.form = {"poll_id": "poll-1"}
            self.assertIsNone(self.view.post_result())
            self.view.context.actions = {"post"}
            self.view.context.post_endpoint_url = ""
            self.assertIsNone(self.view.post_result())

        self.view.context.post_endpoint_url = "https://receiver.example/api"
        storage = MagicMock()
        storage.get_result.return_value = None
        with self.patch_auth(), patch(
            "zopyx.surveyjs.browser.survey_results.get_result_storage",
            return_value=storage,
        ):
            self.assertIsNone(self.view.post_result())

        storage.get_result.return_value = {"poll_id": "poll-1", "result": {"a": 1}}
        with self.patch_auth(), patch(
            "zopyx.surveyjs.browser.survey_results.get_result_storage",
            return_value=storage,
        ), patch.object(self.view, "_latest_form_json", return_value=None):
            self.assertIsNone(self.view.post_result())
        self.assertGreaterEqual(self.view.request.response.redirect.call_count, 5)

    def test_post_result_posts_normalized_payload_and_handles_http_failure(self):
        storage = MagicMock()
        storage.get_result.return_value = {
            "poll_id": "poll-1",
            "created": datetime(2024, 2, 2, tzinfo=timezone.utc),
            "result": {"a": 1},
        }
        response = MagicMock(status_code=202)
        self.view.request.response.redirect.reset_mock()
        with self.patch_auth(), patch(
            "zopyx.surveyjs.browser.survey_results.get_result_storage",
            return_value=storage,
        ), patch.object(
            self.view, "_latest_form_json", return_value={"pages": []}
        ), patch(
            "zopyx.surveyjs.browser.survey_results.httpx.post",
            return_value=response,
        ) as post:
            self.view.post_result()
        post.assert_called_once()
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["poll"]["poll_id"], "poll-1")
        self.assertEqual(payload["form"], {"pages": []})
        self.assertEqual(post.call_args.kwargs["timeout"], 10.0)

        response.raise_for_status.side_effect = RuntimeError("receiver failed")
        with self.patch_auth(), patch(
            "zopyx.surveyjs.browser.survey_results.get_result_storage",
            return_value=storage,
        ), patch.object(
            self.view, "_latest_form_json", return_value={"pages": []}
        ), patch("zopyx.surveyjs.browser.survey_results.httpx.post", return_value=response):
            self.view.post_result()
        self.assertTrue(self.view.request.response.redirect.called)

    def test_result_detail_reports_missing_inputs_result_and_form(self):
        self.view.request.form = {}
        self.assertEqual(self.view.result_detail()["error"], "Poll ID is required")
        self.view.request.form = {"poll_id": "poll-1"}
        storage = MagicMock()
        with patch(
            "zopyx.surveyjs.browser.survey_results.get_result_storage",
            return_value=storage,
        ):
            storage.get_result.return_value = None
            self.assertEqual(self.view.result_detail()["error"], "Poll result not found")
            storage.get_result.return_value = {"result": {"a": 1}}
            with patch.object(self.view, "_latest_form_json", return_value=None):
                self.assertEqual(
                    self.view.result_detail()["error"],
                    "No form definition available",
                )

    def test_result_detail_builds_html_with_converter(self):
        storage = MagicMock()
        storage.get_result.return_value = {
            "result": {"a": 1},
            "user": "alice",
            "created": datetime(2024, 2, 2, tzinfo=timezone.utc),
            "seq_no": 3,
        }
        converter = MagicMock()
        converter.collect_items.return_value = ([{"label": "A"}], [])
        with patch(
            "zopyx.surveyjs.browser.survey_results.get_result_storage",
            return_value=storage,
        ), patch.object(
            self.view, "_latest_form_json", return_value={"pages": []}
        ), patch(
            "zopyx.surveyjs.converters.cli.SurveyConverter",
            return_value=converter,
        ), patch(
            "zopyx.surveyjs.converters.build_markdown",
            return_value="markdown",
        ), patch(
            "zopyx.surveyjs.converters.html.build_html",
            return_value="<p>answer</p>",
        ):
            result = self.view.result_detail()
        self.assertEqual(result["poll_id"], "poll-1")
        self.assertEqual(result["seq_no"], 3)
        self.assertEqual(result["html"], "<p>answer</p>")
        converter.collect_items.assert_called_once()


if __name__ == "__main__":
    unittest.main()
