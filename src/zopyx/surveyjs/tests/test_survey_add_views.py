from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock

from zopyx.surveyjs.browser.survey_add import SurveyAddView


class SurveyAddViewMethodTests(unittest.TestCase):
    def setUp(self):
        self.view = SurveyAddView.__new__(SurveyAddView)
        self.view._errors = []
        self.view._form_values = {}

    def test_form_values_and_safe_json_are_initialized(self):
        values = self.view.form_values
        self.assertEqual(values["actions"], ["store"])
        self.assertIn("survey_languages", self.view.initial_data_json)
        self.assertNotIn("</script>", SurveyAddView.html_safe_json({"x": "</script>"}))

    def test_extract_form_data_from_payload_and_raw_form(self):
        self.view.request = MagicMock()
        self.view.request.form = {"payload": '{"title":" A ","actions":["store"]}'}
        data, errors = self.view._extract_form_data()
        self.assertEqual(data["title"], " A ")
        self.assertEqual(data["actions"], ["store"])
        self.assertIsNone(data["effective"])
        self.assertEqual(errors, [])

        self.view.request.form = {"title": " Raw ", "description": " Desc "}
        data, errors = self.view._extract_form_data()
        self.assertEqual(data["title"], "Raw")
        self.assertEqual(data["description"], "Desc")
        self.assertEqual(errors, [])

    def test_extract_form_data_reports_invalid_json(self):
        self.view.request = MagicMock()
        self.view.request.form = {"payload": "not-json"}
        data, errors = self.view._extract_form_data()
        self.assertEqual(data["title"], "")
        self.assertEqual(len(errors), 1)

    def test_list_line_and_integer_normalization(self):
        self.assertEqual(self.view._ensure_list(None), [])
        self.assertEqual(self.view._ensure_list("store"), ["store"])
        self.assertEqual(self.view._ensure_list(["store", " ", 2]), ["store", "2"])
        self.assertEqual(self.view._ensure_list(3), ["3"])
        self.assertEqual(self.view._split_lines("a, b\nc"), ["a", "b", "c"])
        self.assertEqual(self.view._split_lines(["a", " b "]), ["a", "b"])
        self.assertEqual(self.view._coerce_int("3", 1), 3)
        self.assertEqual(self.view._coerce_int("bad", 1), 1)
        self.assertEqual(self.view._coerce_int(0, 1), 1)

    def test_build_survey_fields_normalizes_configuration(self):
        fields = self.view._build_survey_fields(
            {
                "title": "Title",
                "description": "Description",
                "actions": "mail",
                "post_endpoint_url": "",
                "email_cc": "a@example.com, b@example.com",
                "email_bcc": ["c@example.com"],
                "email_formats": ["text"],
                "survey_languages": "en",
                "max_payload_size_mb": "4",
                "trusted_access_ttl_hours": "24",
                "force_server_side_validation": False,
                "access_mode": "trusted",
                "embedding_mode": "iframe",
            }
        )
        self.assertEqual(fields["actions"], {"mail"})
        self.assertEqual(fields["email_cc"], ["a@example.com", "b@example.com"])
        self.assertEqual(fields["email_bcc"], ["c@example.com"])
        self.assertEqual(fields["max_payload_size_mb"], 4)
        self.assertFalse(fields["force_server_side_validation"])
        self.assertEqual(fields["survey_languages"], ["en"])

    def test_datetime_parse_and_format_handles_valid_invalid_and_boundaries(self):
        parsed = self.view._parse_datetime_value("2024-01-02 03:04Z")
        self.assertEqual(parsed.tzinfo, timezone.utc)
        self.assertIsNone(self.view._parse_datetime_value("bad"))
        self.assertIsNone(self.view._parse_datetime_value(""))
        self.assertEqual(
            self.view._format_datetime_value(datetime(2024, 1, 2, 3, 4)),
            "2024-01-02T03:04",
        )
        self.assertEqual(self.view._format_datetime_value("none"), "")
        self.assertEqual(self.view._format_datetime_value("1800-01-01"), "")
        self.assertEqual(self.view._format_datetime_value(None), "")

    def test_normalize_dublincore_dates_removes_shadow_attributes(self):
        survey = MagicMock()
        survey.effective = datetime(2024, 1, 1, tzinfo=timezone.utc)
        survey.expires = None
        self.view._normalize_dublincore_dates(survey)
        survey.setEffectiveDate.assert_called_once()

    def test_apply_effective_expires_sets_dates_and_reindexes(self):
        survey = MagicMock()
        self.view._apply_effective_expires(
            survey,
            {"effective": "2024-01-01", "expires": "2024-12-31"},
        )
        survey.setEffectiveDate.assert_called_once()
        survey.setExpirationDate.assert_called_once()
        survey.reindexObject.assert_called_once_with(idxs=["effective", "expires"])


if __name__ == "__main__":
    unittest.main()
