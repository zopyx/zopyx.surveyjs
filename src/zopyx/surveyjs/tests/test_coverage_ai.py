"""Coverage tests for the AI browser modules and shared HTTP helpers.

These tests drive the error, fallback and bookkeeping branches of

- ``browser/ai.py`` (``AIView``)
- ``browser/llm_models.py`` (``LLMModelsView``)
- ``browser/survey_template_views.py`` (``SurveyTemplateViewer``)
- ``browser/services/http.py`` (JSON response helpers)

that the existing suites do not reach. Everything is mocked, no network or
LLM calls happen and no Plone layer is required (the views are instantiated
directly with dummy contexts, as in ``test_ai.py``).
"""

from __future__ import annotations

import json
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from zopyx.surveyjs.browser.ai import AIView
from zopyx.surveyjs.browser.llm_models import LLMModelsView
from zopyx.surveyjs.browser.services import forms as forms_service
from zopyx.surveyjs.browser.services.http import (
    json_error,
    json_response,
    parse_json_body,
)
from zopyx.surveyjs.browser.survey_template_views import SurveyTemplateViewer
from zopyx.surveyjs.constants import FORM_VERSIONS_KEY

EMPTY_PROMPT_SETTINGS = {"before": "", "default": "", "after": ""}
AI_SETTINGS = {
    "provider": "installed",
    "model_name": "gpt-4o",
    "api_key": "secret",
    "api_url": None,
}
AI_URL = "http://nohost/plone/survey/@@ai"


class DummyResponse:
    def __init__(self) -> None:
        self.redirect_urls = []

    def redirect(self, url):
        self.redirect_urls.append(url)
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
    def __init__(self, filename: str, payload, content_type: str = "") -> None:
        self.filename = filename
        self._payload = payload
        self.contentType = content_type

    def read(self):
        return self._payload


class BrokenUpload:
    filename = "form.docx"
    contentType = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    def read(self):
        raise OSError("disk error")


def _fake_annotations(context):
    return context._annos


def _fake_pdf_module(service_cls):
    module = types.ModuleType("privacyforms_pdf")
    module.PDFFormService = service_cls
    return module


def _fake_llm_module(entries):
    module = types.ModuleType("llm")
    module.get_models_with_aliases = lambda: entries
    return module


class _ModelEntry:
    """Stand-in for ``llm.models_with_aliases.ModelWithAliases``."""

    def __init__(self, model, aliases=None, async_model=None) -> None:
        self.model = model
        self.aliases = set(aliases or ())
        self.async_model = async_model


def _fake_ai_response(text, *, callable_text=False):
    class FakeResponse:
        def __init__(self) -> None:
            self.text = (lambda: text) if callable_text else text

    return FakeResponse()


def _fake_model(text, *, callable_text=False):
    class FakeModel:
        def prompt(self, prompt):
            self.last_prompt = prompt
            return _fake_ai_response(text, callable_text=callable_text)

    return FakeModel()


@contextmanager
def _ai_settings(configured=True):
    """Patch the registry-backed AI settings with a fixed configuration."""
    with (
        patch(
            "zopyx.surveyjs.browser.ai.ai_service.load_ai_settings",
            return_value=AI_SETTINGS,
        ),
        patch(
            "zopyx.surveyjs.browser.ai.ai_service.is_configured",
            return_value=configured,
        ),
        patch(
            "zopyx.surveyjs.browser.ai.ai_service.load_prompt_settings",
            return_value=EMPTY_PROMPT_SETTINGS,
        ),
    ):
        yield


