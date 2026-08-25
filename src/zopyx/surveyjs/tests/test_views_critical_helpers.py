import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from zopyx.surveyjs.browser.views import Views, _extract_json_object, _mask_storage_location, _run_external_validation
from zopyx.surveyjs.browser import views as views_module


class ViewsCoverageTests(unittest.TestCase):
    def make_view(self):
        view = Views.__new__(Views)
        view.context = MagicMock()
        view.context.absolute_url.return_value = "http://nohost/survey"
        view.context.max_payload_size_mb = 1
        view.request = MagicMock()
        view.request.form = {}
        view.request.response = MagicMock()
        view.request.get.return_value = "GET"
        view.request.get_header.return_value = None
        view.request.getHeader.return_value = None
        return view

    def test_json_storage_and_text_helpers(self):
        self.assertEqual(_extract_json_object('noise {"a": 1} trailing'), '{"a": 1}')
        self.assertIsNone(_extract_json_object("no json"))
        self.assertEqual(_mask_storage_location("zodb"), "Plone (ZODB)")
        masked = _mask_storage_location("postgresql://user:pw123@db.example/forms")
        self.assertTrue(masked.startswith("postgresql://user:"))
        self.assertIn("@db.example/forms", masked)
        self.assertEqual(_mask_storage_location("not a url"), "not a url")

        view = self.make_view()
        self.assertEqual(view._compact_metadata_value(""), ("—", ""))
        self.assertEqual(view._compact_metadata_value("short"), ("short", "short"))
        compact, full = view._compact_metadata_value("x" * 170)
        self.assertTrue(compact.endswith("..."))
        self.assertEqual(len(compact), 160)
        self.assertEqual(view._interpolate_text("Hello {name}", {"name": "A"}), "Hello A")
        self.assertEqual(view._interpolate_text("Hello {missing}", {}), "Hello {missing}")
        self.assertEqual(view._parse_json_loose('prefix {"ok": true} suffix'), {"ok": True})
        self.assertIsNone(view._get_converter_format("missing"))
        self.assertEqual(view._get_converter_format("json")["content_type"], "application/json")

    def test_field_value_text_and_id_fallbacks(self):
        view = self.make_view()
        obj = MagicMock()
        obj.value = ["a", "b"]
        field = MagicMock()
        with patch.object(views_module.ICollection, "providedBy", return_value=False), patch.object(
            views_module.IChoice, "providedBy", return_value=False
        ):
            self.assertEqual(view._survey_field_value_text(obj, "value", field), "a, b")
        obj.flag = True
        self.assertEqual(view._survey_field_value_text(obj, "flag", field), "Yes")
        obj.file = SimpleNamespace(filename="upload.txt")
        self.assertEqual(view._survey_field_value_text(obj, "file", field), "upload.txt")
        view.context.UID.side_effect = RuntimeError("no uid")
        view.context.getId.return_value = "survey-id"
        self.assertEqual(view._form_id(), "survey-id")

    def test_external_validation_missing_binary_and_exception(self):
        with patch.object(views_module, "run_data_validation", side_effect=FileNotFoundError):
            result = _run_external_validation({"pages": []}, {"a": 1}, "hash")
        self.assertEqual(result["reason"], "external_validator_missing")
        with patch.object(views_module, "run_data_validation", side_effect=RuntimeError("broken")):
            result = _run_external_validation({"pages": []}, {"a": 1}, "hash")
        self.assertEqual(result["reason"], "external_validator_error")

    def test_save_poll_rejects_missing_invalid_and_oversized_payloads(self):
        view = self.make_view()
        with patch.object(view, "_check_post_authenticator"), patch.object(
            views_module, "json_error"
        ) as error:
            view.save_poll()
            self.assertEqual(error.call_args.args[1], 400)
            view.request.form = {"pollResult": object()}
            view.save_poll()
            self.assertEqual(error.call_args.args[1], 400)
            view.request.form = {"pollResult": "{}"}
            view.request.getHeader.return_value = str(2 * 1024 * 1024)
            view.save_poll()
            self.assertEqual(error.call_args.args[1], 413)

    def test_save_poll_handles_invalid_json_and_cors_preflight(self):
        view = self.make_view()
        view.request.form = {"pollResult": "not-json"}
        with patch.object(view, "_check_post_authenticator"), patch.object(
            views_module, "json_error"
        ) as error:
            view.save_poll()
            self.assertEqual(error.call_args.args[2], "invalid_json")
        view.request.form = {"pollResult": "{}"}
        view.request.get_header.side_effect = lambda name: "https://app.example" if name == "Origin" else None
        with patch.object(view, "_check_post_authenticator"), patch(
            "zopyx.surveyjs.browser.embed_security.handle_cors_preflight", return_value=True
        ):
            self.assertIsNone(view.save_poll())


if __name__ == "__main__":
    unittest.main()
