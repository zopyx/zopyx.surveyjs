from __future__ import annotations

import unittest
from unittest.mock import patch

from zopyx.surveyjs.browser.ai import AIView


class DummyResponse:
    def __init__(self) -> None:
        self.redirect_url = None

    def redirect(self, url):
        self.redirect_url = url
        return url


class DummyRequest:
    def __init__(self, form=None) -> None:
        self.form = form or {}
        self.response = DummyResponse()


class DummyContext:
    def __init__(self, annos=None) -> None:
        self._annos = annos if annos is not None else {}

    def absolute_url(self) -> str:
        return "http://nohost/plone/survey"


class DummyUpload:
    def __init__(self, filename: str, payload: bytes, content_type: str) -> None:
        self.name = filename  # Used by file_validation
        self.filename = filename
        self._payload = payload
        self.contentType = content_type
        self._position = 0

    def read(self, size=None):
        if size is None:
            data = self._payload[self._position:]
            self._position = len(self._payload)
            return data
        # For chunked reading
        data = self._payload[self._position:self._position + size]
        self._position += len(data)
        return data
    
    def seek(self, position):
        self._position = position


def _make_minimal_docx() -> bytes:
    """Create a minimal valid DOCX file for testing."""
    import zipfile
    import io
    
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Required files for DOCX
        zf.writestr('[Content_Types].xml', 
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>')
        zf.writestr('word/document.xml', 
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Test</w:t></w:r></w:p></w:body>'
            '</w:document>')
        zf.writestr('_rels/.rels',
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    
    buffer.seek(0)
    return buffer.read()


def _make_minimal_pdf() -> bytes:
    """Create a minimal valid PDF file for testing."""
    return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids []\n/Count 0\n>>\nendobj\nxref\n0 3\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\ntrailer\n<<\n/Size 3\n/Root 1 0 R\n>>\nstartxref\n116\n%%EOF"


def _make_minimal_odt() -> bytes:
    """Create a minimal valid ODT file for testing."""
    import zipfile
    import io
    
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('mimetype', 'application/vnd.oasis.opendocument.text')
        zf.writestr('content.xml', 
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0">'
            '<office:body><office:text><text:p xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">Test</text:p></office:text></office:body>'
            '</office:document-content>')
    
    buffer.seek(0)
    return buffer.read()


def _make_minimal_html() -> bytes:
    """Create a minimal valid HTML file for testing."""
    return b'<!DOCTYPE html><html><head><title>Test</title></head><body><p>Test</p></body></html>'


def _fake_annotations(context):
    return context._annos


class AIViewTests(unittest.TestCase):
    def _make_view(self, *, form=None, annos=None):
        view = AIView.__new__(AIView)
        view.context = DummyContext(annos=annos)
        view.request = DummyRequest(form=form)
        return view

    def test_build_pdf_to_survey_mapping_maps_pdf_id_to_survey_name(self) -> None:
        view = self._make_view()
        pdf_form_data = [
            {"name": "first_name", "label": "First Name", "type": "text"},
            {"name": "email", "label": "Email", "type": "text"},
        ]
        survey_json = {
            "pages": [
                {
                    "elements": [
                        {"type": "text", "name": "first_name", "title": "First Name"},
                        {"type": "text", "name": "mail", "title": "Email"},
                    ]
                }
            ]
        }

        mapping = view._build_pdf_to_survey_mapping(pdf_form_data, survey_json)

        self.assertEqual(mapping["pdf_field_count"], 2)
        self.assertEqual(mapping["survey_field_count"], 2)
        self.assertGreaterEqual(mapping["mapped_count"], 1)
        self.assertTrue(
            any(m["survey_name"] == "first_name" for m in mapping["mappings"])
        )

    @patch("zopyx.surveyjs.browser.services.rate_limit.RateLimitService")
    @patch("zopyx.surveyjs.browser.ai.Path.write_text")
    @patch("zopyx.surveyjs.browser.ai.plone.api.portal.show_message")
    @patch("zopyx.surveyjs.browser.ai.IAnnotations", side_effect=_fake_annotations)
    @patch(
        "zopyx.surveyjs.browser.ai.ai_service.load_ai_settings",
        return_value=("gpt-4o", "secret", None),
    )
    def test_upload_fillable_pdf_stores_internal_mapping(
        self, _settings, _annos, _show_message, _write_text, _rate_limit
    ) -> None:
        annos = {}
        upload = DummyUpload("form.pdf", _make_minimal_pdf(), "application/pdf")
        view = self._make_view(form={"document_file": upload}, annos=annos)
        generated = {"pages": [{"elements": [{"type": "text", "name": "first_name"}]}]}

        with patch.object(
            view,
            "_extract_pdf_form_data",
            return_value=(True, [{"name": "first_name"}], None),
        ):
            with patch.object(
                view, "_call_ai_conversion", return_value='{"pages": []}'
            ):
                with patch.object(
                    view, "_parse_generated_json", return_value=generated
                ):
                    result = view.upload_document()

        self.assertIn("/@@ai", result)
        self.assertEqual(annos[AIView.TEMP_FORM_ANNOTATION_KEY], generated)
        self.assertIn(AIView.TEMP_PDF_FIELD_MAPPING_ANNOTATION_KEY, annos)
        mapping = annos[AIView.TEMP_PDF_FIELD_MAPPING_ANNOTATION_KEY]
        self.assertIsInstance(mapping, dict)
        self.assertIn("mappings", mapping)

    @patch("zopyx.surveyjs.browser.services.rate_limit.RateLimitService")
    @patch("zopyx.surveyjs.browser.ai.Path.write_text")
    @patch("zopyx.surveyjs.browser.ai.plone.api.portal.show_message")
    @patch("zopyx.surveyjs.browser.ai.IAnnotations", side_effect=_fake_annotations)
    @patch(
        "zopyx.surveyjs.browser.ai.ai_service.load_ai_settings",
        return_value=("gpt-4o", "secret", None),
    )
    def test_upload_non_fillable_pdf_clears_internal_mapping(
        self, _settings, _annos, _show_message, _write_text, _rate_limit
    ) -> None:
        annos = {AIView.TEMP_PDF_FIELD_MAPPING_ANNOTATION_KEY: {"stale": True}}
        upload = DummyUpload("scan.pdf", _make_minimal_pdf(), "application/pdf")
        view = self._make_view(form={"document_file": upload}, annos=annos)
        generated = {"pages": [{"elements": [{"type": "text", "name": "a"}]}]}

        with patch.object(
            view, "_extract_pdf_form_data", return_value=(False, None, None)
        ):
            with patch.object(
                view, "_call_ai_conversion", return_value='{"pages": []}'
            ):
                with patch.object(
                    view, "_parse_generated_json", return_value=generated
                ):
                    view.upload_document()

        self.assertNotIn(AIView.TEMP_PDF_FIELD_MAPPING_ANNOTATION_KEY, annos)

    @patch("zopyx.surveyjs.browser.services.rate_limit.RateLimitService")
    @patch("zopyx.surveyjs.browser.ai.Path.write_text")
    @patch("zopyx.surveyjs.browser.ai.plone.api.portal.show_message")
    @patch("zopyx.surveyjs.browser.ai.IAnnotations", side_effect=_fake_annotations)
    @patch(
        "zopyx.surveyjs.browser.ai.ai_service.load_ai_settings",
        return_value=("gpt-4o", "secret", None),
    )
    def test_upload_non_pdf_clears_internal_mapping(
        self, _settings, _annos, _show_message, _write_text, _rate_limit
    ) -> None:
        annos = {AIView.TEMP_PDF_FIELD_MAPPING_ANNOTATION_KEY: {"stale": True}}
        upload = DummyUpload(
            "document.docx",
            _make_minimal_docx(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        view = self._make_view(form={"document_file": upload}, annos=annos)
        generated = {"pages": [{"elements": [{"type": "text", "name": "b"}]}]}

        with patch.object(view, "_call_ai_conversion", return_value='{"pages": []}'):
            with patch.object(view, "_parse_generated_json", return_value=generated):
                view.upload_document()

        self.assertNotIn(AIView.TEMP_PDF_FIELD_MAPPING_ANNOTATION_KEY, annos)

    @patch("zopyx.surveyjs.browser.ai.Path.write_text")
    @patch("zopyx.surveyjs.browser.ai.plone.api.portal.show_message")
    @patch("zopyx.surveyjs.browser.ai.IAnnotations", side_effect=_fake_annotations)
    @patch(
        "zopyx.surveyjs.browser.ai.ai_service.load_ai_settings",
        return_value=("gpt-4o", "secret", None),
    )
    def test_chat_refine_creates_temp_form_when_workspace_is_empty(
        self, _settings, _annos, _show_message, _write_text
    ) -> None:
        annos = {}
        view = self._make_view(
            form={"chat_prompt": "Create an event registration form."},
            annos=annos,
        )
        generated = {"pages": [{"elements": [{"type": "text", "name": "full_name"}]}]}

        with patch.object(
            view, "_call_ai_text_refinement", return_value='{"pages": []}'
        ):
            with patch.object(view, "_parse_generated_json", return_value=generated):
                result = view.chat_refine_temp_form()

        self.assertIn("/@@ai", result)
        self.assertEqual(annos[AIView.TEMP_FORM_ANNOTATION_KEY], generated)
        self.assertEqual(annos[AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY], [])
        self.assertNotIn(AIView.TEMP_PDF_FIELD_MAPPING_ANNOTATION_KEY, annos)

    @patch("zopyx.surveyjs.browser.ai.Path.write_text")
    @patch("zopyx.surveyjs.browser.ai.plone.api.portal.show_message")
    @patch("zopyx.surveyjs.browser.ai.IAnnotations", side_effect=_fake_annotations)
    @patch(
        "zopyx.surveyjs.browser.ai.ai_service.load_ai_settings",
        return_value=("gpt-4o", "secret", None),
    )
    def test_chat_refine_appends_history_when_workspace_has_form(
        self, _settings, _annos, _show_message, _write_text
    ) -> None:
        annos = {
            AIView.TEMP_FORM_ANNOTATION_KEY: {
                "pages": [{"elements": [{"type": "text", "name": "old_field"}]}]
            }
        }
        view = self._make_view(
            form={"chat_prompt": "Rename the field."},
            annos=annos,
        )
        refined = {"pages": [{"elements": [{"type": "text", "name": "new_field"}]}]}

        with patch.object(
            view, "_call_ai_text_refinement", return_value='{"pages": []}'
        ):
            with patch.object(view, "_parse_generated_json", return_value=refined):
                result = view.chat_refine_temp_form()

        self.assertIn("/@@ai", result)
        self.assertEqual(annos[AIView.TEMP_FORM_ANNOTATION_KEY], refined)
        self.assertEqual(len(annos[AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY]), 1)
        self.assertEqual(
            annos[AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY][0]["prompt"],
            "Rename the field.",
        )