class AIViewCoverageTests(unittest.TestCase):
    def _make_view(self, *, form=None, annos=None):
        view = AIView.__new__(AIView)
        view.context = DummyContext(annos=annos)
        view.request = DummyRequest(form=form)
        return view

    def _annotations(self, annos):
        """Patch the annotation lookup to return a plain dict."""
        return patch(
            "zopyx.surveyjs.browser.ai.IAnnotations", side_effect=_fake_annotations
        )

    @staticmethod
    def _message(show_message):
        return show_message.call_args.args[0]

    # ------------------------------------------------------------------
    # _to_jsonable
    # ------------------------------------------------------------------

    def test_to_jsonable_handles_containers_bytes_and_broken_vars(self) -> None:
        view = self._make_view()

        # list/tuple/set branch
        self.assertEqual(
            view._to_jsonable([1, {"a": 2}, (3, 4)]),
            [1, {"a": 2}, [3, 4]],
        )

        class BytesSerializer:
            def json(self):
                return b'{"k": 7}'

        class StrSerializer:
            def to_json(self):
                return '{"s": "x"}'

        # bytes response is decoded, string response is parsed as JSON
        self.assertEqual(view._to_jsonable(BytesSerializer()), {"k": 7})
        self.assertEqual(view._to_jsonable(StrSerializer()), {"s": "x"})

        class BrokenMapping(dict):
            def items(self):
                raise RuntimeError("items broken")

        class BrokenVars:
            @property
            def __dict__(self):
                return BrokenMapping()

        # vars() succeeds but the recursive conversion blows up: the debug
        # logging must not swallow the object, it must fall back to str()
        rendered = view._to_jsonable(BrokenVars())
        self.assertIsInstance(rendered, str)
        self.assertIn("BrokenVars object at", rendered)

    # ------------------------------------------------------------------
    # temp form properties
    # ------------------------------------------------------------------

    def test_temp_form_json_pretty_and_history_items(self) -> None:
        annos = {}
        view = self._make_view(annos=annos)

        with self._annotations(annos):
            # no draft -> empty string
            self.assertEqual(view.temp_form_json_pretty, "")

            form = {"title": "Contact", "pages": [{"elements": []}]}
            annos[AIView.TEMP_FORM_ANNOTATION_KEY] = form
            pretty = view.temp_form_json_pretty
            self.assertEqual(json.loads(pretty), form)
            self.assertIn("\n", pretty)

            self.assertEqual(view.temp_history_items, [])
            annos[AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY] = [
                {"prompt": "  first  ", "form_json": {"a": 1}},
                {"prompt": "x" * 200, "form_json": {"b": 2}},
                {"form_json": {"c": 3}},
            ]
            items = view.temp_history_items

        self.assertEqual(len(items), 3)
        # newest first, 1-indexed step back
        self.assertEqual(
            items[0],
            {"history_index": 2, "step_back": 1, "prompt": "(no prompt)"},
        )
        self.assertEqual(items[1]["history_index"], 1)
        self.assertEqual(items[1]["step_back"], 2)
        self.assertEqual(items[1]["prompt"], "x" * 157 + "...")
        self.assertEqual(items[2]["history_index"], 0)
        self.assertEqual(items[2]["step_back"], 3)
        self.assertEqual(items[2]["prompt"], "first")

    # ------------------------------------------------------------------
    # _extract_pdf_form_data
    # ------------------------------------------------------------------

    def test_extract_pdf_form_data_reports_fields_and_deletes_temp_file(self) -> None:
        calls = {}

        class RecordingService:
            def has_form(self, path):
                calls["path"] = path
                return True

            def extract(self, path):
                calls["extracted"] = path
                return {"fields": [{"name": "first_name", "row_y": 10}]}

        view = self._make_view()
        with patch.dict(
            sys.modules, {"privacyforms_pdf": _fake_pdf_module(RecordingService)}
        ):
            has_form, form_data, error = view._extract_pdf_form_data(b"%PDF-1.7")

        self.assertTrue(has_form)
        self.assertIsNone(error)
        self.assertEqual(form_data, {"fields": [{"name": "first_name", "row_y": 10}]})
        self.assertEqual(calls["extracted"], calls["path"])
        self.assertTrue(calls["path"].endswith(".pdf"))
        # the temporary file is removed in the finally block
        self.assertFalse(Path(calls["path"]).exists())

    def test_extract_pdf_form_data_without_fillable_form(self) -> None:
        class EmptyService:
            def has_form(self, path):
                return False

            def extract(self, path):
                raise AssertionError("extract() must not run without a form")

        view = self._make_view()
        with patch.dict(
            sys.modules, {"privacyforms_pdf": _fake_pdf_module(EmptyService)}
        ):
            has_form, form_data, error = view._extract_pdf_form_data(b"%PDF-1.7")

        self.assertIs(has_form, False)
        self.assertIsNone(form_data)
        self.assertIsNone(error)

    def test_extract_pdf_form_data_reports_missing_library_and_failures(self) -> None:
        view = self._make_view()

        with patch.dict(sys.modules, {"privacyforms_pdf": None}):
            has_form, form_data, error = view._extract_pdf_form_data(b"%PDF")
        self.assertIsNone(has_form)
        self.assertIsNone(form_data)
        self.assertIn("privacyforms PDF extractor not available", error)

        class BrokenService:
            def has_form(self, path):
                raise RuntimeError("corrupt pdf")

        with patch.dict(
            sys.modules, {"privacyforms_pdf": _fake_pdf_module(BrokenService)}
        ):
            result = view._extract_pdf_form_data(b"%PDF")
        self.assertEqual(result, (None, None, "corrupt pdf"))

    def test_extract_pdf_form_data_survives_unlink_failure(self) -> None:
        calls = {}

        class RecordingService:
            def has_form(self, path):
                calls["path"] = path
                return True

            def extract(self, path):
                return {"fields": []}

        view = self._make_view()
        with (
            patch.dict(
                sys.modules, {"privacyforms_pdf": _fake_pdf_module(RecordingService)}
            ),
            patch(
                "zopyx.surveyjs.browser.ai.Path.unlink",
                side_effect=RuntimeError("locked"),
            ),
        ):
            has_form, form_data, error = view._extract_pdf_form_data(b"%PDF-1.7")

        self.assertTrue(has_form)
        self.assertEqual(form_data, {"fields": []})
        self.assertIsNone(error)
        # the failed cleanup left the file behind - remove it ourselves
        leftovers = Path(calls["path"])
        self.assertTrue(leftovers.exists())
        leftovers.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # element collection / mapping
    # ------------------------------------------------------------------

    def test_collect_survey_elements_skips_non_dicts_and_walks_cells(self) -> None:
        view = self._make_view()
        survey_json = {
            "pages": [
                {
                    "elements": [
                        "not-a-dict",
                        {
                            "type": "text",
                            "name": "outer",
                            "elements": [{"type": "text", "title": "Inner title"}],
                        },
                    ]
                },
                {
                    "elements": [
                        {
                            "type": "matrix",
                            "name": "grid",
                            "cells": [[{"type": "text", "name": "cell_field"}]],
                        }
                    ]
                },
            ],
            "elements": [{"type": "text", "name": "top_level"}],
        }

        elements = view._collect_survey_elements(survey_json)
        names = [element["survey_name"] for element in elements]

        self.assertEqual(names, ["outer", "", "grid", "cell_field", "top_level"])
        self.assertEqual(elements[1]["survey_title"], "Inner title")

    def test_build_pdf_to_survey_mapping_uses_medium_confidence_matches(self) -> None:
        view = self._make_view()
        pdf_form_data = [
            {"name": "unknown_id_1", "label": "Contact Mail", "type": "text"},
            {"name": "Subject Line", "label": "unrelated", "type": "text"},
        ]
        survey_json = {
            "pages": [
                {
                    "elements": [
                        {"type": "text", "name": "contactmail", "title": ""},
                        {"type": "text", "name": "other", "title": "Subject Line"},
                    ]
                }
            ]
        }

        mapping = view._build_pdf_to_survey_mapping(pdf_form_data, survey_json)

        self.assertEqual(mapping["pdf_field_count"], 2)
        self.assertEqual(mapping["survey_field_count"], 2)
        self.assertEqual(mapping["mapped_count"], 2)
        by_id = {m["pdf_field_id"]: m for m in mapping["mappings"]}
        self.assertEqual(by_id["unknown_id_1"]["matched_by"], "pdf_label->survey_name")
        self.assertEqual(by_id["unknown_id_1"]["confidence"], "medium")
        self.assertEqual(by_id["unknown_id_1"]["survey_name"], "contactmail")
        self.assertEqual(by_id["Subject Line"]["matched_by"], "pdf_id->survey_title")
        self.assertEqual(by_id["Subject Line"]["confidence"], "medium")
        self.assertEqual(by_id["Subject Line"]["survey_title"], "Subject Line")

    # ------------------------------------------------------------------
    # AI plumbing
    # ------------------------------------------------------------------

    def test_prepare_ai_model_delegates_to_service(self) -> None:
        view = self._make_view()
        with patch(
            "zopyx.surveyjs.browser.ai.ai_service.build_llm_model",
            return_value="model",
        ) as build:
            self.assertEqual(view._prepare_ai_model(AI_SETTINGS), "model")
        build.assert_called_once_with(AI_SETTINGS)

    def test_call_ai_conversion_and_text_refinement(self) -> None:
        view = self._make_view()
        model = MagicMock()
        helper = MagicMock()
        helper.prompt_with_attachment.return_value = "attachment-payload"

        with (
            patch.object(view, "_prepare_ai_model", return_value=model) as prepare,
            patch(
                "zopyx.surveyjs.browser.ai.ai_service.get_ai_helper",
                return_value=helper,
            ),
        ):
            result = view._call_ai_conversion(
                "prompt", "/tmp/upload.pdf", "application/pdf", AI_SETTINGS
            )
            # MagicMock attributes are callable, so .text() is invoked
            plain = view._call_ai_text_refinement("refine", AI_SETTINGS)

        self.assertEqual(result, "attachment-payload")
        self.assertIs(plain, model.prompt.return_value.text.return_value)
        model.prompt.assert_called_with("refine")
        prepare.assert_called_with(AI_SETTINGS)
        helper.prompt_with_attachment.assert_called_once_with(
            model=model,
            prompt="prompt",
            file_path="/tmp/upload.pdf",
            mime_type="application/pdf",
        )

        # .text is used directly when it is not callable
        with patch.object(view, "_prepare_ai_model") as prepare:
            prepare.side_effect = [
                _fake_model("called", callable_text=True),
                _fake_model("plain", callable_text=False),
            ]
            self.assertEqual(
                view._call_ai_text_refinement("a", AI_SETTINGS),
                "called",
            )
            self.assertEqual(
                view._call_ai_text_refinement("b", AI_SETTINGS),
                "plain",
            )

    def test_parse_generated_json_handles_every_payload_shape(self) -> None:
        view = self._make_view()

        self.assertEqual(view._parse_generated_json(b'{"a": 1}'), {"a": 1})
        self.assertEqual(view._parse_generated_json('  {"b": 2}  '), {"b": 2})
        self.assertEqual(view._parse_generated_json({"c": 3}), {"c": 3})
        self.assertEqual(view._parse_generated_json([1, 2]), [1, 2])
        # non str/bytes/dict/list payloads are stringified first
        self.assertEqual(view._parse_generated_json("  42  "), 42)
        self.assertEqual(view._parse_generated_json(42), 42)

        with self.assertRaises(ValueError) as ctx:
            view._parse_generated_json("   ")
        self.assertEqual(str(ctx.exception), "AI response is empty.")

        # JSON buried in prose/code fences is extracted
        self.assertEqual(
            view._parse_generated_json(
                'Sure, here you go:\n```json\n{"d": 4}\n```\nDone.'
            ),
            {"d": 4},
        )

        with self.assertRaises(json.JSONDecodeError):
            view._parse_generated_json("{not json")

    # ------------------------------------------------------------------
    # upload_document
    # ------------------------------------------------------------------

    def test_upload_document_rejects_missing_file_and_unsupported_type(self) -> None:
        views = []
        with patch(
            "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
        ) as show_message:
            view = self._make_view(form={})
            views.append(view)
            self.assertEqual(view.upload_document(), AI_URL)
            self.assertEqual(
                self._message(show_message),
                "No file uploaded. Please upload a file.",
            )

            view = self._make_view(
                form={"document_file": DummyUpload("", b"x", "application/pdf")}
            )
            views.append(view)
            self.assertEqual(view.upload_document(), AI_URL)
            self.assertEqual(
                self._message(show_message), "Uploaded file has no filename."
            )

            view = self._make_view(
                form={"document_file": DummyUpload("evil.exe", b"x", "")}
            )
            views.append(view)
            self.assertEqual(view.upload_document(), AI_URL)
            self.assertIn(
                "Unsupported file type. Allowed file types: PDF, DOCX, ODT, HTML.",
                self._message(show_message),
            )
            self.assertIn("received extension=.exe", self._message(show_message))

        for view in views:
            self.assertEqual(view.request.response.redirect_urls, [AI_URL])

    def test_upload_document_reports_read_errors_and_unconfigured_ai(self) -> None:
        annos = {}
        with patch(
            "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
        ) as show_message:
            view = self._make_view(form={"document_file": BrokenUpload()}, annos=annos)
            self.assertEqual(view.upload_document(), AI_URL)
            self.assertEqual(self._message(show_message), "Upload failed: disk error")

            view = self._make_view(
                form={"document_file": DummyUpload("form.docx", b"data", "x")},
                annos=annos,
            )
            with (
                self._annotations(annos),
                patch(
                    "zopyx.surveyjs.browser.ai.ai_service.load_ai_settings",
                    return_value=AI_SETTINGS,
                ),
                patch(
                    "zopyx.surveyjs.browser.ai.ai_service.is_configured",
                    return_value=False,
                ),
            ):
                self.assertEqual(view.upload_document(), AI_URL)

        self.assertIn(
            "AI model not configured. Configure an AI model in Forms settings "
            "before using AI upload.",
            self._message(show_message),
        )
        self.assertNotIn(AIView.TEMP_FORM_ANNOTATION_KEY, annos)

    def test_upload_document_derives_extension_and_reports_pdf_details(self) -> None:
        annos = {}
        generated = {"pages": [{"elements": [{"type": "text", "name": "a"}]}]}
        pdf_fields = [{"name": "a", "label": "A"}]
        upload = DummyUpload("document", b"%PDF-1.7 body", "application/pdf; q=1")

        view = self._make_view(form={"document_file": upload}, annos=annos)
        with (
            patch("zopyx.surveyjs.browser.ai.Path.write_text") as write_text,
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
            patch(
                "zopyx.surveyjs.browser.ai.ai_service.load_ai_settings",
                return_value=AI_SETTINGS,
            ),
            patch(
                "zopyx.surveyjs.browser.ai.ai_service.is_configured",
                return_value=True,
            ),
            patch.object(
                view,
                "_extract_pdf_form_data",
                return_value=(True, pdf_fields, "no /AcroForm dictionary"),
            ),
            patch.object(view, "_call_ai_conversion", return_value='{"pages": []}'),
            patch.object(view, "_parse_generated_json", return_value=generated),
        ):
            result = view.upload_document()

        self.assertEqual(result, AI_URL)
        message = self._message(show_message)
        size = len(b"%PDF-1.7 body")
        self.assertIn(f"AI upload succeeded for document ({size} bytes).", message)
        self.assertIn("Fillable PDF form detected.", message)
        self.assertIn("Form extraction note: no /AcroForm dictionary", message)
        self.assertEqual(annos[AIView.TEMP_FORM_ANNOTATION_KEY], generated)
        self.assertEqual(annos[AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY], [])
        mapping = annos[AIView.TEMP_PDF_FIELD_MAPPING_ANNOTATION_KEY]
        self.assertEqual(mapping["pdf_field_count"], 1)
        self.assertEqual(mapping["mapped_count"], 1)
        self.assertEqual(mapping["mappings"][0]["survey_name"], "a")
        write_text.assert_called_once()
        self.assertEqual(json.loads(write_text.call_args.args[0]), generated)

    def test_upload_document_encodes_text_payloads_and_reports_ai_failure(self) -> None:
        annos = {}
        generated = {"pages": []}
        upload = DummyUpload("form.docx", "<html>text</html>", "application/x-any")

        view = self._make_view(form={"document_file": upload}, annos=annos)
        with (
            patch("zopyx.surveyjs.browser.ai.Path.write_text"),
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
            patch(
                "zopyx.surveyjs.browser.ai.ai_service.load_ai_settings",
                return_value=AI_SETTINGS,
            ),
            patch(
                "zopyx.surveyjs.browser.ai.ai_service.is_configured",
                return_value=True,
            ),
            patch.object(view, "_call_ai_conversion", return_value="payload"),
            patch.object(view, "_parse_generated_json", return_value=generated),
        ):
            view.upload_document()

        size = len("<html>text</html>".encode("utf-8"))
        self.assertIn(
            f"AI upload succeeded for form.docx ({size} bytes).",
            self._message(show_message),
        )
        self.assertEqual(annos[AIView.TEMP_FORM_ANNOTATION_KEY], generated)

        # conversion error -> no draft is stored, the error is reported
        annos.clear()
        view = self._make_view(
            form={"document_file": DummyUpload("form.docx", b"data", "x")},
            annos=annos,
        )
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
            patch(
                "zopyx.surveyjs.browser.ai.ai_service.load_ai_settings",
                return_value=AI_SETTINGS,
            ),
            patch(
                "zopyx.surveyjs.browser.ai.ai_service.is_configured",
                return_value=True,
            ),
            patch.object(
                view, "_call_ai_conversion", side_effect=RuntimeError("model down")
            ),
        ):
            result = view.upload_document()

        self.assertEqual(result, AI_URL)
        self.assertEqual(
            self._message(show_message), "AI conversion failed: model down"
        )
        self.assertNotIn(AIView.TEMP_FORM_ANNOTATION_KEY, annos)

    # ------------------------------------------------------------------
    # version bookkeeping actions
    # ------------------------------------------------------------------

    def test_store_temp_as_version_requires_a_draft(self) -> None:
        annos = {}
        view = self._make_view(annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
        ):
            result = view.store_temp_as_version()

        self.assertEqual(result, AI_URL)
        self.assertEqual(
            self._message(show_message),
            "No temporary AI form is available to store.",
        )
        self.assertNotIn(FORM_VERSIONS_KEY, annos)

    def test_store_temp_as_version_persists_and_clears_the_draft(self) -> None:
        draft = {"pages": [{"elements": [{"type": "text", "name": "a"}]}]}
        annos = {AIView.TEMP_FORM_ANNOTATION_KEY: draft}
        view = self._make_view(annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.user.get_current"
            ) as get_current,
        ):
            get_current.return_value.getId.return_value = "tester"
            result = view.store_temp_as_version()

        self.assertEqual(result, AI_URL)
        self.assertNotIn(AIView.TEMP_FORM_ANNOTATION_KEY, annos)
        self.assertEqual(annos[AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY], [])
        versions = forms_service.list_form_versions(annos)
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["form_json"], draft)
        self.assertEqual(versions[0]["user"], "tester")
        self.assertIs(versions[0]["locked"], False)
        self.assertEqual(
            self._message(show_message),
            f"Stored as new version {versions[0]['id']}.",
        )

        # a failing save keeps the draft and reports the error
        annos = {AIView.TEMP_FORM_ANNOTATION_KEY: draft}
        view = self._make_view(annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.user.get_current"
            ) as get_current,
            patch(
                "zopyx.surveyjs.browser.ai.forms_service.save_form_version",
                side_effect=RuntimeError("zodb gone"),
            ),
        ):
            get_current.return_value.getId.return_value = "tester"
            self.assertEqual(view.store_temp_as_version(), AI_URL)

        self.assertEqual(
            self._message(show_message), "Failed to store form version: zodb gone"
        )
        self.assertEqual(annos[AIView.TEMP_FORM_ANNOTATION_KEY], draft)

    def test_copy_latest_version_to_temp_covers_all_outcomes(self) -> None:
        annos = {}
        view = self._make_view(annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
        ):
            self.assertEqual(view.copy_latest_version_to_temp(), AI_URL)
        self.assertEqual(
            self._message(show_message), "No persisted form versions found to copy."
        )

        # latest version without a JSON object
        forms_service.save_form_version(annos, "not-a-dict", "tester")
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
        ):
            self.assertEqual(view.copy_latest_version_to_temp(), AI_URL)
        self.assertEqual(
            self._message(show_message),
            "Latest version has no valid JSON object to copy.",
        )

        # newest version wins and lands in the temp annotations
        latest = forms_service.save_form_version(
            annos, {"pages": [{"elements": []}]}, "tester"
        )
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
        ):
            self.assertEqual(view.copy_latest_version_to_temp(), AI_URL)
        self.assertEqual(annos[AIView.TEMP_FORM_ANNOTATION_KEY], latest["form_json"])
        self.assertEqual(annos[AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY], [])
        self.assertEqual(
            self._message(show_message),
            f"Copied latest version {latest['id']} into temporary AI storage.",
        )

    def test_clear_temp_storage_removes_draft_and_history(self) -> None:
        annos = {
            AIView.TEMP_FORM_ANNOTATION_KEY: {"pages": []},
            AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY: [{"prompt": "p"}],
        }
        view = self._make_view(annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
        ):
            self.assertEqual(view.clear_temp_storage(), AI_URL)

        self.assertNotIn(AIView.TEMP_FORM_ANNOTATION_KEY, annos)
        self.assertEqual(annos[AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY], [])
        self.assertEqual(self._message(show_message), "Temporary AI storage cleared.")

        # works on an already empty workspace
        with (
            patch("zopyx.surveyjs.browser.ai.plone.api.portal.show_message"),
            self._annotations(annos),
        ):
            self.assertEqual(view.clear_temp_storage(), AI_URL)
        self.assertEqual(annos, {AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY: []})

    # ------------------------------------------------------------------
    # chat_refine_temp_form
    # ------------------------------------------------------------------

    def test_chat_refine_requires_prompt_and_configuration(self) -> None:
        annos = {}
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
        ):
            view = self._make_view(form={"chat_prompt": "   "}, annos=annos)
            self.assertEqual(view.chat_refine_temp_form(), AI_URL)
        self.assertEqual(
            self._message(show_message),
            "Please enter a prompt for AI refinement.",
        )

        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
            patch(
                "zopyx.surveyjs.browser.ai.ai_service.load_ai_settings",
                return_value=AI_SETTINGS,
            ),
            patch(
                "zopyx.surveyjs.browser.ai.ai_service.load_prompt_settings",
                return_value=EMPTY_PROMPT_SETTINGS,
            ),
            patch(
                "zopyx.surveyjs.browser.ai.ai_service.is_configured",
                return_value=False,
            ),
        ):
            view = self._make_view(form={"chat_prompt": "Create a form"}, annos=annos)
            self.assertEqual(view.chat_refine_temp_form(), AI_URL)
        self.assertEqual(
            self._message(show_message),
            "AI model not configured. Configure an AI model in Forms settings.",
        )
        self.assertNotIn(AIView.TEMP_FORM_ANNOTATION_KEY, annos)

    def test_chat_refine_reports_failure_for_creation_and_refinement(self) -> None:
        # empty workspace -> draft creation
        annos = {}
        view = self._make_view(form={"chat_prompt": "Create"}, annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
            _ai_settings(),
            patch.object(
                view, "_call_ai_text_refinement", side_effect=RuntimeError("llm down")
            ),
        ):
            self.assertEqual(view.chat_refine_temp_form(), AI_URL)
        self.assertEqual(
            self._message(show_message), "AI draft creation failed: llm down"
        )

        # existing draft -> refinement
        existing = {"pages": [{"elements": []}]}
        annos = {AIView.TEMP_FORM_ANNOTATION_KEY: existing}
        view = self._make_view(form={"chat_prompt": "Improve"}, annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
            _ai_settings(),
            patch.object(
                view, "_call_ai_text_refinement", side_effect=RuntimeError("llm down")
            ),
        ):
            self.assertEqual(view.chat_refine_temp_form(), AI_URL)
        self.assertEqual(self._message(show_message), "AI refinement failed: llm down")
        self.assertEqual(annos[AIView.TEMP_FORM_ANNOTATION_KEY], existing)

    def test_chat_refine_rebuilds_and_trims_the_history(self) -> None:
        current = {"pages": [{"elements": [{"type": "text", "name": "old"}]}]}
        refined = {"pages": [{"elements": [{"type": "text", "name": "new"}]}]}
        history = [
            {"prompt": f"p{index}", "form_json": {"index": index}} for index in range(5)
        ]
        annos = {
            AIView.TEMP_FORM_ANNOTATION_KEY: current,
            AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY: history,
        }
        view = self._make_view(form={"chat_prompt": "Rename"}, annos=annos)
        with (
            patch("zopyx.surveyjs.browser.ai.Path.write_text") as write_text,
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
            _ai_settings(),
            patch.object(view, "_call_ai_text_refinement", return_value="payload"),
            patch.object(view, "_parse_generated_json", return_value=refined),
        ):
            self.assertEqual(view.chat_refine_temp_form(), AI_URL)

        self.assertEqual(
            self._message(show_message),
            "AI refinement applied to temporary form.",
        )
        kept = annos[AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY]
        # the oldest entry is dropped, the previous draft is appended
        self.assertEqual(
            [entry["prompt"] for entry in kept], ["p1", "p2", "p3", "p4", "Rename"]
        )
        self.assertEqual(kept[-1]["form_json"], current)
        self.assertEqual(annos[AIView.TEMP_FORM_ANNOTATION_KEY], refined)
        self.assertNotIn(AIView.TEMP_PDF_FIELD_MAPPING_ANNOTATION_KEY, annos)
        self.assertEqual(json.loads(write_text.call_args.args[0]), refined)

        # a non-list history annotation is replaced by a fresh list
        annos = {
            AIView.TEMP_FORM_ANNOTATION_KEY: current,
            AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY: "broken",
        }
        view = self._make_view(form={"chat_prompt": "First real step"}, annos=annos)
        with (
            patch("zopyx.surveyjs.browser.ai.Path.write_text"),
            patch("zopyx.surveyjs.browser.ai.plone.api.portal.show_message"),
            self._annotations(annos),
            _ai_settings(),
            patch.object(view, "_call_ai_text_refinement", return_value="payload"),
            patch.object(view, "_parse_generated_json", return_value=refined),
        ):
            view.chat_refine_temp_form()

        self.assertEqual(
            annos[AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY],
            [{"prompt": "First real step", "form_json": current}],
        )

    # ------------------------------------------------------------------
    # history restore / delete
    # ------------------------------------------------------------------

    def _history(self):
        return [
            {"prompt": "p0", "form_json": {"step": 0}},
            {"prompt": "p1", "form_json": {"step": 1}},
            {"prompt": "p2", "form_json": {"step": 2}},
        ]

    def test_restore_temp_history_step_rejects_bad_input(self) -> None:
        annos = {AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY: self._history()}
        view = self._make_view(form={"history_index": "abc"}, annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
        ):
            self.assertEqual(view.restore_temp_history_step(), AI_URL)
        self.assertEqual(self._message(show_message), "Invalid history step.")

        view = self._make_view(form={"history_index": "0"}, annos={})
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations({}),
        ):
            self.assertEqual(view.restore_temp_history_step(), AI_URL)
        self.assertEqual(self._message(show_message), "No temporary history available.")

        annos = {AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY: self._history()}
        view = self._make_view(form={"history_index": "5"}, annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
        ):
            self.assertEqual(view.restore_temp_history_step(), AI_URL)
        self.assertEqual(
            self._message(show_message), "Selected history step is out of range."
        )

        annos = {AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY: [{"prompt": "p0"}]}
        view = self._make_view(form={"history_index": "0"}, annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
        ):
            self.assertEqual(view.restore_temp_history_step(), AI_URL)
        self.assertEqual(
            self._message(show_message),
            "Selected history step has no valid form JSON.",
        )
        self.assertNotIn(AIView.TEMP_FORM_ANNOTATION_KEY, annos)

    def test_restore_temp_history_step_restores_and_truncates_history(self) -> None:
        history = self._history()
        annos = {
            AIView.TEMP_FORM_ANNOTATION_KEY: {"step": 2},
            AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY: history,
        }
        view = self._make_view(form={"history_index": "1"}, annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
        ):
            self.assertEqual(view.restore_temp_history_step(), AI_URL)

        self.assertEqual(annos[AIView.TEMP_FORM_ANNOTATION_KEY], {"step": 1})
        self.assertEqual(annos[AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY], history[:1])
        self.assertEqual(
            self._message(show_message),
            "Restored temporary form to 2 step(s) back.",
        )

    def test_delete_temp_history_step_rejects_bad_input(self) -> None:
        annos = {AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY: self._history()}
        view = self._make_view(form={"history_index": "1.5"}, annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
        ):
            self.assertEqual(view.delete_temp_history_step(), AI_URL)
        self.assertEqual(self._message(show_message), "Invalid history step.")
        self.assertEqual(
            annos[AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY], self._history()
        )

        view = self._make_view(form={"history_index": "0"}, annos={})
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations({}),
        ):
            self.assertEqual(view.delete_temp_history_step(), AI_URL)
        self.assertEqual(self._message(show_message), "No temporary history available.")

        annos = {AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY: self._history()}
        view = self._make_view(form={"history_index": "7"}, annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
        ):
            self.assertEqual(view.delete_temp_history_step(), AI_URL)
        self.assertEqual(
            self._message(show_message), "Selected history step is out of range."
        )

    def test_delete_temp_history_step_drops_that_and_later_entries(self) -> None:
        history = self._history()
        annos = {AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY: history}
        view = self._make_view(form={"history_index": "1"}, annos=annos)
        with (
            patch(
                "zopyx.surveyjs.browser.ai.plone.api.portal.show_message"
            ) as show_message,
            self._annotations(annos),
        ):
            self.assertEqual(view.delete_temp_history_step(), AI_URL)

        self.assertEqual(annos[AIView.TEMP_FORM_HISTORY_ANNOTATION_KEY], history[:1])
        self.assertEqual(self._message(show_message), "Deleted 2 history item(s).")
        # the current draft is untouched by a history delete
        self.assertNotIn(AIView.TEMP_FORM_ANNOTATION_KEY, annos)


