"""Branch-coverage tests for the PDF/results/monitor/template browser views.

The feature-level tests exercise the happy paths. These tests drive the
remaining error and edge branches: disabled features, missing uploads,
storage/transport failures, invalid input, callable catalog values and the
widget variants of the PDF filler.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from zopyx.surveyjs.browser import fillable_pdf as fillable_pdf_module
from zopyx.surveyjs.browser import survey_monitor as monitor_module
from zopyx.surveyjs.browser import survey_results as results_module
from zopyx.surveyjs.browser import survey_templates_overview as templates_module
from zopyx.surveyjs.browser.fillable_pdf import FillablePDFView
from zopyx.surveyjs.browser.survey_monitor import SurveyMonitorView
from zopyx.surveyjs.browser.survey_results import SurveyResults
from zopyx.surveyjs.browser.survey_templates_overview import SurveyTemplatesOverview


class FillablePDFViewBranchTests(unittest.TestCase):
    def setUp(self):
        self.view = FillablePDFView.__new__(FillablePDFView)
        self.view.context = MagicMock()
        self.view.context.absolute_url.return_value = "http://nohost/survey"
        self.view.request = MagicMock()
        self.view.request.form = {}
        self.show_message = patch("plone.api.portal.show_message").start()
        patch.object(self.view, "_check_post_authenticator").start()
        self.addCleanup(patch.stopall)

    def reset_context(self):
        self.view.context = MagicMock()
        self.view.context.absolute_url.return_value = "http://nohost/survey"

    # --- __call__ / feature gate -------------------------------------------

    def test_call_requires_the_fillable_pdf_feature(self):
        self.view.require_feature = MagicMock(return_value=False)
        self.view.index = MagicMock(return_value="rendered")
        self.assertIsNone(self.view())
        self.view.require_feature.assert_called_once_with("fillable-pdf")
        self.view.index.assert_not_called()

        self.view.require_feature.return_value = True
        self.assertEqual(self.view(), "rendered")
        self.view.index.assert_called_once_with()

    # --- form-version helpers ----------------------------------------------

    def test_get_latest_form_json_uses_the_versions_service(self):
        annos = {}
        with (
            patch.object(fillable_pdf_module, "IAnnotations", return_value=annos),
            patch.object(
                fillable_pdf_module.forms_service, "ensure_form_versions"
            ) as ensure,
            patch.object(
                fillable_pdf_module.forms_service,
                "latest_form_json",
                return_value={"pages": []},
            ) as latest,
        ):
            result = self.view._get_latest_form_json()
        self.assertEqual(result, {"pages": []})
        ensure.assert_called_once_with(annos)
        latest.assert_called_once_with(annos)

    def test_json_form_helpers_handle_absent_and_present_forms(self):
        with patch.object(self.view, "_get_latest_form_json", return_value={}):
            self.assertEqual(self.view._get_json_form_field_names(), set())
            self.assertEqual(self.view.json_form_properties, [])

        form = {
            "pages": [
                {"elements": [{"type": "text", "name": "a", "inputType": "text"}]}
            ]
        }
        with patch.object(self.view, "_get_latest_form_json", return_value=form):
            self.assertEqual(self.view._get_json_form_field_names(), {"a"})
            self.assertEqual(
                [prop["name"] for prop in self.view.json_form_properties], ["a"]
            )

    # --- PDF metadata properties -------------------------------------------

    def test_pdf_metadata_properties_without_and_with_template(self):
        self.view.context.fillable_pdf = None
        self.assertEqual(self.view.pdf_fields, [])
        self.assertEqual(self.view.pdf_content_type, "application/pdf")

        self.view.context.fillable_pdf = MagicMock(spec=["data", "filename"])
        self.assertEqual(self.view.pdf_content_type, "application/pdf")
        self.assertIs(self.view.pdf_filename, self.view.context.fillable_pdf.filename)

    # --- privacyforms extraction -------------------------------------------

    def test_extraction_passes_bytes_to_service_and_tolerates_unlink_failure(self):
        leaked = []
        real_unlink = Path.unlink

        def deny_unlink(path):
            leaked.append(path)
            raise OSError("file in use")

        service = MagicMock()
        service.extract.return_value = MagicMock(fields=[])
        with (
            patch.object(
                fillable_pdf_module, "PDFFormService", return_value=service
            ) as service_cls,
            patch.object(Path, "unlink", deny_unlink),
        ):
            fields = self.view._extract_fields_with_privacyforms_pdf(b"%PDF-1.4\n")

        self.assertEqual(fields, [])
        service_cls.assert_called_once_with()
        self.assertEqual(len(leaked), 1)
        self.assertTrue(leaked[0].name.endswith(".pdf"))
        service.extract.assert_called_once_with(leaked[0])
        self.addCleanup(lambda: [real_unlink(p) for p in leaked if p.exists()])

    # --- validation ---------------------------------------------------------

    def test_validation_rejects_a_pdf_without_pages(self):
        reader = MagicMock()
        reader.pages = []
        with patch.object(fillable_pdf_module, "PdfReader", return_value=reader):
            valid, message = self.view._validate_fillable_pdf(b"%PDF-1.4\n")
        self.assertFalse(valid)
        self.assertIn("no pages", message)
        reader.get_fields.assert_not_called()

    # --- upload -------------------------------------------------------------

    def test_upload_accepts_a_non_stream_payload(self):
        class RawUpload:
            filename = "raw.pdf"

        raw = RawUpload()
        self.view.request.form = {"pdf_file": raw}
        stored = MagicMock(filename="raw.pdf", data=b"raw")
        with (
            patch.object(
                self.view, "_validate_fillable_pdf", return_value=(True, "ok")
            ),
            patch.object(
                fillable_pdf_module, "NamedBlobFile", return_value=stored
            ) as named,
        ):
            self.view.upload_pdf()

        named.assert_called_once_with(
            data=raw, contentType="application/pdf", filename="raw.pdf"
        )
        self.assertIs(self.view.context.fillable_pdf, stored)
        self.view.context.reindexObject.assert_called_once_with()
        self.view.request.response.redirect.assert_called_with(
            "http://nohost/survey/@@fillable-pdf"
        )

    def test_upload_reports_a_storage_failure(self):
        class RawUpload:
            filename = "raw.pdf"

        self.view.request.form = {"pdf_file": RawUpload()}
        with (
            patch.object(
                self.view, "_validate_fillable_pdf", return_value=(True, "ok")
            ),
            patch.object(
                fillable_pdf_module,
                "NamedBlobFile",
                side_effect=RuntimeError("disk full"),
            ),
        ):
            self.view.upload_pdf()

        self.show_message.assert_called_once_with(
            "Failed to upload PDF: disk full",
            request=self.view.request,
            type="error",
        )
        self.view.request.response.redirect.assert_called_with(
            "http://nohost/survey/@@fillable-pdf"
        )

    # --- download -----------------------------------------------------------

    def test_download_returns_404_without_a_template(self):
        self.view.context.fillable_pdf = None
        self.assertEqual(self.view.download_pdf(), "No PDF template available.")
        self.view.request.response.setStatus.assert_called_once_with(404)
        self.view.request.response.write.assert_not_called()

    def test_download_streams_the_stored_template(self):
        self.view.context.fillable_pdf = MagicMock(
            data=b"%PDF-1.4 body", filename="template.pdf"
        )
        self.assertIsNone(self.view.download_pdf())
        self.view.request.response.setHeader.assert_any_call(
            "Content-Type", "application/pdf"
        )
        self.view.request.response.setHeader.assert_any_call(
            "Content-Disposition", 'attachment; filename="template.pdf"'
        )
        self.view.request.response.write.assert_called_once_with(b"%PDF-1.4 body")

    # --- delete -------------------------------------------------------------

    def test_delete_removes_the_stored_template(self):
        self.view.context.fillable_pdf = MagicMock()
        self.view.delete_pdf()

        self.assertEqual(
            self.show_message.call_args.args[0], "PDF template deleted successfully."
        )
        self.assertEqual(self.show_message.call_args.kwargs["type"], "info")
        self.assertNotIn("fillable_pdf", vars(self.view.context))
        self.view.context.reindexObject.assert_called_once_with()
        self.view.request.response.redirect.assert_called_with(
            "http://nohost/survey/@@fillable-pdf"
        )

    def test_delete_without_template_still_redirects(self):
        self.view.context = MagicMock(spec=["absolute_url", "reindexObject"])
        self.view.context.absolute_url.return_value = "http://nohost/survey"
        self.view.delete_pdf()

        self.assertEqual(
            self.show_message.call_args.args[0], "PDF template deleted successfully."
        )
        self.view.context.reindexObject.assert_not_called()
        self.view.request.response.redirect.assert_called_with(
            "http://nohost/survey/@@fillable-pdf"
        )

    def test_delete_reports_a_reindex_failure(self):
        self.reset_context()
        self.view.context.fillable_pdf = MagicMock()
        self.view.context.reindexObject.side_effect = RuntimeError("index locked")
        self.view.delete_pdf()

        self.show_message.assert_called_once_with(
            "Failed to delete PDF: index locked",
            request=self.view.request,
            type="error",
        )
        self.view.request.response.redirect.assert_called_with(
            "http://nohost/survey/@@fillable-pdf"
        )

    # --- fill ---------------------------------------------------------------

    def test_fill_requires_an_uploaded_template(self):
        self.view.context.fillable_pdf = None
        with patch.object(fillable_pdf_module, "PYMUPDF_AVAILABLE", True):
            self.view.fill_pdf()

        self.show_message.assert_called_once_with(
            "No PDF template available to fill.",
            request=self.view.request,
            type="error",
        )
        self.view.request.response.redirect.assert_called_with(
            "http://nohost/survey/@@fillable-pdf"
        )

    def test_fill_covers_all_widget_variants(self):
        self.view.context.fillable_pdf = MagicMock(data=b"%PDF", filename="form.pdf")
        self.view.request.form = {
            "on_state": "yes",
            "no_states": "yes",
            "unchecked": "no",
            "flag_off": 0,
            "signature": "signed",
        }
        nameless = MagicMock(field_name="", field_type_string="Text")
        on_state = MagicMock(field_name="on_state", field_type_string="Checkbox")
        on_state.button_states.return_value = ["On"]
        no_states = MagicMock(field_name="no_states", field_type_string="Checkbox")
        no_states.button_states.return_value = []
        unchecked = MagicMock(field_name="unchecked", field_type_string="Checkbox")
        flag_off = MagicMock(field_name="flag_off", field_type_string="Checkbox")
        signature = MagicMock(field_name="signature", field_type_string="Signature")

        page = MagicMock()
        page.widgets.return_value = [
            nameless,
            on_state,
            no_states,
            unchecked,
            flag_off,
            signature,
        ]
        doc = MagicMock()
        doc.__iter__.return_value = iter([page])
        doc.tobytes.return_value = b"filled-pdf"
        fake_fitz = MagicMock()
        fake_fitz.open.return_value = doc

        with (
            patch.object(fillable_pdf_module, "PYMUPDF_AVAILABLE", True),
            patch.object(fillable_pdf_module, "fitz", fake_fitz, create=True),
        ):
            self.view.fill_pdf()

        nameless.update.assert_not_called()
        self.assertTrue(on_state.field_value)
        self.assertTrue(no_states.field_value)
        self.assertFalse(unchecked.field_value)
        self.assertFalse(flag_off.field_value)
        self.assertEqual(signature.field_value, "signed")
        doc.close.assert_called_once_with()
        self.show_message.assert_not_called()
        self.view.request.response.write.assert_called_once_with(b"filled-pdf")


class SurveyMonitorViewCoverageTests(unittest.TestCase):
    def make_view(self):
        view = SurveyMonitorView.__new__(SurveyMonitorView)
        view.context = MagicMock()
        view.context.absolute_url.return_value = "http://nohost/survey"
        view.request = MagicMock()
        view.request.form = {}
        return view

    def test_init_defaults_the_time_window(self):
        context = MagicMock()
        request = MagicMock()
        view = SurveyMonitorView(context, request)
        self.assertEqual(view.time_window, "1h")
        self.assertIs(view.context, context)
        self.assertIs(view.request, request)

    def test_call_renders_the_template(self):
        view = self.make_view()
        view.index = MagicMock(return_value="html")
        with patch.object(
            monitor_module, "get_submission_stats", return_value={"total": 0}
        ):
            self.assertEqual(view(), "html")
        self.assertEqual(view.time_window, "1h")
        view.index.assert_called_once_with()

    def test_stats_and_cache_diagnostics_helpers(self):
        view = self.make_view()
        view.time_window = "5m"
        with patch.object(
            monitor_module, "get_submission_stats", return_value={"total": 3}
        ) as stats:
            self.assertEqual(view.get_stats(), {"total": 3})
        stats.assert_called_once_with("5m")

        with patch.object(
            monitor_module,
            "get_monitoring_diagnostics",
            return_value={"path": "/tmp/cache", "configured": True},
        ):
            self.assertEqual(view.get_cache_path(), "/tmp/cache")
            self.assertEqual(
                view.get_cache_diagnostics(),
                {"path": "/tmp/cache", "configured": True},
            )

        with patch.object(
            monitor_module,
            "get_monitoring_diagnostics",
            side_effect=RuntimeError("no backend"),
        ):
            self.assertEqual(
                view.get_cache_diagnostics(),
                {"configured": False, "error": "no backend"},
            )

        with patch.object(
            monitor_module, "get_monitoring_metrics", return_value={"hits": 7}
        ):
            self.assertEqual(view.get_cache_metrics(), {"hits": 7})


class SurveyTemplatesOverviewCoverageTests(unittest.TestCase):
    def make_brain(self, obj):
        brain = MagicMock()
        brain.getObject.return_value = obj
        brain.Title = "Template"
        brain.Description = "Description"
        brain.UID = "uid-1"
        brain.review_state = "published"
        brain.effective = None
        brain.expires = None
        brain.getURL.return_value = "http://nohost/template"
        return brain

    def make_view(self):
        view = SurveyTemplatesOverview.__new__(SurveyTemplatesOverview)
        view.context = MagicMock()
        view.context.getPhysicalPath.return_value = ("", "folder")
        view._format_catalog_iso = MagicMock(return_value="")
        view._translate_label = MagicMock(side_effect=lambda value: value)
        view._survey_field_value_text = MagicMock(return_value="value")
        view._compact_metadata_value = MagicMock(
            side_effect=lambda value: (value, value)
        )
        return view

    def test_entries_fall_back_to_brain_state_and_skip_template_json(self):
        obj = MagicMock()
        obj.Language.return_value = "en"
        obj.actions = set()
        brain = self.make_brain(obj)
        catalog = MagicMock()
        catalog.searchResults.return_value = [brain]
        fields = [
            ("email_to", MagicMock(title="Email To")),
            ("post_endpoint_url", MagicMock(title="POST endpoint")),
            ("template_json", MagicMock(title="Template JSON")),
            ("title", MagicMock(title="Title")),
        ]
        view = self.make_view()

        with (
            patch("plone.api.portal.get_tool", return_value=catalog),
            patch(
                "plone.api.content.get_state",
                side_effect=RuntimeError("no workflow state"),
            ) as get_state,
            patch.object(
                templates_module, "getFieldsInOrder", return_value=fields
            ) as get_fields,
        ):
            entries = view.survey_templates_overview_entries()

        get_state.assert_called_once_with(obj)
        get_fields.assert_called_once()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["review_state"], "published")
        self.assertEqual([item["label"] for item in entries[0]["metadata"]], ["Title"])
        self.assertEqual(entries[0]["uid"], "uid-1")
        self.assertFalse(entries[0]["expires_future"])

    def test_entries_invoke_a_callable_expiry(self):
        calls = []

        def expires():
            calls.append(True)
            return datetime(2099, 1, 1, tzinfo=timezone.utc)

        obj = MagicMock()
        obj.Language.return_value = "de"
        obj.actions = {"mail"}
        brain = self.make_brain(obj)
        brain.expires = expires
        catalog = MagicMock()
        catalog.searchResults.return_value = [brain]
        view = self.make_view()

        with (
            patch("plone.api.portal.get_tool", return_value=catalog),
            patch("plone.api.content.get_state", return_value="published"),
            patch.object(templates_module, "getFieldsInOrder", return_value=[]),
        ):
            entries = view.survey_templates_overview_entries()

        self.assertEqual(calls, [True])
        self.assertTrue(entries[0]["expires_future"])
        self.assertEqual(entries[0]["language"], "de")
        self.assertEqual(entries[0]["metadata"], [])


class SurveyResultsBranchTests(unittest.TestCase):
    def setUp(self):
        self.view = SurveyResults.__new__(SurveyResults)
        self.view.context = MagicMock()
        self.view.context.absolute_url.return_value = "http://nohost/survey"
        self.view.context.actions = {"post"}
        self.view.context.post_endpoint_url = "https://receiver.example/api"
        self.view.request = MagicMock()
        self.view.request.form = {}
        self.view.request.response.redirect.return_value = None
        self.show_message = patch("plone.api.portal.show_message").start()
        patch.object(results_module, "IAnnotations", return_value={}).start()
        patch.object(
            results_module, "get_post_endpoint_policy", return_value={}
        ).start()
        patch("plone.api.user.get_roles", return_value=["Manager"]).start()
        self.addCleanup(patch.stopall)

    def patch_auth(self):
        return patch.object(self.view, "_check_post_authenticator")

    def last_message_type(self):
        return self.show_message.call_args.kwargs.get("type")

    # --- delegation helpers -------------------------------------------------

    def test_delegating_result_helpers_and_results_data(self):
        storage = MagicMock()
        storage.list_results.return_value = [{"poll_id": "p1"}]
        rows = [{"id": 1}]
        with (
            patch.object(results_module, "get_result_storage", return_value=storage),
            patch.object(
                results_module.results_service,
                "parse_tabulator_param",
                return_value={"page": 2},
            ) as parse,
            patch.object(
                results_module.results_service, "results_row", return_value=rows[0]
            ) as row,
            patch.object(
                results_module.results_service,
                "results_apply_filters",
                return_value=rows,
            ) as apply_filters,
            patch.object(
                results_module.results_service,
                "build_results_payload",
                return_value={"data": rows},
            ) as build,
            patch.object(results_module, "json_response") as json_response,
        ):
            parsed = {"page": 2}
            self.assertEqual(self.view._parse_tabulator_param("page"), parsed)
            self.assertIs(self.view._results_row({"id": 1}), rows[0])
            self.assertIs(self.view._results_apply_filters(rows, []), rows)
            self.assertIs(self.view.results, storage.list_results.return_value)
            self.view.results_data()

        parse.assert_called_once_with(self.view.request, "page")
        row.assert_called_once_with({"id": 1})
        apply_filters.assert_called_once_with(rows, [])
        build.assert_called_once_with([{"poll_id": "p1"}], self.view.request)
        json_response.assert_called_once_with(
            self.view.request.response, {"data": rows}
        )

    # --- download_result ----------------------------------------------------

    def test_download_result_guards_and_missing_export(self):
        self.view.request.form = {"poll_id": "p1", "format": "bogus"}
        self.view.download_result()
        self.assertEqual(self.last_message_type(), "error")
        self.view.request.response.redirect.assert_called_with(
            "http://nohost/survey/results"
        )

        storage = MagicMock()
        storage.get_result.return_value = None
        self.view.request.form = {"poll_id": "p1", "format": "text"}
        with patch.object(results_module, "get_result_storage", return_value=storage):
            self.view.download_result()
        self.assertEqual(self.last_message_type(), "error")
        self.assertEqual(self.view.request.response.redirect.call_count, 2)

        storage.get_result.return_value = {"poll_id": "p1", "result": {"a": 1}}
        converter = MagicMock()
        converter.collect_items.return_value = ([], [])
        with (
            patch.object(results_module, "get_result_storage", return_value=storage),
            patch.object(self.view, "_latest_form_json", return_value={"pages": []}),
            patch(
                "zopyx.surveyjs.converters.cli.SurveyConverter",
                return_value=converter,
            ),
            patch.object(self.view, "_write_export", return_value=None),
        ):
            self.view.download_result()

        self.assertIn("not available", str(self.show_message.call_args.args[0]))
        self.assertEqual(self.view.request.response.redirect.call_count, 3)
        converter.collect_items.assert_called_once_with({"a": 1}, "p1")

    # --- mail_result --------------------------------------------------------

    def test_mail_result_guards_and_send_failure(self):
        self.view.request.form = {"poll_id": "p1", "format": "bogus"}
        with self.patch_auth():
            self.view.mail_result()
        self.assertEqual(self.last_message_type(), "error")

        self.view.request.form = {"poll_id": "p1", "format": "text"}
        with (
            self.patch_auth(),
            patch.object(
                results_module, "resolve_mail_settings", return_value={}
            ) as resolve,
        ):
            self.view.mail_result()
        self.assertIn("Mail-To", str(self.show_message.call_args.args[0]))
        resolve.assert_called_once()
        self.assertEqual(
            resolve.call_args.args[1],
            [
                "email_to",
                "email_subject",
                "email_body",
                "email_sender",
                "email_cc",
                "email_bcc",
            ],
        )

        settings = {"email_to": "dest@example.com", "email_subject": "Report"}
        storage = MagicMock()
        storage.get_result.return_value = None
        with (
            self.patch_auth(),
            patch.object(
                results_module, "resolve_mail_settings", return_value=settings
            ),
            patch.object(results_module, "get_result_storage", return_value=storage),
        ):
            self.view.mail_result()
        self.assertEqual(self.show_message.call_args.args[0], "Poll result not found")

        storage.get_result.return_value = {"poll_id": "p1", "result": {"a": 1}}
        converter = MagicMock()
        converter.collect_items.return_value = ([], [])
        with (
            self.patch_auth(),
            patch.object(
                results_module, "resolve_mail_settings", return_value=settings
            ),
            patch.object(results_module, "get_result_storage", return_value=storage),
            patch.object(self.view, "_latest_form_json", return_value={"pages": []}),
            patch(
                "zopyx.surveyjs.converters.cli.SurveyConverter",
                return_value=converter,
            ),
            patch.object(self.view, "_write_export", return_value=None),
        ):
            self.view.mail_result()
        self.assertIn("not available", str(self.show_message.call_args.args[0]))

        converter.send_email.side_effect = RuntimeError("smtp down")
        with (
            self.patch_auth(),
            patch.object(
                results_module, "resolve_mail_settings", return_value=settings
            ),
            patch.object(results_module, "get_result_storage", return_value=storage),
            patch.object(self.view, "_latest_form_json", return_value={"pages": []}),
            patch(
                "zopyx.surveyjs.converters.cli.SurveyConverter",
                return_value=converter,
            ),
            patch.object(
                self.view, "_write_export", return_value=Path("/tmp/export.txt")
            ),
        ):
            self.view.mail_result()

        self.assertIn("Failed to send mail", str(self.show_message.call_args.args[0]))
        self.assertEqual(self.last_message_type(), "error")
        converter.save_attachments.assert_called_once_with([])
        self.assertEqual(converter.send_email.call_args.args[0], "dest@example.com")

    # --- post_result --------------------------------------------------------

    def test_post_result_missing_result_missing_form_and_transport_failure(self):
        self.view.request.form = {"poll_id": "p1"}
        storage = MagicMock()
        storage.get_result.return_value = None
        with (
            self.patch_auth(),
            patch.object(
                results_module,
                "validate_post_endpoint_url",
                return_value="https://receiver.example/api",
            ) as validate,
            patch.object(results_module, "get_result_storage", return_value=storage),
        ):
            self.view.post_result()
        validate.assert_called_once_with("https://receiver.example/api")
        self.assertEqual(self.show_message.call_args.args[0], "Poll result not found")

        storage.get_result.return_value = {"poll_id": "p1", "result": {"a": 1}}
        with (
            self.patch_auth(),
            patch.object(
                results_module, "validate_post_endpoint_url", return_value="https://x"
            ),
            patch.object(results_module, "get_result_storage", return_value=storage),
            patch.object(self.view, "_latest_form_json", return_value=None),
        ):
            self.view.post_result()
        self.assertEqual(
            self.show_message.call_args.args[0],
            "No form definition available to include in POST",
        )

        with (
            self.patch_auth(),
            patch.object(
                results_module, "validate_post_endpoint_url", return_value="https://x"
            ),
            patch.object(results_module, "get_result_storage", return_value=storage),
            patch.object(self.view, "_latest_form_json", return_value={"pages": []}),
            patch.object(
                results_module.httpx,
                "post",
                side_effect=RuntimeError("connection refused"),
            ),
        ):
            self.view.post_result()

        self.assertIn("Failed to POST result", str(self.show_message.call_args.args[0]))
        self.assertEqual(self.last_message_type(), "error")
        self.view.request.response.redirect.assert_called_with(
            "http://nohost/survey/results"
        )

    # --- delete_results -----------------------------------------------------

    def test_delete_results_collects_ids_from_body_and_form(self):
        storage = MagicMock()
        storage.delete_results.return_value = {"deleted": 2}
        self.view.request.form = {"poll_id": "p2", "poll_ids": ["p3", "p4"]}
        with (
            self.patch_auth(),
            patch.object(results_module, "parse_json_body", return_value=None),
            patch.object(results_module, "get_result_storage", return_value=storage),
            patch.object(results_module, "json_response") as json_response,
        ):
            self.view.delete_results()

        storage.delete_results.assert_called_once_with(
            self.view.context, ["p2", "p3", "p4"]
        )
        json_response.assert_called_once_with(
            self.view.request.response, {"deleted": 2}
        )

        self.view.request.form = {}
        storage.reset_mock()
        with (
            self.patch_auth(),
            patch.object(
                results_module, "parse_json_body", return_value={"poll_ids": "p9"}
            ),
            patch.object(results_module, "get_result_storage", return_value=storage),
            patch.object(results_module, "json_response"),
        ):
            self.view.delete_results()
        storage.delete_results.assert_called_once_with(self.view.context, ["p9"])

        self.view.request.form = {"poll_ids": "p10"}
        storage.reset_mock()
        with (
            self.patch_auth(),
            patch.object(results_module, "parse_json_body", return_value=None),
            patch.object(results_module, "get_result_storage", return_value=storage),
            patch.object(results_module, "json_response"),
        ):
            self.view.delete_results()
        storage.delete_results.assert_called_once_with(self.view.context, ["p10"])

    def test_delete_results_requires_ids(self):
        storage = MagicMock()
        self.view.request.form = {}
        with (
            self.patch_auth(),
            patch.object(results_module, "parse_json_body", return_value={}),
            patch.object(results_module, "get_result_storage", return_value=storage),
            patch.object(results_module, "json_error") as json_error,
        ):
            self.view.delete_results()

        json_error.assert_called_once_with(
            self.view.request.response,
            400,
            "No poll IDs provided for deletion",
        )
        storage.delete_results.assert_not_called()


if __name__ == "__main__":
    unittest.main()
