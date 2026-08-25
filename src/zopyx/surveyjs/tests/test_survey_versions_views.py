from io import BytesIO
import unittest
from unittest.mock import MagicMock, patch

from zopyx.surveyjs.browser.survey_versions import SurveyVersions
from zopyx.surveyjs.constants import FORM_VERSIONS_KEY


class SurveyVersionsMethodTests(unittest.TestCase):
    def setUp(self):
        self.view = SurveyVersions.__new__(SurveyVersions)
        self.view.context = MagicMock()
        self.view.context.absolute_url.return_value = "http://nohost/survey"
        self.view.request = MagicMock()
        self.view.request.form = {}
        self.view.request.response.redirect.return_value = None

    def call_with_annotations(self, annotations, method, **form):
        self.view.request.form = form
        with (
            patch("zopyx.surveyjs.browser.survey_versions.IAnnotations", return_value=annotations),
            patch("plone.api.portal.show_message"),
        ):
            return method()

    def test_download_version_missing_id_redirects(self):
        result = self.call_with_annotations({}, self.view.download_version)
        self.assertIsNone(result)
        self.view.request.response.redirect.assert_called_once()

    def test_download_version_missing_entry_redirects(self):
        result = self.call_with_annotations(
            {FORM_VERSIONS_KEY: {}}, self.view.download_version, version_id="missing"
        )
        self.assertIsNone(result)
        self.view.request.response.redirect.assert_called_once()

    def test_toggle_version_lock_flips_state(self):
        annotations = {FORM_VERSIONS_KEY: {"v1": {"id": "v1", "locked": False}}}
        with patch.object(self.view, "_check_post_authenticator"):
            self.call_with_annotations(annotations, self.view.toggle_version_lock, version_id="v1")
        self.assertTrue(annotations[FORM_VERSIONS_KEY]["v1"]["locked"])

    def test_delete_version_rejects_locked_version(self):
        annotations = {FORM_VERSIONS_KEY: {"v1": {"id": "v1", "locked": True}}}
        with patch.object(self.view, "_check_post_authenticator"):
            self.call_with_annotations(annotations, self.view.delete_version, version_id="v1")
        self.assertIn("v1", annotations[FORM_VERSIONS_KEY])

    def test_upload_version_rejects_invalid_json(self):
        upload = BytesIO(b"not-json")
        with patch.object(self.view, "_check_post_authenticator"):
            self.call_with_annotations({}, self.view.upload_version, json_file=upload)
        self.view.request.response.redirect.assert_called_once()

    def test_view_version_json_returns_missing_error(self):
        self.call_with_annotations({}, self.view.view_version_json, version_id="missing")
        self.view.request.response.setHeader.assert_called_once_with(
            "content-type", "application/json"
        )


if __name__ == "__main__":
    unittest.main()