class LLMModelsViewCoverageTests(unittest.TestCase):
    def test_call_renders_the_index_template(self) -> None:
        view = LLMModelsView.__new__(LLMModelsView)
        with patch.object(LLMModelsView, "index", MagicMock(return_value="RENDERED")):
            self.assertEqual(view(), "RENDERED")

    def test_get_models_sorts_and_skips_entries_without_a_model(self) -> None:
        class StreamedModel:
            model_id = "Zeta"
            can_stream = True
            supports_schema = True
            supports_tools = False
            attachment_types = {"image/png", "application/pdf"}

        class MinimalModel:
            model_id = "alpha"

        async_model = object()
        entries = [
            _ModelEntry(StreamedModel(), {"b", "a"}),
            _ModelEntry(None, {"ignored"}),
            _ModelEntry(MinimalModel(), set(), async_model),
        ]

        view = LLMModelsView.__new__(LLMModelsView)
        with patch.dict(sys.modules, {"llm": _fake_llm_module(entries)}):
            models = view.get_models()

        self.assertEqual([model["model_id"] for model in models], ["alpha", "Zeta"])
        alpha, zeta = models
        self.assertEqual(zeta["aliases"], ["a", "b"])
        self.assertIs(zeta["can_stream"], True)
        self.assertIs(zeta["supports_schema"], True)
        self.assertIs(zeta["supports_tools"], False)
        self.assertEqual(zeta["attachment_types"], ["application/pdf", "image/png"])
        self.assertIs(zeta["is_async"], False)
        self.assertEqual(zeta["class_name"], "StreamedModel")
        self.assertEqual(alpha["aliases"], [])
        self.assertEqual(alpha["attachment_types"], [])
        self.assertIs(alpha["can_stream"], False)
        self.assertIs(alpha["is_async"], True)
        self.assertEqual(alpha["class_name"], "MinimalModel")

    def test_llm_library_presence_is_reported_and_absence_tolerated(self) -> None:
        view = LLMModelsView.__new__(LLMModelsView)
        with patch.dict(sys.modules, {"llm": _fake_llm_module([])}):
            self.assertIs(view.has_llm(), True)
            self.assertEqual(view.get_models(), [])
        with patch.dict(sys.modules, {"llm": None}):
            self.assertIs(view.has_llm(), False)
            self.assertEqual(view.get_models(), [])


