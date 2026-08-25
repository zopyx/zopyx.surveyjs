from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

from zopyx.surveyjs.browser.survey_overview import SurveyOverview
from zopyx.surveyjs.browser.survey_templates_overview import SurveyTemplatesOverview
from zopyx.surveyjs.browser.survey_versions import SurveyVersions
from zopyx.surveyjs.constants import FORM_VERSIONS_KEY


class OverviewMethodTests(unittest.TestCase):
    def make_brain(self, obj, portal_type="Survey"):
        brain = MagicMock()
        brain.getObject.return_value = obj
        brain.Title = "Example"
        brain.Description = "Description"
        brain.UID = "uid-1"
        brain.review_state = "published"
        brain.effective = datetime(2024, 1, 1, tzinfo=timezone.utc)
        brain.expires = datetime(2099, 1, 1, tzinfo=timezone.utc)
        brain.getURL.return_value = "http://nohost/example"
        return brain

    def configure_view(self, view):
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

    def test_survey_overview_entries_handles_actions_state_and_storage_errors(self):
        obj = MagicMock()
        obj.access_mode = "trusted"
        obj.Language.return_value = "en"
        obj.actions = {"post"}
        brain = self.make_brain(obj)
        catalog = MagicMock()
        catalog.searchResults.return_value = [brain]
        storage = MagicMock()
        storage.count_results.side_effect = RuntimeError("storage down")
        view = self.configure_view(SurveyOverview.__new__(SurveyOverview))
        with patch("plone.api.portal.get_tool", return_value=catalog), patch(
            "zopyx.surveyjs.browser.survey_overview.get_result_storage",
            return_value=storage,
        ), patch("plone.api.content.get_state", side_effect=RuntimeError):
            entries = view.survey_overview_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["access_mode"], "Trusted access token")
        self.assertEqual(entries[0]["results_count"], 0)
        self.assertTrue(entries[0]["expires_future"])
        catalog.searchResults.assert_called_once()

    def test_template_overview_entries_handles_review_state_and_expiry(self):
        obj = MagicMock()
        obj.Language.return_value = "de"
        obj.actions = set()
        brain = self.make_brain(obj, "SurveyTemplate")
        brain.expires = "invalid"
        catalog = MagicMock()
        catalog.searchResults.return_value = [brain]
        view = self.configure_view(SurveyTemplatesOverview.__new__(SurveyTemplatesOverview))
        with patch("plone.api.portal.get_tool", return_value=catalog), patch(
            "plone.api.content.get_state", return_value="private"
        ):
            entries = view.survey_templates_overview_entries()
        self.assertEqual(entries[0]["uid"], "uid-1")
        self.assertEqual(entries[0]["language"], "de")
        self.assertFalse(entries[0]["expires_future"])


class CreateTemplateFromVersionTests(unittest.TestCase):
    def setUp(self):
        self.view = SurveyVersions.__new__(SurveyVersions)
        self.view.context = MagicMock()
        self.view.context.absolute_url.return_value = "http://nohost/survey"
        self.view.context.aq_parent = MagicMock()
        self.view.context.Description.return_value = "Survey description"
        self.view.request = MagicMock()
        self.view.request.response.redirect.return_value = None
        self.view.request.form = {"version_id": "v1", "template_title": "Template"}
        self.annotations = {FORM_VERSIONS_KEY: {"v1": {"form_json": {"pages": []}}}}
        patcher = patch.object(self.view, "_check_post_authenticator")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_create_template_rejects_missing_input_version_and_permission(self):
        with patch("plone.api.portal.show_message"):
            self.view.request.form = {}
            self.view.create_template_from_version()
            self.view.request.form = {"version_id": "missing", "template_title": "T"}
            with patch("zopyx.surveyjs.browser.survey_versions.IAnnotations", return_value=self.annotations):
                self.view.create_template_from_version()
            self.view.request.form = {"version_id": "v1", "template_title": "T"}
            with patch("zopyx.surveyjs.browser.survey_versions.IAnnotations", return_value=self.annotations), patch(
                "plone.api.user.has_permission", return_value=False
            ):
                self.view.create_template_from_version()
        self.assertGreaterEqual(self.view.request.response.redirect.call_count, 3)

    def test_create_template_copies_form_and_reports_creation_failure(self):
        template = MagicMock()
        template.absolute_url.return_value = "http://nohost/template"
        with patch("zopyx.surveyjs.browser.survey_versions.IAnnotations", return_value=self.annotations), patch(
            "plone.api.user.has_permission", return_value=True
        ), patch("plone.api.content.create", return_value=template), patch(
            "zopyx.surveyjs.browser.survey_versions.iterSchemata", return_value=[]
        ), patch("plone.api.portal.show_message"):
            self.view.create_template_from_version()
        self.assertIn('"pages": []', template.template_json)
        template.reindexObject.assert_called_once()

        with patch("zopyx.surveyjs.browser.survey_versions.IAnnotations", return_value=self.annotations), patch(
            "plone.api.user.has_permission", return_value=True
        ), patch("plone.api.content.create", side_effect=RuntimeError("create failed")), patch(
            "plone.api.portal.show_message"
        ):
            self.view.create_template_from_version()
        self.assertGreaterEqual(self.view.request.response.redirect.call_count, 2)


if __name__ == "__main__":
    unittest.main()
