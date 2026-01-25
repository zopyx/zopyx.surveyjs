from datetime import datetime, timezone
from string import Formatter
import re
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import time
import csv
import io
import hashlib
import logging
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from sqlalchemy.engine import make_url
from zope.annotation.interfaces import IAnnotations
from zope.event import notify
import plone.api
import httpx

from .. import _
from ..events import SurveyJSFormSubmitted
from ..constants import FORM_VERSIONS_KEY, PDF_FORM_KEY
from ..storage import _get_storage_location, get_result_storage
from ..utils import ensure_timezone_aware
from ..data_validation.validate_data import validate_data as run_data_validation
from ..pdf_forms import fill_pdf_form as fill_pdf_form_bytes

import orjson
import uuid
from plone.namedfile.file import NamedBlobFile

from .services import ai as ai_service
from .services import auth as auth_service
from .services import export as export_service
from .services import forms as forms_service
from .services import pdf as pdf_service
from .services import results as results_service
from .services.http import json_error, json_response, parse_json_body

logger = logging.getLogger(__name__)

CONVERTER_FORMATS = [
    ("text", "Text (.txt)", "txt", "text/plain"),
    ("md", "Markdown (.md)", "md", "text/markdown"),
    ("html", "HTML (.html)", "html", "text/html"),
    ("pdf", "PDF (.pdf)", "pdf", "application/pdf"),
    ("csv", "CSV (.csv)", "csv", "text/csv"),
    (
        "xlsx",
        "Excel (.xlsx)",
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    ("xml", "XML (.xml)", "xml", "application/xml"),
    (
        "docx",
        "Word (.docx)",
        "docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ("json", "JSON (.json)", "json", "application/json"),
]


class RootRedirect(BrowserView):
    """Redirect the Plone root to the English language root."""

    def __call__(self):
        target = self.context.get("en")
        if target is not None:
            return self.request.response.redirect(target.absolute_url())
        return self.request.response.redirect(self.context.absolute_url())


def _extract_json_object(raw_text: str) -> str | None:
    """Best-effort extraction of a JSON object from noisy text."""
    if not raw_text:
        return None
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return raw_text[start : end + 1]


def _mask_storage_location(location: str) -> str:
    if location == "zodb":
        return "Plone (ZODB)"
    try:
        url = make_url(location)
    except Exception:
        return location
    if url.password:
        url = url.set(password="****")
    return url.render_as_string(hide_password=False)


def _run_external_validation(form_json, poll_result, submission_hash: str):
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        schema_path = tmpdir_path / "schema.json"
        data_path = tmpdir_path / "data.json"
        result_path = tmpdir_path / "validation.json"

        schema_bytes = orjson.dumps(form_json)
        data_bytes = orjson.dumps(poll_result)
        schema_path.write_bytes(schema_bytes)
        data_path.write_bytes(data_bytes)

        logger.info(
            "Survey external validation start: schema_bytes=%s data_bytes=%s submission=%s",
            len(schema_bytes),
            len(data_bytes),
            submission_hash,
        )

        start_time = time.monotonic()
        try:
            return_code = run_data_validation(
                schema_json=str(schema_path),
                form_json=str(data_path),
                result_json=str(result_path),
            )
        except FileNotFoundError:
            logger.info(
                "Survey external validation missing binary: submission=%s",
                submission_hash,
            )
            return dict(ok=False, status=500, reason="external_validator_missing")
        except Exception:
            logger.exception(
                "Survey external validation error: submission=%s",
                submission_hash,
            )
            return dict(ok=False, status=500, reason="external_validator_error")
        duration = time.monotonic() - start_time

        logger.info(
            "Survey external validation done: rc=%s duration=%.3fs submission=%s",
            return_code,
            duration,
            submission_hash,
        )

        result_data = {}
        if result_path.exists():
            try:
                result_data = orjson.loads(result_path.read_bytes())
            except orjson.JSONDecodeError:
                logger.info(
                    "Survey external validation result parse failed: submission=%s",
                    submission_hash,
                )

        if return_code != 0 and not result_data:
            return dict(ok=False, status=500, reason="external_validator_error")

        if result_data and not result_data.get("valid", True):
            return dict(
                ok=False,
                status=400,
                reason="external_validation_failed",
                details=result_data,
            )

        if return_code != 0:
            return dict(ok=False, status=500, reason="external_validator_error")

        return dict(
            ok=True, status=200, reason="external_validation_ok", details=result_data
        )


class Views(BrowserView):
    @property
    def storage_info(self) -> str:
        location = _get_storage_location()
        masked = _mask_storage_location(location)
        if location == "zodb":
            return masked
        return f"Relational database: {masked}"

    def _format_portal_time(self, value):
        if not value:
            return None
        try:
            return plone.api.portal.get_localized_time(value, long_format=True)
        except Exception:
            return str(value)

    def _extract_year(self, value):
        try:
            year_attr = getattr(value, "year", None)
        except Exception:
            return None
        if year_attr is None:
            return None
        if callable(year_attr):
            try:
                return int(year_attr())
            except Exception:
                return None
        try:
            return int(year_attr)
        except Exception:
            return None

    def _is_reasonable_date(self, value):
        year = self._extract_year(value)
        if year is None:
            return True
        return 1970 <= year <= 2100

    def survey_status_label(self):
        try:
            state = plone.api.content.get_state(self.context)
        except Exception:
            state = None
        if state in {"published", "internally_published"}:
            return _("Published")
        return _("Inactive")

    def survey_effective_display(self):
        value = getattr(self.context, "effective", None)
        if callable(value):
            value = value()
        if value and not self._is_reasonable_date(value):
            return None
        return self._format_portal_time(value)

    def survey_expires_display(self):
        value = getattr(self.context, "expires", None)
        if callable(value):
            value = value()
        if value and not self._is_reasonable_date(value):
            return None
        return self._format_portal_time(value)

    def survey_results_count(self):
        try:
            storage = get_result_storage(self.context)
            return len(storage.list_results(self.context))
        except Exception:
            return 0

    def _format_catalog_date(self, value):
        if callable(value):
            value = value()
        if value and not self._is_reasonable_date(value):
            return ""
        return self._format_portal_time(value) or ""

    def _format_catalog_iso(self, value):
        if callable(value):
            value = value()
        if value and not self._is_reasonable_date(value):
            return ""
        if hasattr(value, "ISO"):
            text = value.ISO()
        elif hasattr(value, "isoformat"):
            try:
                text = value.isoformat(timespec="minutes")
            except Exception:
                text = str(value)
        else:
            text = str(value) if value else ""
        match = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})", text)
        if match:
            return f"{match.group(1)} {match.group(2)}"
        return text

    def survey_overview_entries(self):
        catalog = plone.api.portal.get_tool("portal_catalog")
        context_path = "/".join(self.context.getPhysicalPath())
        brains = catalog.searchResults(
            portal_type="Survey",
            path={"query": context_path, "depth": -1},
            sort_on="sortable_title",
        )
        storage = get_result_storage(self.context)
        access_labels = {
            "public": _("Public"),
            "trusted": _("Trusted access token"),
        }
        entries = []
        for brain in brains:
            obj = brain.getObject()
            access_mode = getattr(obj, "access_mode", "") or ""
            access_label = access_labels.get(access_mode, access_mode)
            language = getattr(obj, "Language", None)
            language = language() if callable(language) else language
            if isinstance(language, (list, tuple)):
                language = ", ".join([str(item) for item in language if item])
            language = language or ""
            try:
                review_state = plone.api.content.get_state(obj)
            except Exception:
                review_state = brain.review_state or ""
            try:
                results_count = storage.count_results(obj)
            except Exception:
                results_count = 0
            expires_value = brain.expires
            if callable(expires_value):
                expires_value = expires_value()
            try:
                expires_future = bool(
                    expires_value
                    and ensure_timezone_aware(expires_value)
                    > datetime.now(timezone.utc)
                )
            except Exception:
                expires_future = False
            entries.append(
                {
                    "title": brain.Title or "",
                    "description": brain.Description or "",
                    "url": brain.getURL(),
                    "review_state": review_state,
                    "effective": self._format_catalog_iso(brain.effective),
                    "expires": self._format_catalog_iso(brain.expires),
                    "results_count": results_count,
                    "access_mode": access_label,
                    "language": language,
                    "expires_future": expires_future,
                }
            )
        return entries

    def format_created(self, created):
        return results_service.format_created(created)

    def get_form_json(self):
        """JSON for SurveyJS renderer"""

        if not self._require_trusted_access():
            return
        annos = IAnnotations(self.context)
        form_versions = forms_service.sorted_form_versions(annos)
        form_data = form_versions[-1]["form_json"] if form_versions else {}
        json_response(self.request.response, form_data)

    @property
    def pdf_form_available(self):
        pdf_form = getattr(self.context, "pdf_form", None)
        if not pdf_form:
            return False
        annos = IAnnotations(self.context)
        pdf_meta = annos.get(PDF_FORM_KEY) or {}
        return bool(pdf_meta.get("field_map"))

    def _get_pdf_form_state(self):
        return pdf_service.get_pdf_form_state(self.context)

    def get_pdf_form_json(self):
        state = self._get_pdf_form_state()
        if not state["pdf_form"]:
            json_error(
                self.request.response,
                404,
                "PDF form missing",
                message="No PDF form configured for this survey.",
            )
            return
        json_response(self.request.response, state["form_json"] or {})

    def upload_pdf_form(self):
        uploaded_file = self.request.form.get("pdf_file")
        if not uploaded_file:
            json_error(
                self.request.response,
                400,
                "No PDF uploaded",
                message="Please upload a PDF file.",
            )
            return

        try:
            pdf_bytes = uploaded_file.read()
            if not isinstance(pdf_bytes, bytes):
                pdf_bytes = pdf_bytes.encode("utf-8")
        except Exception as exc:
            json_error(
                self.request.response,
                400,
                "Upload failed",
                message=str(exc),
            )
            return

        try:
            extract_mode = (
                (self.request.form.get("extract_mode", "pdfcpu") or "pdfcpu")
                .strip()
                .lower()
            )
            survey_title = getattr(self.context, "title", None) or "PDF Form"

            survey_json, field_map = pdf_service.extract_pdf_form_data(
                pdf_bytes, extract_mode, survey_title
            )

            filename = getattr(uploaded_file, "filename", None) or "form.pdf"
            self.context.pdf_form = NamedBlobFile(
                data=pdf_bytes,
                filename=filename,
                contentType="application/pdf",
            )

            annos = IAnnotations(self.context)
            version_data = forms_service.save_form_version(
                annos,
                survey_json,
                plone.api.user.get_current().getId(),
                locked=False,
            )
            version_id = version_data["id"]

            annos[PDF_FORM_KEY] = dict(
                version_id=version_id,
                field_map=field_map,
                pdf_filename=filename,
                field_count=len(field_map),
                source=extract_mode,
                created=datetime.now(timezone.utc),
            )

            result = dict(
                success=True,
                json=survey_json,
                field_count=len(field_map),
                fields=field_map,
                version_id=version_id,
                extraction_mode=extract_mode,
            )
            if extract_mode == "llm":
                result["warning"] = (
                    "LLM extraction does not include PDF field mapping; "
                    "filled PDF export will be unavailable until pdfcpu mapping is used."
                )
            self.request.response.setStatus(200)
            json_response(self.request.response, result)

        except Exception as exc:
            json_error(
                self.request.response,
                500,
                "PDF analysis failed",
                message=str(exc),
            )

    def _generate_survey_json_from_pdf_llm(self, pdf_bytes: bytes) -> dict:
        return pdf_service.generate_survey_json_from_pdf_llm(pdf_bytes)

    def fill_pdf_form(self):
        state = self._get_pdf_form_state()
        pdf_form = state["pdf_form"]
        if not pdf_form:
            json_error(
                self.request.response,
                404,
                "PDF form missing",
                message="No PDF form configured for this survey.",
            )
            return

        if not state["field_map"]:
            json_error(
                self.request.response,
                400,
                "pdf_mapping_missing",
                message="PDF field mapping is missing. Re-upload using pdfcpu.",
                extra={"isSuccess": False},
            )
            return

        raw_poll = self.request.form.get("pollResult")
        if raw_poll is None:
            json_error(
                self.request.response,
                400,
                "missing_poll_result",
                extra={"isSuccess": False},
            )
            return

        if isinstance(raw_poll, bytes):
            raw_bytes = raw_poll
        elif isinstance(raw_poll, str):
            raw_bytes = raw_poll.encode("utf-8")
        else:
            json_error(
                self.request.response,
                400,
                "invalid_payload",
                extra={"isSuccess": False},
            )
            return

        max_payload_mb = getattr(self.context, "max_payload_size_mb", 1) or 1
        try:
            max_payload_bytes = int(max_payload_mb) * 1024 * 1024
        except (TypeError, ValueError):
            max_payload_bytes = 1 * 1024 * 1024

        content_length = self.request.getHeader("Content-Length")
        if content_length:
            try:
                if int(content_length) > max_payload_bytes:
                    json_error(
                        self.request.response,
                        413,
                        "request_too_large",
                        extra={"isSuccess": False},
                    )
                    return
            except ValueError:
                pass
        elif len(raw_bytes) > max_payload_bytes:
            json_error(
                self.request.response,
                413,
                "request_too_large",
                extra={"isSuccess": False},
            )
            return

        if len(raw_bytes) > max_payload_bytes:
            json_error(
                self.request.response,
                413,
                "json_too_large",
                extra={"isSuccess": False},
            )
            return

        try:
            poll_result = orjson.loads(raw_bytes)
        except orjson.JSONDecodeError:
            json_error(
                self.request.response,
                400,
                "invalid_json",
                extra={"isSuccess": False},
            )
            return

        form_json = state["form_json"] or {}
        if not form_json:
            json_error(
                self.request.response,
                400,
                "missing_form_schema",
                extra={"isSuccess": False},
            )
            return

        form_version_id = state.get("version_id") or ""
        if not form_version_id:
            annos = IAnnotations(self.context)
            form_version_id = self._latest_form_version_id(annos)
        if not self._require_trusted_access():
            return
        if not self._require_auth_token(form_version_id):
            return

        submission_hash = hashlib.sha256(raw_bytes).hexdigest()[:12]
        force_validation = getattr(self.context, "force_server_side_validation", False)
        if force_validation:
            external_validation = _run_external_validation(
                form_json, poll_result, submission_hash
            )
            if not external_validation.get("ok"):
                payload = {
                    "isSuccess": False,
                    "error": external_validation.get("reason"),
                }
                details = external_validation.get("details")
                if details:
                    payload["details"] = details
                self.request.response.setStatus(external_validation.get("status", 500))
                self.request.response.setHeader("content-type", "application/json")
                self.request.response.write(orjson.dumps(payload))
                return

        poll_id = str(uuid.uuid1())
        data = dict(
            poll_id=poll_id,
            created=datetime.now(timezone.utc),
            user=plone.api.user.get_current().getId(),
            form_version=state.get("version_id"),
            result=poll_result,
        )
        notify(SurveyJSFormSubmitted(self.context, data))

        try:
            filled_pdf = fill_pdf_form_bytes(
                pdf_form.data, poll_result, state["field_map"] or []
            )
        except Exception as exc:
            json_error(
                self.request.response,
                500,
                "pdf_fill_failed",
                message=str(exc),
                extra={"isSuccess": False},
            )
            return

        filename = state.get("pdf_meta", {}).get("pdf_filename") or "filled-form.pdf"
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        self.request.response.setHeader("content-type", "application/pdf")
        self.request.response.setHeader(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        self.request.response.write(filled_pdf)

    def save_form_json(self):
        json_form = orjson.loads(self.request.form["surveyText"])

        annos = IAnnotations(self.context)
        forms_service.save_form_version(
            annos,
            json_form,
            plone.api.user.get_current().getId(),
            locked=False,
        )

        json_response(self.request.response, dict(isSuccess=True))

    def save_poll(self):
        raw_poll = self.request.form.get("pollResult")
        if raw_poll is None:
            logger.warning("Survey save failed: status=400 reason=missing_poll_result")
            json_error(
                self.request.response,
                400,
                "missing_poll_result",
                extra={"isSuccess": False},
            )
            return

        if isinstance(raw_poll, bytes):
            raw_bytes = raw_poll
        elif isinstance(raw_poll, str):
            raw_bytes = raw_poll.encode("utf-8")
        else:
            logger.warning("Survey save failed: status=400 reason=invalid_payload")
            json_error(
                self.request.response,
                400,
                "invalid_payload",
                extra={"isSuccess": False},
            )
            return

        max_payload_mb = getattr(self.context, "max_payload_size_mb", 1) or 1
        try:
            max_payload_bytes = int(max_payload_mb) * 1024 * 1024
        except (TypeError, ValueError):
            max_payload_bytes = 1 * 1024 * 1024

        content_length = self.request.getHeader("Content-Length")
        if content_length:
            try:
                if int(content_length) > max_payload_bytes:
                    logger.warning(
                        "Survey save failed: status=413 reason=request_too_large"
                    )
                    json_error(
                        self.request.response,
                        413,
                        "request_too_large",
                        extra={"isSuccess": False},
                    )
                    return
            except ValueError:
                pass
        elif len(raw_bytes) > max_payload_bytes:
            logger.warning("Survey save failed: status=413 reason=request_too_large")
            json_error(
                self.request.response,
                413,
                "request_too_large",
                extra={"isSuccess": False},
            )
            return

        if len(raw_bytes) > max_payload_bytes:
            logger.warning("Survey save failed: status=413 reason=json_too_large")
            json_error(
                self.request.response,
                413,
                "json_too_large",
                extra={"isSuccess": False},
            )
            return

        try:
            poll_result = orjson.loads(raw_bytes)
        except orjson.JSONDecodeError:
            logger.warning("Survey save failed: status=400 reason=invalid_json")
            json_error(
                self.request.response,
                400,
                "invalid_json",
                extra={"isSuccess": False},
            )
            return

        actions = getattr(self.context, "actions", set()) or set()
        annos = IAnnotations(self.context)
        if FORM_VERSIONS_KEY not in annos:
            forms_service.ensure_form_versions(annos)

        form_versions = forms_service.sorted_form_versions(annos)
        form_version_id = form_versions[-1]["id"] if form_versions else None
        form_json = form_versions[-1]["form_json"] if form_versions else {}

        if not form_json:
            logger.warning("Survey save failed: status=400 reason=missing_form_schema")
            json_error(
                self.request.response,
                400,
                "missing_form_schema",
                extra={"isSuccess": False},
            )
            return

        if not self._require_trusted_access():
            return

        if not self._require_auth_token(form_version_id or ""):
            return

        submission_hash = hashlib.sha256(raw_bytes).hexdigest()[:12]
        force_validation = getattr(self.context, "force_server_side_validation", False)
        if force_validation:
            external_validation = _run_external_validation(
                form_json, poll_result, submission_hash
            )
            if not external_validation.get("ok"):
                logger.info(
                    "Survey external validation failed: reason=%s submission=%s",
                    external_validation.get("reason"),
                    submission_hash,
                )
                payload = {
                    "isSuccess": False,
                    "error": external_validation.get("reason"),
                }
                details = external_validation.get("details")
                if details:
                    payload["details"] = details
                json_response(
                    self.request.response,
                    payload,
                    status=external_validation.get("status", 500),
                )
                return
            logger.info(
                "Survey external validation ok: submission=%s",
                submission_hash,
            )
        else:
            logger.info(
                "Survey external validation skipped: enabled=%s submission=%s",
                False,
                submission_hash,
            )

        data = dict(
            poll_id=str(uuid.uuid1()),
            created=datetime.now(timezone.utc),
            user=plone.api.user.get_current().getId(),
            form_version=form_version_id,
            result=poll_result,
        )

        notify(SurveyJSFormSubmitted(self.context, data))

        result = dict(isSuccess=True)
        if "store" not in actions:
            result.update(
                stored=False,
                message="Storage action disabled; result not persisted.",
            )
        self.request.response.setStatus(200)
        json_response(
            self.request.response,
            result,
            dumps_options=orjson.OPT_INDENT_2,
        )

    def clear_results(self):
        storage = get_result_storage(self.context)
        storage.clear_results(self.context)

        plone.api.portal.show_message(_("Results cleared"))
        self.request.response.redirect(self.context.absolute_url() + "/view")

    def get_polls_json(self):
        """get polls"""
        storage = get_result_storage(self.context)
        results = storage.list_results(self.context)

        json_response(self.request.response, results)

    def get_polls_json2(self):
        """get polls"""
        storage = get_result_storage(self.context)
        results = [d.get("result") for d in storage.list_results(self.context)]

        json_response(self.request.response, results)

    def download_form_json(self):
        """Download current form JSON as attachment"""
        annos = IAnnotations(self.context)

        # Initialize if doesn't exist
        forms_service.ensure_form_versions(annos)
        form_versions = forms_service.sorted_form_versions(annos)
        form_data = form_versions[-1]["form_json"] if form_versions else {}

        # Prepare download with attachment header
        filename = f"{self.context.getId()}-survey-form.json"
        json_content = orjson.dumps(form_data, option=orjson.OPT_INDENT_2)

        self.request.response.setHeader("Content-Type", "application/json")
        self.request.response.setHeader(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        self.request.response.write(json_content)

    def download_polls_csv(self):
        """Download all poll results as CSV."""
        storage = get_result_storage(self.context)
        results = storage.list_results(self.context)
        logger.info("Downloading poll results (CSV) from %s", _get_storage_location())

        output = io.StringIO()
        # Discover all field names to create a stable header
        field_order = []
        seen_fields = set()
        for entry in results:
            result_payload = entry.get("result") or {}
            if isinstance(result_payload, dict):
                for key in result_payload.keys():
                    if key not in seen_fields:
                        seen_fields.add(key)
                        field_order.append(key)

        base_columns = ["poll_id", "user", "created", "form_version"]

        writer = csv.writer(output)
        writer.writerow(base_columns + field_order)

        for entry in results:
            created = entry.get("created")
            if isinstance(created, datetime):
                created = ensure_timezone_aware(created).isoformat()

            row = [
                entry.get("poll_id", ""),
                entry.get("user", ""),
                created or "",
                entry.get("form_version", ""),
            ]

            result_payload = entry.get("result") or {}
            for field in field_order:
                value = result_payload.get(field, "")
                if isinstance(value, (list, dict, tuple)):
                    try:
                        value = orjson.dumps(value).decode("utf-8")
                    except Exception:
                        value = str(value)
                elif value is None:
                    value = ""
                row.append(str(value))

            writer.writerow(row)

        filename = f"{self.context.getId()}-survey-data.csv"
        csv_bytes = output.getvalue().encode("utf-8")
        self.request.response.setHeader("Content-Type", "text/csv")
        self.request.response.setHeader(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        self.request.response.write(csv_bytes)

    def download_polls_json(self):
        """Download poll results JSON as attachment"""
        storage = get_result_storage(self.context)
        results = storage.list_results(self.context)
        logger.info("Downloading poll results (JSON) from %s", _get_storage_location())

        # Prepare download with attachment header
        filename = f"{self.context.getId()}-survey-data.json"
        json_content = orjson.dumps(results, option=orjson.OPT_INDENT_2)

        self.request.response.setHeader("Content-Type", "application/json")
        self.request.response.setHeader(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        self.request.response.write(json_content)

    @property
    def converter_formats(self):
        return [
            dict(key=key, label=label, short_label=label.split(" (", 1)[0])
            for key, label, ext, _content_type in CONVERTER_FORMATS
        ]

    def _parse_json_loose(self, raw_text: str) -> dict:
        """Try strict JSON first, then a bracket-extracted fallback."""
        cleaned = raw_text or ""
        try:
            return orjson.loads(cleaned)
        except orjson.JSONDecodeError:
            fallback = _extract_json_object(cleaned)
            if fallback:
                return orjson.loads(fallback)
            raise

    def _get_converter_format(self, format_key):
        for key, label, ext, content_type in CONVERTER_FORMATS:
            if key == format_key:
                return dict(key=key, label=label, ext=ext, content_type=content_type)
        return None

    def _latest_form_json(self, annos):
        return forms_service.latest_form_json(annos)

    def _latest_form_version_id(self, annos):
        return forms_service.latest_form_version_id(annos)

    def _form_id(self):
        try:
            uid = self.context.UID()
        except Exception:
            uid = None
        if uid:
            return uid
        get_id = getattr(self.context, "getId", None)
        if callable(get_id):
            return get_id()
        return str(getattr(self.context, "id", ""))

    def _auth(self):
        return auth_service.AuthService(self.context, self.request, self._form_id)

    def _require_trusted_access(self) -> bool:
        return self._auth().require_trusted_access(logger=logger)

    def _build_auth_token(self, form_version_id):
        token = self._auth().build_auth_token(form_version_id or "")
        if token:
            logger.info("Survey auth token generated: token=%s", token)
        return token

    def auth_token(self):
        annos = IAnnotations(self.context)
        form_version_id = self._latest_form_version_id(annos)
        return self._build_auth_token(form_version_id)

    def auth_token_pdf(self):
        state = self._get_pdf_form_state()
        form_version_id = state.get("version_id") or ""
        if not form_version_id:
            annos = IAnnotations(self.context)
            form_version_id = self._latest_form_version_id(annos)
        return self._build_auth_token(form_version_id)

    def trusted_access_token(self):
        annos = IAnnotations(self.context)
        form_version_id = self._latest_form_version_id(annos)
        token, metadata = self._auth().issue_trusted_access_token(form_version_id or "")
        if not token or not metadata:
            json_error(
                self.request.response,
                503,
                "trusted_access_cache_unavailable",
                extra={"isSuccess": False},
            )
            return
        url = f"{self.context.absolute_url()}/@@viewer?access_token={token}"
        payload = {
            "isSuccess": True,
            "token": token,
            "url": url,
            "expires_at": metadata.get("expires_at"),
        }
        json_response(self.request.response, payload)

    def _require_auth_token(self, form_version_id):
        return self._auth().require_auth_token(form_version_id or "", logger=logger)

    def _serialize_result_entry(self, result_entry):
        return export_service.serialize_result_entry(result_entry)

    def _write_export(
        self,
        format_key,
        poll_id,
        items,
        attachments,
        creator,
        created,
        output_dir,
    ):
        return export_service.write_export(
            format_key,
            poll_id,
            items,
            attachments,
            creator,
            created,
            output_dir,
        )

    def _interpolate_text(self, text, mapping):
        if not text:
            return text
        formatter = Formatter()
        try:
            return formatter.vformat(text, (), mapping)
        except KeyError:
            return text

    def download_result(self):
        """Download a single poll result in the requested format."""
        poll_id = self.request.form.get("poll_id")
        format_key = (self.request.form.get("format") or "").lower()
        format_info = self._get_converter_format(format_key)

        if not poll_id or not format_info:
            plone.api.portal.show_message(_("Invalid poll ID or format"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/results"
            )

        storage = get_result_storage(self.context)
        result_data = storage.get_result(self.context, poll_id)
        logger.info(
            "Downloading poll result %s (%s) from %s",
            poll_id,
            format_key or "unknown",
            _get_storage_location(),
        )

        if not result_data:
            plone.api.portal.show_message(_("Poll result not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/results"
            )

        annos = IAnnotations(self.context)
        form_json = self._latest_form_json(annos)
        entry = result_data.get("result", {})
        creator = result_data.get("user")
        created = result_data.get("created")
        if isinstance(created, datetime):
            created = ensure_timezone_aware(created).isoformat()

        from ..converters.cli import SurveyConverter

        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            data_path = tmpdir_path / "data.json"
            form_path = tmpdir_path / "form.json"
            output_dir = tmpdir_path / "output"

            data_payload = [self._serialize_result_entry(result_data)]
            data_path.write_bytes(orjson.dumps(data_payload))
            form_path.write_bytes(orjson.dumps(form_json))

            converter = SurveyConverter(data_path, form_path, output_dir)
            items, attachments = converter.collect_items(entry, poll_id)

            output_path = self._write_export(
                format_key,
                poll_id,
                items,
                attachments,
                creator,
                created,
                output_dir,
            )

            if output_path is None:
                plone.api.portal.show_message(
                    _("Requested export format is not available"), type="error"
                )
                return self.request.response.redirect(
                    self.context.absolute_url() + "/results"
                )

            self.request.response.setHeader("Content-Type", format_info["content_type"])
            filename = f"{poll_id}.{format_info['ext']}"
            self.request.response.setHeader(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
            self.request.response.write(output_path.read_bytes())
            return self.request.response

    def mail_result(self):
        """Send a single poll result export by email."""
        poll_id = self.request.form.get("poll_id")
        format_key = (self.request.form.get("format") or "").lower()
        format_info = self._get_converter_format(format_key)

        if not poll_id or not format_info:
            plone.api.portal.show_message(_("Invalid poll ID or format"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/results"
            )

        email_to = getattr(self.context, "email_to", None)
        email_subject = getattr(self.context, "email_subject", None)
        email_body = getattr(self.context, "email_body", "") or ""
        email_sender = getattr(self.context, "email_sender", None)
        email_cc = getattr(self.context, "email_cc", None) or []
        email_bcc = getattr(self.context, "email_bcc", None) or []

        if not email_to or not email_subject:
            plone.api.portal.show_message(
                _("Mail settings are incomplete (Mail-To and Subject required)"),
                type="error",
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/results"
            )

        storage = get_result_storage(self.context)
        result_data = storage.get_result(self.context, poll_id)

        if not result_data:
            plone.api.portal.show_message(_("Poll result not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/results"
            )

        annos = IAnnotations(self.context)
        form_json = self._latest_form_json(annos)
        entry = result_data.get("result", {})
        creator = result_data.get("user")
        created = result_data.get("created")
        if isinstance(created, datetime):
            created = ensure_timezone_aware(created).isoformat()
        formats_label = format_info["label"]
        email_subject = self._interpolate_text(email_subject, {"poll_id": poll_id})
        email_body = self._interpolate_text(
            email_body,
            {
                "created": created or "",
                "creator": creator or "",
                "formats": formats_label,
            },
        )

        from ..converters.cli import SurveyConverter

        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            data_path = tmpdir_path / "data.json"
            form_path = tmpdir_path / "form.json"
            output_dir = tmpdir_path / "output"

            data_payload = [self._serialize_result_entry(result_data)]
            data_path.write_bytes(orjson.dumps(data_payload))
            form_path.write_bytes(orjson.dumps(form_json))

            converter = SurveyConverter(data_path, form_path, output_dir)
            items, attachments = converter.collect_items(entry, poll_id)

            output_path = self._write_export(
                format_key,
                poll_id,
                items,
                attachments,
                creator,
                created,
                output_dir,
            )

            if output_path is None:
                plone.api.portal.show_message(
                    _("Requested export format is not available"), type="error"
                )
                return self.request.response.redirect(
                    self.context.absolute_url() + "/results"
                )

            saved_attachments = converter.save_attachments(attachments)
            try:
                converter.send_email(
                    email_to,
                    [output_path],
                    poll_id,
                    creator,
                    created,
                    saved_attachments,
                    sender=email_sender,
                    subject=email_subject,
                    body=email_body or None,
                    cc=email_cc,
                    bcc=email_bcc,
                )
            except Exception as exc:
                plone.api.portal.show_message(
                    _("Failed to send mail: ${error}", mapping={"error": str(exc)}),
                    type="error",
                )
                return self.request.response.redirect(
                    self.context.absolute_url() + "/results"
                )

        plone.api.portal.show_message(_("Mail sent"), type="info")
        return self.request.response.redirect(self.context.absolute_url() + "/results")

    def post_result(self):
        """POST a single poll result to the configured endpoint."""
        poll_id = self.request.form.get("poll_id")
        endpoint_url = getattr(self.context, "post_endpoint_url", None)
        actions = getattr(self.context, "actions", set()) or set()

        if not poll_id:
            plone.api.portal.show_message(_("Poll ID is required"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/results"
            )

        if "post" not in actions:
            plone.api.portal.show_message(
                _("POST action is not enabled for this survey"), type="error"
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/results"
            )

        if not endpoint_url:
            plone.api.portal.show_message(
                _("No POST endpoint configured for this survey"), type="error"
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/results"
            )

        storage = get_result_storage(self.context)
        result_data = storage.get_result(self.context, poll_id)

        if not result_data:
            plone.api.portal.show_message(_("Poll result not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/results"
            )

        annos = IAnnotations(self.context)
        form_json = self._latest_form_json(annos)
        if not form_json:
            plone.api.portal.show_message(
                _("No form definition available to include in POST"), type="error"
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/results"
            )

        created = result_data.get("created")
        if isinstance(created, datetime):
            created = ensure_timezone_aware(created).isoformat()

        payload = {
            "poll": dict(result_data, created=created),
            "form": form_json,
            "survey_url": getattr(self.context, "absolute_url", lambda: "")(),
        }

        try:
            response = httpx.post(endpoint_url, json=payload, timeout=10.0)
            response.raise_for_status()
            plone.api.portal.show_message(
                _(
                    "Result POSTed to endpoint (status ${status})",
                    mapping={"status": response.status_code},
                ),
                type="info",
            )
        except Exception as exc:
            plone.api.portal.show_message(
                _("Failed to POST result: ${error}", mapping={"error": str(exc)}),
                type="error",
            )
        return self.request.response.redirect(self.context.absolute_url() + "/results")

    @property
    def versions(self):
        """Get all form versions sorted by date (newest first)"""
        annos = IAnnotations(self.context)

        # Initialize if doesn't exist
        forms_service.ensure_form_versions(annos)
        return forms_service.sorted_form_versions(annos, reverse=True)

    @property
    def has_versions(self):
        """Check if any versions exist"""
        return len(self.versions) > 0

    def download_version(self):
        """Download a specific version as JSON file"""
        version_id = self.request.form.get("version_id")

        if not version_id:
            plone.api.portal.show_message(_("No version ID provided"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})

        version_data = form_versions.get(version_id)
        if not version_data:
            plone.api.portal.show_message(_("Version not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        # Prepare download
        filename = f"survey-form-{version_id[:8]}.json"
        json_content = orjson.dumps(
            version_data["form_json"], option=orjson.OPT_INDENT_2
        )

        self.request.response.setHeader("Content-Type", "application/json")
        self.request.response.setHeader(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        self.request.response.write(json_content)

    def restore_version(self):
        """Restore an old version by creating a new version with old content"""
        version_id = self.request.form.get("version_id")

        if not version_id:
            plone.api.portal.show_message(_("No version ID provided"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})

        old_version = form_versions.get(version_id)
        if not old_version:
            plone.api.portal.show_message(_("Version not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        # Create new version with old content (preserves history)
        forms_service.save_form_version(
            annos,
            old_version["form_json"],
            plone.api.user.get_current().getId(),
            locked=False,
        )

        plone.api.portal.show_message(
            _("Version restored successfully. A new version has been created."),
            type="info",
        )
        return self.request.response.redirect(
            self.context.absolute_url() + "/@@form-versions"
        )

    def toggle_version_lock(self):
        """Toggle lock state for a form version."""
        version_id = self.request.form.get("version_id")
        if not version_id:
            plone.api.portal.show_message(_("No version ID provided"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})
        version_data = form_versions.get(version_id)
        if not version_data:
            plone.api.portal.show_message(_("Version not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        locked = bool(version_data.get("locked"))
        version_data["locked"] = not locked
        form_versions[version_id] = version_data

        message = (
            _("Version locked") if version_data["locked"] else _("Version unlocked")
        )
        plone.api.portal.show_message(message, type="info")
        return self.request.response.redirect(
            self.context.absolute_url() + "/@@form-versions"
        )

    def delete_version(self):
        """Delete a form version unless locked."""
        version_id = self.request.form.get("version_id")
        if not version_id:
            plone.api.portal.show_message(_("No version ID provided"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})
        version_data = form_versions.get(version_id)
        if not version_data:
            plone.api.portal.show_message(_("Version not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        if version_data.get("locked"):
            plone.api.portal.show_message(
                _("Version is locked and cannot be deleted"), type="error"
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        del form_versions[version_id]
        plone.api.portal.show_message(_("Version deleted"), type="info")
        return self.request.response.redirect(
            self.context.absolute_url() + "/@@form-versions"
        )

    def upload_version(self):
        """Upload a JSON file and save as new version"""
        uploaded_file = self.request.form.get("json_file")

        if not uploaded_file:
            plone.api.portal.show_message(_("No file uploaded"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        try:
            # Read file content
            file_content = uploaded_file.read()
            if isinstance(file_content, bytes):
                file_content = file_content.decode("utf-8")

            # Parse and validate JSON
            json_data = orjson.loads(file_content)

            # Basic SurveyJS validation - check for required fields
            if not isinstance(json_data, dict):
                raise ValueError("JSON must be an object")

            # Optional: Add more specific SurveyJS structure validation
            # For now, basic validation that it's a dict is sufficient

        except (orjson.JSONDecodeError, ValueError) as e:
            plone.api.portal.show_message(
                _("Invalid JSON file: ${error}", mapping={"error": str(e)}),
                type="error",
            )
            return self.request.response.redirect(
                self.context.absolute_url() + "/@@form-versions"
            )

        # Save as new version
        annos = IAnnotations(self.context)
        forms_service.save_form_version(
            annos,
            json_data,
            plone.api.user.get_current().getId(),
            locked=False,
        )

        plone.api.portal.show_message(
            _("JSON uploaded successfully as new version"), type="info"
        )
        return self.request.response.redirect(
            self.context.absolute_url() + "/@@form-versions"
        )

    def view_version_json(self):
        """Return JSON for a specific version for viewing"""
        version_id = self.request.form.get("version_id")

        annos = IAnnotations(self.context)
        form_versions = annos.get(FORM_VERSIONS_KEY, {})

        version_data = form_versions.get(version_id)
        if not version_data:
            result = {"error": "Version not found"}
        else:
            result = version_data["form_json"]

        json_response(
            self.request.response,
            result,
            dumps_options=orjson.OPT_INDENT_2,
        )

    @property
    def results(self):
        """Get all poll results sorted by creation date (newest first)"""
        storage = get_result_storage(self.context)
        return storage.list_results(self.context)

    def get_paginated_results(self):
        """Return paginated results"""
        return results_service.get_paginated_results(self.results, self.request)

    def _parse_tabulator_param(self, name):
        return results_service.parse_tabulator_param(self.request, name)

    def _results2_row(self, entry):
        return results_service.results2_row(entry)

    def _results2_apply_filters(self, rows, filters):
        return results_service.results2_apply_filters(rows, filters)

    def results2_data(self):
        payload = results_service.build_results2_payload(self.results, self.request)
        json_response(self.request.response, payload)

    def view_result_json(self):
        """Return JSON for a specific poll result for viewing"""
        poll_id = self.request.form.get("poll_id")
        storage = get_result_storage(self.context)
        result_data = storage.get_result(self.context, poll_id)
        if not result_data:
            result = {"error": "Poll result not found"}
        else:
            result = result_data["result"]

        json_response(self.request.response, result)

    def result_detail(self):
        """Build HTML detail view data for a specific poll result."""
        poll_id = self.request.form.get("poll_id")
        if not poll_id:
            return {"error": "Poll ID is required"}
        storage = get_result_storage(self.context)
        result_data = storage.get_result(self.context, poll_id)
        if not result_data:
            return {"error": "Poll result not found"}

        annos = IAnnotations(self.context)
        form_json = self._latest_form_json(annos)
        if not form_json:
            return {"error": "No form definition available"}

        entry = result_data.get("result", {})
        creator = result_data.get("user")
        created = result_data.get("created")
        created_value = created
        if isinstance(created, datetime):
            created_value = ensure_timezone_aware(created).isoformat()

        from ..converters import build_markdown
        from ..converters.html import build_html
        from ..converters.cli import SurveyConverter

        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            data_path = tmpdir_path / "data.json"
            form_path = tmpdir_path / "form.json"
            output_dir = tmpdir_path / "output"

            data_payload = [self._serialize_result_entry(result_data)]
            data_path.write_bytes(orjson.dumps(data_payload))
            form_path.write_bytes(orjson.dumps(form_json))

            converter = SurveyConverter(data_path, form_path, output_dir)
            items, attachments = converter.collect_items(entry, poll_id)
            markdown_body = build_markdown(items, poll_id, creator, created_value)
            html_body = build_html(markdown_body, attachments)

        return {
            "poll_id": poll_id,
            "creator": creator or "",
            "created": self.format_created(created),
            "seq_no": result_data.get("seq_no", ""),
            "html": html_body,
            "formats": self.converter_formats,
        }

    @property
    def is_manager(self):
        """Return True if the current user has the Manager role"""
        return "Manager" in plone.api.user.get_roles(obj=self.context)

    @property
    def can_manage_portal_content(self):
        """Return True for Managers or users with Modify portal content."""
        return self.is_manager or plone.api.user.has_permission(
            "Modify portal content", obj=self.context
        )

    @property
    def trusted_access_enabled(self):
        return self._auth().trusted_access_enabled()

    def _require_manager(self):
        """Ensure the current user is a manager before performing a destructive action."""
        if self.is_manager:
            return True

        self.request.response.setStatus(403)
        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(
            orjson.dumps({"error": "You are not allowed to delete results"})
        )
        return False

    def delete_results(self):
        """Delete one or multiple poll results (Managers only)."""
        if not self._require_manager():
            return
        storage = get_result_storage(self.context)

        poll_ids = []

        # Accept JSON payload
        payload = parse_json_body(self.request)
        if isinstance(payload, dict):
            poll_ids = payload.get("poll_ids") or []

        # Fallback to form parameters
        poll_id = self.request.form.get("poll_id")
        if poll_id:
            poll_ids.append(poll_id)

        form_poll_ids = self.request.form.get("poll_ids")
        if form_poll_ids:
            if isinstance(form_poll_ids, (list, tuple)):
                poll_ids.extend(form_poll_ids)
            elif isinstance(form_poll_ids, str):
                poll_ids.append(form_poll_ids)

        if isinstance(poll_ids, str):
            poll_ids = [poll_ids]

        poll_ids = [pid for pid in poll_ids if pid]
        if not poll_ids:
            json_error(
                self.request.response,
                400,
                "No poll IDs provided for deletion",
            )
            return
        status = storage.delete_results(self.context, poll_ids)

        json_response(self.request.response, status)

    @property
    def has_mail_action(self):
        """Return True if the survey actions include mail."""
        actions = getattr(self.context, "actions", set()) or set()
        return "mail" in actions

    @property
    def has_post_action(self):
        """Return True if the survey actions include POST and have an endpoint."""
        actions = getattr(self.context, "actions", set()) or set()
        endpoint_url = getattr(self.context, "post_endpoint_url", None)
        return "post" in actions and bool(endpoint_url)

    @property
    def storing_enabled(self):
        """Return True if the survey actions include store."""
        actions = getattr(self.context, "actions", set()) or set()
        return "store" in actions

    @property
    def plone_api(self):
        return plone.api

    @property
    def surveyjs_license_key(self):
        """Return the configured SurveyJS license key."""
        try:
            from plone.registry.interfaces import IRegistry
            from zope.component import getUtility
            from ..interfaces import IFormsSettings

            registry = getUtility(IRegistry)
            settings = registry.forInterface(IFormsSettings, check=False)
            return (getattr(settings, "surveyjs_license_key", "") or "").strip()
        except Exception:
            return ""

    @property
    def embedding_allowed(self):
        """Check if embedding is allowed for this survey."""
        return getattr(self.context, "embedding_mode", "none") == "iframe"

    def generate_ai_form(self):
        """Generate a SurveyJS form using AI based on user prompt"""

        # Import AI generation functions
        try:
            from .ai_generator import generate_survey_json, strip_markdown_json
        except ImportError as e:
            error_result = {"error": "LLM module not available", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        # Get prompt from request
        prompt = self.request.form.get("prompt", "").strip()

        if not prompt:
            error_result = {
                "error": "No prompt provided",
                "message": "Please enter a description of the form you want to generate",
            }
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        try:
            model_name, api_key, ollama_url = ai_service.load_ai_settings()

            # Generate the survey JSON using LLM with configured settings
            survey_json_str = generate_survey_json(
                prompt,
                model_name=model_name,
                api_key=api_key,
                ollama_url=ollama_url,
            )

            # Strip any markdown formatting
            cleaned_json_str = strip_markdown_json(survey_json_str)

            # Validate JSON
            survey_data = orjson.loads(cleaned_json_str)

            # Return success with generated JSON
            result = {"success": True, "json": survey_data}

            self.request.response.setStatus(200)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(result))

        except orjson.JSONDecodeError as e:
            error_result = {
                "error": "Invalid JSON generated",
                "message": f"The AI generated invalid JSON: {str(e)}",
                "raw_output": cleaned_json_str
                if "cleaned_json_str" in locals()
                else survey_json_str,
            }
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

        except ValueError as e:
            error_result = {"error": "Configuration error", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

        except Exception as e:
            error_result = {"error": "Generation failed", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

    def save_ai_form(self):
        """Save AI-generated form as a new version"""

        try:
            # Get JSON from request
            form_json_str = self.request.form.get("form_json", "")

            if not form_json_str:
                raise ValueError("No form JSON provided")

            # Parse JSON
            json_form = orjson.loads(form_json_str)

            # Validate it's a dict (basic SurveyJS validation)
            if not isinstance(json_form, dict):
                raise ValueError("Form JSON must be an object")

            # Save as version (reuse existing pattern from save_form_json)
            annos = IAnnotations(self.context)
            data = forms_service.save_form_version(
                annos,
                json_form,
                plone.api.user.get_current().getId(),
                locked=False,
            )

            result = dict(
                success=True, message="Form saved successfully", version_id=data["id"]
            )

            self.request.response.setStatus(200)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(result))

        except orjson.JSONDecodeError as e:
            error_result = {"error": "Invalid JSON", "message": str(e)}
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

        except Exception as e:
            error_result = {"error": "Save failed", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

    def refine_ai_form(self):
        """Refine an existing SurveyJS form based on user feedback"""

        # Import AI generation functions
        try:
            from .ai_generator import refine_survey_json, strip_markdown_json
        except ImportError as e:
            error_result = {"error": "LLM module not available", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        # Get current JSON and refinement prompt from request
        current_json_str = self.request.form.get("current_json", "").strip()
        use_existing = self.request.form.get("use_existing", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        refinement_prompt = self.request.form.get("refinement_prompt", "").strip()

        if not current_json_str and use_existing:
            annos = IAnnotations(self.context)
            current_json = self._latest_form_json(annos)
            if not current_json:
                error_result = {
                    "error": "No existing form found",
                    "message": "No saved form version is available to refine",
                }
                self.request.response.setStatus(400)
                self.request.response.setHeader("content-type", "application/json")
                self.request.response.write(orjson.dumps(error_result))
                return
            current_json_str = orjson.dumps(current_json).decode("utf-8")

        if not current_json_str:
            error_result = {
                "error": "No current form provided",
                "message": "Current form JSON is required for refinement",
            }
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        if not refinement_prompt:
            error_result = {
                "error": "No refinement prompt provided",
                "message": "Please enter a description of the changes you want to make",
            }
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        try:
            # Parse current JSON
            current_json = orjson.loads(current_json_str)

            # Validate it's a dict (basic SurveyJS validation)
            if not isinstance(current_json, dict):
                raise ValueError("Current form JSON must be an object")

            model_name, api_key, ollama_url = ai_service.load_ai_settings()

            # Generate the refined survey JSON using LLM with configured settings
            refined_json_str = refine_survey_json(
                current_json,
                refinement_prompt,
                model_name=model_name,
                api_key=api_key,
                ollama_url=ollama_url,
            )

            # Strip any markdown formatting
            cleaned_json_str = strip_markdown_json(refined_json_str)

            # Validate JSON
            refined_data = orjson.loads(cleaned_json_str)

            # Validate it's still a dict
            if not isinstance(refined_data, dict):
                raise ValueError("Refined form must be a JSON object")

            # Return success with refined JSON
            result = {"success": True, "json": refined_data}

            self.request.response.setStatus(200)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(result))

        except orjson.JSONDecodeError as e:
            error_result = {
                "error": "Invalid JSON",
                "message": f"JSON parsing error: {str(e)}",
                "raw_output": cleaned_json_str
                if "cleaned_json_str" in locals()
                else refined_json_str
                if "refined_json_str" in locals()
                else current_json_str,
            }
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

        except ValueError as e:
            error_result = {"error": "Validation error", "message": str(e)}
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

        except Exception as e:
            error_result = {"error": "Refinement failed", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

    def import_pdf_form(self):
        """Import a SurveyJS form from a PDF by converting to PNG and using AI."""
        uploaded_file = self.request.form.get("pdf_file")

        if not uploaded_file:
            error_result = {
                "error": "No PDF uploaded",
                "message": "Please upload a PDF file to import",
            }
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        try:
            from .ai_generator import (
                generate_survey_json_from_image,
                strip_markdown_json,
            )
        except ImportError as e:
            error_result = {"error": "LLM module not available", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        try:
            file_content = uploaded_file.read()
            if not isinstance(file_content, bytes):
                file_content = file_content.encode("utf-8")

            with TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                pdf_path = temp_path / "uploaded.pdf"
                png_path = temp_path / "uploaded.png"

                pdf_path.write_bytes(file_content)

                command = [
                    "convert",
                    "-density",
                    "300",
                    str(pdf_path),
                    "-background",
                    "white",
                    "-alpha",
                    "remove",
                    "-alpha",
                    "off",
                    str(png_path),
                ]
                logger.info(
                    f"Executing ImageMagick convert command: {' '.join(command)}"
                )
                result = subprocess.run(command, check=True, capture_output=True)
                logger.info(
                    f"Convert command completed successfully. Output: {result.stdout.decode('utf-8', errors='ignore')}"
                )

                image_path = png_path
                if not image_path.exists():
                    candidates = sorted(temp_path.glob("uploaded*.png"))
                    if not candidates:
                        raise ValueError("PNG conversion failed: no output created")
                    image_path = candidates[0]

                model_name, api_key, ollama_url = ai_service.load_ai_settings()

                prompt = (
                    "Convert this PDF to SurveyJS JSON. Keep the layout, "
                    "keep headers and footer, make JSON as close possible as possible, "
                    "return the form JSON only"
                )

                survey_json_str = generate_survey_json_from_image(
                    str(image_path),
                    prompt,
                    model_name=model_name,
                    api_key=api_key,
                    ollama_url=ollama_url,
                )

            cleaned_json_str = strip_markdown_json(survey_json_str)
            survey_data = orjson.loads(cleaned_json_str)
            if not isinstance(survey_data, dict):
                raise ValueError("Form JSON must be an object")

            result = {
                "success": True,
                "json": survey_data,
            }
            self.request.response.setStatus(200)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(result))

        except subprocess.CalledProcessError as e:
            stderr_msg = e.stderr.decode("utf-8", errors="ignore") or str(e)
            logger.error(f"Convert command failed: {stderr_msg}")
            error_result = {
                "error": "PNG conversion failed",
                "message": stderr_msg,
            }
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

        except FileNotFoundError:
            logger.error("ImageMagick 'convert' command was not found on the system")
            error_result = {
                "error": "Conversion tool missing",
                "message": "ImageMagick 'convert' command was not found",
            }
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

        except orjson.JSONDecodeError as e:
            error_result = {
                "error": "Invalid JSON generated",
                "message": f"The AI generated invalid JSON: {str(e)}",
                "raw_output": cleaned_json_str
                if "cleaned_json_str" in locals()
                else survey_json_str,
            }
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

        except Exception as e:
            error_result = {"error": "Import failed", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

    def store_pdf_form(self):
        """Store a converted SurveyJS form as a new version."""
        payload = self.request.form.get("survey_json")
        if not payload:
            error_result = {
                "error": "Missing survey JSON",
                "message": "No survey JSON provided",
            }
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        try:
            survey_data = orjson.loads(payload)
            if not isinstance(survey_data, dict):
                raise ValueError("Form JSON must be an object")
        except Exception as e:
            error_result = {"error": "Invalid JSON", "message": str(e)}
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        annos = IAnnotations(self.context)
        data = forms_service.save_form_version(
            annos,
            survey_data,
            plone.api.user.get_current().getId(),
            locked=False,
        )

        result = {
            "success": True,
            "version_id": data["id"],
        }
        self.request.response.setStatus(200)
        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(result))


class EmbedViewer(Views):
    """View for embedding surveys in iframes"""

    index = ViewPageTemplateFile("viewer_embed.pt")

    def __call__(self):
        """Set appropriate headers for iframe embedding."""

        if not self.embedding_allowed:
            self.request.response.setStatus(403)
            return "Embedding is disabled for this survey."

        # Remove X-Frame-Options to allow iframe embedding.
        # Note: Setting to empty string removes the header.
        self.request.response.setHeader("X-Frame-Options", "")

        # Use Content-Security-Policy frame-ancestors instead.
        self.request.response.setHeader("Content-Security-Policy", "frame-ancestors *")

        # Render the template.
        return self.index()