class SurveyTemplateViewerCoverageTests(unittest.TestCase):
    def _make_view(self, template_json):
        view = SurveyTemplateViewer.__new__(SurveyTemplateViewer)
        view.context = MagicMock()
        view.context.template_json = template_json
        view.request = MagicMock()
        return view

    def _written(self, view):
        response = view.request.response
        return response, json.loads(response.setResult.call_args.args[0])

    def test_missing_and_invalid_template_json_are_reported(self) -> None:
        view = self._make_view("")
        view.get_template_json()
        response, payload = self._written(view)
        response.setStatus.assert_called_once_with(404)
        self.assertEqual(payload["error"], "template_json_missing")
        self.assertEqual(str(payload["message"]), "No template JSON configured.")
        self.assertEqual(
            response.setHeader.call_args_list[0].args,
            ("X-Survey-Error", "template_json_missing"),
        )

        view = self._make_view("{not json")
        view.get_template_json()
        response, payload = self._written(view)
        response.setStatus.assert_called_once_with(400)
        self.assertEqual(payload["error"], "template_json_invalid")
        self.assertIn("Expecting", payload["message"])

        view = self._make_view("[1, 2, 3]")
        view.get_template_json()
        response, payload = self._written(view)
        response.setStatus.assert_called_once_with(400)
        self.assertEqual(payload["error"], "template_json_invalid")
        self.assertEqual(
            str(payload["message"]), "Template JSON must be a JSON object."
        )

    def test_valid_template_json_is_returned_as_json_response(self) -> None:
        template = {"pages": [{"elements": []}], "title": "Übersicht"}
        view = self._make_view(json.dumps(template))

        view.get_template_json()

        response, payload = self._written(view)
        self.assertEqual(payload, template)
        response.setStatus.assert_called_once_with(200)
        self.assertEqual(
            response.setHeader.call_args.args, ("content-type", "application/json")
        )

    def test_html_safe_json_escapes_markup(self) -> None:
        self.assertEqual(
            SurveyTemplateViewer.html_safe_json({"a": "</script>"}),
            '{"a":"\\u003c/script\\u003e"}',
        )

    def test_call_renders_the_index_template(self) -> None:
        view = SurveyTemplateViewer.__new__(SurveyTemplateViewer)
        with patch.object(
            SurveyTemplateViewer, "index", MagicMock(return_value="RENDERED")
        ):
            self.assertEqual(view(), "RENDERED")


