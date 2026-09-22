"""Coverage tests for the last uncovered branches of the browser modules.

Covers the remaining statements of:

- ``browser/services/results.py`` (filter operators, dict-shaped Tabulator
  parameters)
- ``browser/services/ai.py`` (Ollama URL guard, Anthropic API key export)
- ``browser/survey_overview.py`` (post-field skipping, callable/broken expiry)
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import unittest
from unittest.mock import MagicMock, patch

from zopyx.surveyjs.browser.services import ai as ai_service
from zopyx.surveyjs.browser.services.results import (
    build_results_payload,
    results_apply_filters,
)
from zopyx.surveyjs.browser.survey_add import SurveyAddView
from zopyx.surveyjs.browser.survey_overview import SurveyOverview
from zopyx.surveyjs.content.survey import ISurvey


class FakeRequest:
    """Minimal request stub exposing the ``form`` mapping."""

    def __init__(self, form=None):
        self.form = form or {}


class ResultsFilterTests(unittest.TestCase):
    """Filter operator branches of ``results_apply_filters``."""

    def rows(self):
        return [
            {
                "user": "bob",
                "poll_id": "p1",
                "seq_no": 1,
                "created_ts": 100.0,
                "created_display": "2024-05-01T10:00:00",
            },
            {
                "user": "alice",
                "poll_id": "p2",
                "seq_no": 2,
                "created_ts": 200.0,
                "created_display": "2024-06-01T10:00:00",
            },
        ]

    def test_filter_without_field_key_matches_every_row(self) -> None:
        rows = self.rows()
        self.assertEqual(results_apply_filters(rows, [{"value": "bob"}]), rows)

    def test_filters_without_spec_return_rows_unchanged(self) -> None:
        rows = self.rows()
        self.assertIs(results_apply_filters(rows, []), rows)

    def test_ne_filter_drops_the_matching_row(self) -> None:
        rows = self.rows()
        out = results_apply_filters(
            rows, [{"field": "user", "type": "ne", "value": "bob"}]
        )
        self.assertEqual([row["user"] for row in out], ["alice"])

    def test_like_filter_on_created_ts_matches_the_display_value(self) -> None:
        rows = self.rows()
        out = results_apply_filters(
            rows, [{"field": "created_ts", "type": "like", "value": "2024-06"}]
        )
        self.assertEqual([row["user"] for row in out], ["alice"])

    def test_numeric_filter_on_non_numeric_column_matches_nothing(self) -> None:
        rows = self.rows()
        out = results_apply_filters(
            rows, [{"field": "user", "type": ">", "value": "10"}]
        )
        self.assertEqual(out, [])

    def test_less_than_and_less_or_equal_filters(self) -> None:
        rows = self.rows()
        out = results_apply_filters(
            rows, [{"field": "created_ts", "type": "<", "value": 150}]
        )
        self.assertEqual([row["user"] for row in out], ["bob"])

        out = results_apply_filters(
            rows, [{"field": "created_ts", "type": "<=", "value": 100}]
        )
        self.assertEqual([row["user"] for row in out], ["bob"])

    def test_unknown_filter_type_keeps_row(self) -> None:
        rows = self.rows()
        out = results_apply_filters(rows, [{"field": "user", "type": "regex"}])
        self.assertEqual(len(out), 2)


class BuildResultsPayloadTests(unittest.TestCase):
    """Dict-shaped ``sorters``/``filters`` parameters are normalized."""

    def test_dict_sorters_and_filters_are_wrapped_into_lists(self) -> None:
        results = [
            {"poll_id": "p1", "user": "bob", "created": None},
            {"poll_id": "p2", "user": "alice", "created": None},
        ]
        request = FakeRequest(
            {
                "sorters": '{"field": "user", "dir": "desc"}',
                "filters": '{"field": "user", "type": "like", "value": "bob"}',
            }
        )
        payload = build_results_payload(results, request)

        self.assertEqual(payload["total_rows"], 1)
        self.assertEqual(payload["data"][0]["user"], "bob")

    def test_dict_sorter_is_applied_to_the_row_order(self) -> None:
        results = [
            {"poll_id": "p1", "user": "carol", "created": None},
            {"poll_id": "p2", "user": "alice", "created": None},
        ]
        request = FakeRequest({"sorters": '{"field": "poll_id", "dir": "desc"}'})
        payload = build_results_payload(results, request)

        self.assertEqual([row["poll_id"] for row in payload["data"]], ["p2", "p1"])


class BuildLlmModelTests(unittest.TestCase):
    """Provider guards and API-key export of ``build_llm_model``."""

    def setUp(self) -> None:
        self.fake_ai = MagicMock()
        self.fake_ai.get_model.return_value = "model-instance"
        self.fake_ai.get_custom_model.return_value = "custom-model-instance"
        patcher = patch.object(ai_service, "get_ai_helper", return_value=self.fake_ai)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ollama_without_url_raises_runtime_error(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            ai_service.build_llm_model(
                {
                    "provider": "ollama",
                    "model_name": None,
                    "api_key": None,
                    "api_url": None,
                }
            )
        self.assertIn("Ollama URL not configured", str(ctx.exception))
        self.fake_ai.get_model.assert_not_called()

    def test_installed_claude_model_exports_anthropic_api_key(self) -> None:
        # clear=True keeps the test hermetic: the developer's shell may export
        # OPENAI_API_KEY/ANTHROPIC_API_KEY, which would leak into the assertions.
        with patch.dict(os.environ, {}, clear=True):
            result = ai_service.build_llm_model(
                {
                    "provider": "installed",
                    "model_name": "claude-3-5-sonnet",
                    "api_key": "sk-ant-secret",
                    "api_url": None,
                }
            )
            self.assertEqual(os.environ["ANTHROPIC_API_KEY"], "sk-ant-secret")
            self.assertNotIn("OPENAI_API_KEY", os.environ)

        self.assertEqual(result, "model-instance")
        self.fake_ai.get_model.assert_called_once_with("claude-3-5-sonnet")

    def test_installed_model_without_api_key_is_returned_unchanged(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = ai_service.build_llm_model(
                {
                    "provider": "installed",
                    "model_name": "llama3.2",
                    "api_key": None,
                    "api_url": None,
                }
            )
            self.assertNotIn("ANTHROPIC_API_KEY", os.environ)

        self.assertEqual(result, "model-instance")


class SurveyOverviewBranchTests(unittest.TestCase):
    """Post-field skipping and expiry handling of ``survey_overview_entries``."""

    def make_brain(self, obj):
        brain = MagicMock()
        brain.getObject.return_value = obj
        brain.Title = "Example"
        brain.Description = "Description"
        brain.review_state = "published"
        brain.effective = datetime(2024, 1, 1, tzinfo=timezone.utc)
        brain.getURL.return_value = "http://nohost/example"
        return brain

    def configure_view(self):
        view = SurveyOverview.__new__(SurveyOverview)
        view.context = MagicMock()
        view.context.getPhysicalPath.return_value = ("", "folder")
        view._format_catalog_iso = MagicMock(
            side_effect=lambda value: value.isoformat()
            if hasattr(value, "isoformat")
            else ""
        )
        view._translate_label = MagicMock(side_effect=lambda value: value)
        view._survey_field_value_text = MagicMock(return_value="value")
        view._compact_metadata_value = MagicMock(return_value=("value", ""))
        return view

    def render(self, obj, brain_expires):
        obj.Language.return_value = "en"
        brain = self.make_brain(obj)
        brain.expires = brain_expires
        catalog = MagicMock()
        catalog.searchResults.return_value = [brain]
        view = self.configure_view()
        with (
            patch("plone.api.portal.get_tool", return_value=catalog),
            patch(
                "zopyx.surveyjs.browser.survey_overview.get_result_storage",
                return_value=MagicMock(),
            ),
            patch("plone.api.content.get_state", return_value="published"),
        ):
            return view.survey_overview_entries()[0]

    def test_post_and_email_fields_are_skipped_without_their_actions(self) -> None:
        obj = MagicMock()
        obj.access_mode = ""
        obj.actions = set()

        entry = self.render(obj, "invalid")

        labels = [item["label"] for item in entry["metadata"]]
        self.assertNotIn(ISurvey["post_endpoint_url"].title, labels)
        self.assertNotIn(ISurvey["email_sender"].title, labels)
        self.assertIn(ISurvey["actions"].title, labels)
        self.assertFalse(entry["expires_future"])

    def test_callable_expiry_is_resolved_before_comparison(self) -> None:
        obj = MagicMock()
        obj.access_mode = "public"
        obj.actions = {"post"}

        entry = self.render(obj, lambda: datetime(2099, 1, 1, tzinfo=timezone.utc))

        self.assertTrue(entry["expires_future"])
        labels = [item["label"] for item in entry["metadata"]]
        self.assertIn(ISurvey["post_endpoint_url"].title, labels)

    def test_past_expiry_is_not_in_the_future(self) -> None:
        obj = MagicMock()
        obj.access_mode = "public"
        obj.actions = {"post"}

        entry = self.render(obj, datetime(2000, 1, 1, tzinfo=timezone.utc))

        self.assertFalse(entry["expires_future"])


class SurveyAddDatetimeYearTests(unittest.TestCase):
    """The defensive branch of ``_extract_datetime_year``."""

    def test_year_is_none_when_the_matched_digits_are_not_an_int(self) -> None:
        view = SurveyAddView.__new__(SurveyAddView)
        fake_match = MagicMock()
        fake_match.group.return_value = "12ab"

        with patch(
            "zopyx.surveyjs.browser.survey_add.re.match", return_value=fake_match
        ) as matcher:
            result = view._extract_datetime_year(object())

        self.assertIsNone(result)
        matcher.assert_called_once()

    def test_year_is_none_without_a_matching_date_prefix(self) -> None:
        view = SurveyAddView.__new__(SurveyAddView)
        self.assertIsNone(view._extract_datetime_year(object()))


if __name__ == "__main__":
    unittest.main()
