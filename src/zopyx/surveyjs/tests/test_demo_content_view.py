import unittest
from unittest.mock import MagicMock, patch

from zopyx.surveyjs.browser.demo_content import DemoContent


class DemoContentViewTests(unittest.TestCase):
    def make_view(self):
        view = DemoContent.__new__(DemoContent)
        view.request = MagicMock()
        view.request.response = MagicMock()
        return view

    def test_ensure_private_handles_private_transition_and_failures(self):
        view = self.make_view()
        obj = MagicMock()
        with patch("plone.api.content.get_state", return_value="private"):
            self.assertTrue(view._ensure_private(obj))
        with patch("plone.api.content.get_state", return_value="published"), patch(
            "plone.api.content.get_transitions",
            return_value=[{"id": "retract"}],
            create=True,
        ), patch("plone.api.content.transition") as transition:
            self.assertTrue(view._ensure_private(obj))
            transition.assert_called_once_with(obj=obj, transition="retract")
        with patch("plone.api.content.get_state", side_effect=RuntimeError("workflow")):
            self.assertFalse(view._ensure_private(obj))
        with patch("plone.api.content.get_state", return_value="published"), patch(
            "plone.api.content.get_transitions", return_value=[], create=True
        ):
            self.assertFalse(view._ensure_private(obj))

    def test_generators_return_expected_survey_shapes(self):
        view = self.make_view()
        multilingual = view._generate_multilingual_demo_survey()
        surveyjs = view._generate_surveyjs_demo_survey()
        all_fields = view._generate_all_field_types_survey()
        for form in (multilingual, surveyjs, all_fields):
            self.assertIsInstance(form, dict)
            self.assertTrue(form.get("pages"))
        self.assertIn("locales", multilingual)
        self.assertTrue(any("elements" in page for page in all_fields["pages"]))

    def test_parsers_and_sample_loaders_handle_invalid_data(self):
        view = self.make_view()
        self.assertEqual(view._parse_iso_datetime(None), None)
        self.assertIsNotNone(view._parse_iso_datetime("2024-01-01T12:00:00Z"))
        self.assertIsNone(view._parse_iso_datetime("not-a-date"))
        with patch.object(view, "_find_forms_dir", return_value=None):
            self.assertIsNone(view._load_prefilled_form_json())
            self.assertEqual(view._load_sample_addresses(), [])

    def test_call_creates_demo_folder_and_reports_partial_errors(self):
        view = self.make_view()
        portal = MagicMock()
        demos = MagicMock()
        surveys = [MagicMock(), MagicMock(), MagicMock()]
        content = MagicMock()
        content.create.side_effect = [demos, *surveys]
        user = MagicMock()
        user.getId.return_value = "demo-user"
        with patch("plone.api.portal.get", return_value=portal), patch.object(
            portal, "get", return_value=None
        ), patch("plone.api.content.create", side_effect=[demos, *surveys]), patch(
            "plone.api.user.get_current", return_value=user
        ), patch.object(view, "_ensure_private"), patch.object(
            view, "_generate_multilingual_demo_survey", return_value={"pages": [], "locale": "en"}
        ), patch.object(view, "_generate_surveyjs_demo_survey", side_effect=RuntimeError("broken")), patch.object(
            view, "_create_prefilled_survey", return_value=(None, "missing fixture")
        ), patch.object(view, "_generate_all_field_types_survey", return_value={"pages": [{"elements": []}]}), patch.object(
            view, "_generate_demo_results"), patch.object(view, "_generate_demo_results_all_field_types"), patch(
            "zopyx.surveyjs.browser.demo_content.IAnnotations", return_value={}
        ), patch("zopyx.surveyjs.browser.demo_content.forms_service.save_form_version"), patch(
            "zopyx.surveyjs.browser.demo_content.json_response"
        ) as response:
            view()
        payload = response.call_args.args[1]
        self.assertEqual(payload["folder"], "demos")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(len(payload["errors"]), 2)


if __name__ == "__main__":
    unittest.main()