class HttpServiceCoverageTests(unittest.TestCase):
    def test_json_error_writes_the_body_when_the_header_fails(self) -> None:
        headers = []

        def set_header(name, value):
            if name == "X-Survey-Error":
                raise RuntimeError("header rejected")
            headers.append((name, value))

        response = MagicMock()
        response.setHeader.side_effect = set_header

        json_error(
            response,
            400,
            "invalid_json",
            message="Broken payload",
            extra={"isSuccess": False},
        )

        response.setStatus.assert_called_once_with(400)
        self.assertEqual(headers, [("content-type", "application/json")])
        self.assertEqual(
            json.loads(response.setResult.call_args.args[0]),
            {"error": "invalid_json", "message": "Broken payload", "isSuccess": False},
        )

    def test_json_error_without_message_or_extra(self) -> None:
        response = MagicMock()

        json_error(response, 403, "permission_denied")

        self.assertEqual(
            response.setHeader.call_args_list[0].args,
            ("X-Survey-Error", "permission_denied"),
        )
        self.assertEqual(
            json.loads(response.setResult.call_args.args[0]),
            {"error": "permission_denied"},
        )

    def test_json_response_supports_write_only_responses(self) -> None:
        class WriteOnlyResponse:
            def __init__(self) -> None:
                self.headers = []
                self.status = None
                self.body = b""

            def setStatus(self, status):
                self.status = status

            def setHeader(self, name, value):
                self.headers.append((name, value))

            def write(self, body):
                self.body += body

        response = WriteOnlyResponse()
        json_response(
            response,
            {"ok": True},
            status=201,
            dumps_options=__import__("orjson").OPT_SORT_KEYS,
        )

        self.assertEqual(response.status, 201)
        self.assertEqual(response.headers, [("content-type", "application/json")])
        self.assertEqual(json.loads(response.body), {"ok": True})

    def test_parse_json_body_handles_text_empty_and_invalid_bodies(self) -> None:
        self.assertEqual(parse_json_body({"BODY": '{"a": 1}'}), {"a": 1})
        self.assertIsNone(parse_json_body({"BODY": b""}))
        self.assertIsNone(parse_json_body({"BODY": ""}))
        self.assertIsNone(parse_json_body({"BODY": "{not json"}))
        self.assertIsNone(parse_json_body({}))
        self.assertEqual(parse_json_body({"BODY": b"[1, 2]"}), [1, 2])


if __name__ == "__main__":
    unittest.main()
