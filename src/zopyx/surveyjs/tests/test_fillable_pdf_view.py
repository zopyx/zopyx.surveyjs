import unittest
from unittest.mock import MagicMock, patch

from zopyx.surveyjs.browser import fillable_pdf
from zopyx.surveyjs.browser.fillable_pdf import FillablePDFView


class FillablePDFViewTests(unittest.TestCase):
    def setUp(self):
        self.view = FillablePDFView.__new__(FillablePDFView)
        self.view.context = MagicMock()
        self.view.context.absolute_url.return_value = "http://nohost/survey"
        self.view.request = MagicMock()
        self.view.request.form = {}
        self.auth = patch.object(self.view, "_check_post_authenticator")
        self.auth.start()
        self.addCleanup(self.auth.stop)

    def test_pdf_properties_and_input_types(self):
        self.view.context.fillable_pdf = None
        self.assertFalse(self.view.has_fillable_pdf)
        self.assertIsNone(self.view.pdf_filename)
        self.assertEqual(self.view.pdf_content_type, "application/pdf")
        self.assertEqual(self.view.pdf_size, 0)
        for field_type, expected in (
            ("checkbox", "checkbox"),
            ("radiobuttongroup", "checkbox"),
            ("combobox", "select"),
            ("listbox", "select"),
            ("signature", "signature"),
            ("text", "text"),
        ):
            self.assertEqual(
                self.view._get_input_type_for_field({"type": field_type}), expected
            )

        pdf = MagicMock(data=b"pdf", filename="form.pdf", contentType="application/pdf")
        self.view.context.fillable_pdf = pdf
        self.assertTrue(self.view.has_fillable_pdf)
        self.assertEqual(self.view.pdf_filename, "form.pdf")
        self.assertEqual(self.view.pdf_size, 3)

    def test_extract_json_names_and_properties_recursively(self):
        form = {
            "pages": [
                {
                    "elements": [
                        {"type": "text", "name": "name", "inputType": "text"},
                        {"type": "panel", "name": "panel", "elements": [{"type": "checkbox", "name": "ok"}]},
                    ]
                }
            ]
        }
        self.assertEqual(self.view._extract_field_names_from_json(form), {"name", "panel", "ok"})
        self.assertEqual(
            self.view._extract_form_properties_from_json(form),
            [
                {"name": "name", "type": "text", "inputType": "text"},
                {"name": "ok", "type": "checkbox", "inputType": "—"},
            ],
        )
        with patch.object(self.view, "_get_latest_form_json", return_value=form):
            self.assertEqual([p["name"] for p in self.view.json_form_properties], ["name", "ok"])

    def test_pdf_fields_uses_inline_extraction_and_marks_json_matches(self):
        pdf = MagicMock(data=b"pdf")
        self.view.context.fillable_pdf = pdf
        with patch.object(
            self.view,
            "_extract_pdf_fields_inline",
            return_value=[{"name": "name", "type": "text"}, {"name": "other", "type": "text"}],
        ), patch.object(self.view, "_get_json_form_field_names", return_value={"name"}):
            with patch.object(fillable_pdf, "PRIVACYFORMS_PDF_AVAILABLE", False):
                fields = self.view.pdf_fields
        self.assertTrue(fields[0]["exists_in_json_form"])
        self.assertFalse(fields[1]["exists_in_json_form"])
        self.view.context.fillable_pdf = pdf
        with patch.object(self.view, "_extract_pdf_fields_inline", return_value=fields), patch.object(
            self.view, "_get_json_form_field_names", return_value={"name"}
        ), patch.object(fillable_pdf, "PRIVACYFORMS_PDF_AVAILABLE", False):
            typed = self.view.pdf_fields_with_input_types
        self.assertEqual(typed[0]["input_type"], "text")

    def test_validate_pdf_handles_empty_fields_invalid_and_valid(self):
        reader = MagicMock()
        reader.pages = [MagicMock()]
        with patch("zopyx.surveyjs.browser.fillable_pdf.PdfReader", return_value=reader):
            reader.get_fields.return_value = None
            valid, message = self.view._validate_fillable_pdf(b"pdf")
            self.assertFalse(valid)
            self.assertIn("fillable form fields", message)
            reader.get_fields.return_value = {"name": {}}
            valid, message = self.view._validate_fillable_pdf(b"pdf")
            self.assertTrue(valid)
            self.assertIn("1 form field", message)
        with patch(
            "zopyx.surveyjs.browser.fillable_pdf.PdfReader",
            side_effect=RuntimeError("bad pdf"),
        ):
            valid, message = self.view._validate_fillable_pdf(b"bad")
            self.assertFalse(valid)
            self.assertIn("Could not parse", message)

    def test_upload_pdf_rejects_missing_and_wrong_extension(self):
        with patch("plone.api.portal.show_message"):
            self.view.upload_pdf()
            self.view.request.form = {"pdf_file": MagicMock(filename="form.txt")}
            self.view.upload_pdf()
        self.assertEqual(self.view.request.response.redirect.call_count, 2)

    def test_upload_pdf_stores_valid_pdf_and_handles_validation_failure(self):
        pdf_file = MagicMock(filename="form.pdf")
        pdf_file.read.return_value = b"pdf"
        self.view.request.form = {"pdf_file": pdf_file}
        named_file = MagicMock(filename="form.pdf", data=b"pdf")
        with patch.object(self.view, "_validate_fillable_pdf", return_value=(True, "ok")), patch(
            "zopyx.surveyjs.browser.fillable_pdf.NamedBlobFile", return_value=named_file
        ), patch(
            "plone.api.portal.show_message"
        ):
            self.view.upload_pdf()
        self.assertEqual(self.view.context.fillable_pdf.filename, "form.pdf")
        invalid_file = MagicMock(filename="bad.pdf")
        invalid_file.read.return_value = b"pdf"
        self.view.request.form = {"pdf_file": invalid_file}
        with patch.object(self.view, "_validate_fillable_pdf", return_value=(False, "invalid")), patch(
            "plone.api.portal.show_message"
        ):
            self.view.upload_pdf()
        self.assertEqual(self.view.request.response.redirect.call_count, 2)

    def test_fill_pdf_rejects_unavailable_or_missing_template(self):
        with patch.object(fillable_pdf, "PYMUPDF_AVAILABLE", False), patch(
            "plone.api.portal.show_message"
        ):
            self.view.fill_pdf()
        with patch.object(fillable_pdf, "PYMUPDF_AVAILABLE", True), patch(
            "plone.api.portal.show_message"
        ):
            self.view.fill_pdf()
        self.assertEqual(self.view.request.response.redirect.call_count, 2)

    def test_fill_pdf_updates_text_checkbox_and_choice_widgets(self):
        pdf = MagicMock(data=b"pdf", filename="template.pdf")
        self.view.context.fillable_pdf = pdf
        self.view.request.form = {
            "name": "Alice",
            "consent": "yes",
            "country": "DE",
        }
        text = MagicMock(field_name="name", field_type_string="Text")
        checkbox = MagicMock(field_name="consent", field_type_string="Checkbox")
        checkbox.button_states.return_value = ["Yes"]
        choice = MagicMock(field_name="country", field_type_string="ComboBox")
        page = MagicMock()
        page.widgets.return_value = [text, checkbox, choice]
        doc = MagicMock()
        doc.__iter__.return_value = iter([page])
        doc.tobytes.return_value = b"filled-pdf"
        fake_fitz = MagicMock()
        fake_fitz.open.return_value = doc
        with patch.object(fillable_pdf, "PYMUPDF_AVAILABLE", True), patch.object(
            fillable_pdf, "fitz", fake_fitz, create=True
        ), patch("plone.api.portal.show_message"):
            self.view.fill_pdf()
        self.assertEqual(text.field_value, "Alice")
        self.assertTrue(checkbox.field_value)
        self.assertEqual(choice.field_value, "DE")
        doc.close.assert_called_once()
        self.view.request.response.write.assert_called_once_with(b"filled-pdf")
        self.view.request.response.setHeader.assert_any_call(
            "Content-Type", "application/pdf"
        )


if __name__ == "__main__":
    unittest.main()
