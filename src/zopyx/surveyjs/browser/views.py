from datetime import datetime, timezone, timedelta
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
from zope.schema.interfaces import ICollection, IChoice, IVocabularyFactory
from zope.component import getUtility
from zope.i18n import translate
import plone.api

from .. import _
from ..events import SurveyJSFormSubmitted
from ..constants import FORM_VERSIONS_KEY, PDF_FORM_KEY
from ..audit import audit_form_version_change
from ..storage import _get_storage_location, get_result_storage
from ..utils import ensure_timezone_aware
from ..data_validation.validate_data import validate_data as run_data_validation
from ..pdf_forms import fill_pdf_form as fill_pdf_form_bytes
from ..pdf_form_extract import PDFFormExtractor

import orjson
import uuid
from plone.namedfile.file import NamedBlobFile

from .services import ai as ai_service
from .services import auth as auth_service
from .services import export as export_service
from .services import forms as forms_service
from .services import pdf as pdf_service
from .services import results as results_service
from .services.http import json_error, json_response

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


def _find_sample_forms_dir() -> Path | None:
    start = Path(__file__).resolve()
    for parent in start.parents:
        candidate = parent / "sample_forms"
        if candidate.is_dir():
            return candidate
    return None


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


class RootRedirect(BrowserView):
    """Redirect the Plone root to the English language root."""

    def __call__(self):
        target = self.context.get("en")
        if target is not None:
            return self.request.response.redirect(target.absolute_url())
        return self.request.response.redirect(self.context.absolute_url())


class Views(BrowserView):
    @property
    def survey_language_labels(self) -> dict[str, str]:
        from ..content.survey import survey_languages_vocabulary

        labels: dict[str, str] = {}
        for term in survey_languages_vocabulary:
            value = getattr(term, "value", None)
            if not value:
                continue
            title = getattr(term, "title", None) or str(value)
            labels[str(value)] = str(title)
        return labels

    @property
    def can_add_survey(self) -> bool:
        return plone.api.user.has_permission(
            "zopyx.surveyjs.AddSurvey", obj=self.context
        )

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

    def _parse_download_date(self, raw_value, is_end=False):
        if not raw_value:
            return None
        value = str(raw_value).strip()
        if not value:
            return None
        try:
            if len(value) <= 10:
                date_value = datetime.fromisoformat(value)
                dt = datetime(
                    date_value.year,
                    date_value.month,
                    date_value.day,
                    tzinfo=timezone.utc,
                )
                if is_end:
                    dt = dt + timedelta(days=1)
                return dt
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            dt = datetime.fromisoformat(value)
            dt = ensure_timezone_aware(dt)
            return dt
        except Exception:
            return None

    def _download_date_range(self):
        raw_from = self.request.form.get("from")
        raw_to = self.request.form.get("to")
        start = self._parse_download_date(raw_from, is_end=False)
        end = self._parse_download_date(raw_to, is_end=True)
        return start, end

    def _filter_results_by_date(self, results):
        start, end = self._download_date_range()
        if start or end:
            logger.info(
                "Applying export filter (from=%s, to=%s) for %s",
                start.isoformat() if start else "",
                end.isoformat() if end else "",
                self.context.absolute_url(),
            )
        if not start and not end:
            return results
        filtered = []
        for entry in results:
            created = entry.get("created")
            if isinstance(created, str):
                created_value = self._parse_download_date(created, is_end=False)
            elif isinstance(created, datetime):
                created_value = ensure_timezone_aware(created)
            else:
                created_value = None
            if not created_value:
                continue
            if start and created_value < start:
                continue
            if end and created_value >= end:
                continue
            filtered.append(entry)
        return filtered

    def _ensure_private(self, obj):
        try:
            state = plone.api.content.get_state(obj)
        except Exception:
            return False
        if state == "private":
            return True
        try:
            transitions = plone.api.content.get_transitions(obj)
        except Exception:
            transitions = []
        transition_ids = {item.get("id") for item in transitions if item.get("id")}
        for candidate in ("retract", "hide", "make-private"):
            if candidate in transition_ids:
                try:
                    plone.api.content.transition(obj=obj, transition=candidate)
                    return True
                except Exception:
                    continue
        return False

    def get_ai_model(self) -> str:
        """Return the AI backend type based on configured settings."""
        model_name, _api_key, ollama_url = ai_service.load_ai_settings()
        if ollama_url:
            return "local"
        if model_name:
            return "remote"
        return "no_ai"

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

    def _translate_label(self, value):
        if not value:
            return ""
        try:
            return translate(value, context=self.request)
        except Exception:
            return str(value)

    def _vocabulary_title(self, field, value):
        if not field:
            return str(value)
        vocab = getattr(field, "vocabulary", None)
        if vocab is None:
            vocab_name = getattr(field, "vocabularyName", None)
            if vocab_name:
                try:
                    vocab = getUtility(IVocabularyFactory, vocab_name)(self.context)
                except Exception:
                    vocab = None
        if vocab is None:
            return str(value)
        try:
            term = vocab.getTerm(value)
            title = term.title if term else value
            return self._translate_label(title)
        except Exception:
            return str(value)

    def _survey_field_value_text(self, obj, name, field):
        if not hasattr(obj, name):
            return ""
        value = getattr(obj, name)
        if callable(value):
            try:
                value = value()
            except Exception:
                return ""
        if value is None:
            return ""
        if hasattr(value, "filename"):
            return value.filename or ""
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if ICollection.providedBy(field):
            if not value:
                return ""
            values = list(value)
            if isinstance(value, set):
                values = sorted(values, key=lambda item: str(item))
            return ", ".join(
                [
                    str(self._vocabulary_title(field.value_type, item))
                    for item in values
                    if item or item == 0
                ]
            )
        if IChoice.providedBy(field):
            return str(self._vocabulary_title(field, value))
        if isinstance(value, (list, tuple)):
            return ", ".join([str(item) for item in value if item or item == 0])
        return str(value)

    def _compact_metadata_value(self, value, max_len=160):
        text = (value or "").strip()
        if not text:
            return "—", ""
        if len(text) <= max_len:
            return text, text
        return text[: max_len - 3].rstrip() + "...", text

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
            previous_versions = forms_service.sorted_form_versions(annos)
            previous_version = previous_versions[-1] if previous_versions else None
            version_data = forms_service.save_form_version(
                annos,
                survey_json,
                plone.api.user.get_current().getId(),
                locked=False,
            )
            version_id = version_data["id"]
            audit_form_version_change(
                self.context,
                form_json=survey_json,
                source="upload_pdf_form",
                new_version_id=version_id,
                previous_version_id=previous_version["id"]
                if previous_version
                else None,
                previous_form_json=previous_version.get("form_json")
                if previous_version
                else None,
                locked=version_data.get("locked"),
                extra={
                    "pdf_filename": filename,
                    "pdf_extract_mode": extract_mode,
                    "pdf_field_count": len(field_map),
                },
            )

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
        previous_versions = forms_service.sorted_form_versions(annos)
        previous_version = previous_versions[-1] if previous_versions else None
        data = forms_service.save_form_version(
            annos,
            json_form,
            plone.api.user.get_current().getId(),
            locked=False,
        )
        audit_form_version_change(
            self.context,
            form_json=json_form,
            source="editor",
            new_version_id=data["id"],
            previous_version_id=previous_version["id"] if previous_version else None,
            previous_form_json=previous_version.get("form_json")
            if previous_version
            else None,
            locked=data.get("locked"),
        )

        json_response(self.request.response, dict(isSuccess=True))

    def save_poll(self):
        # Handle CORS preflight for embed submissions.
        # OPTIONS requests carry no token — check method first, before token presence.
        origin = self.request.get_header("Origin") or self.request.get("HTTP_ORIGIN")
        embed_token = self.request.get_header("X-Embed-Token")

        if origin:
            from .embed_security import handle_cors_preflight
            allowed_origins = list(
                getattr(self.context, "embed_direct_origins", []) or []
            )
            if handle_cors_preflight(self.request, self.request.response, allowed_origins):
                return
        
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

        # Check for direct DOM embed submission
        origin = self.request.get_header("Origin") or self.request.get("HTTP_ORIGIN")
        embed_token = self.request.get_header("X-Embed-Token")
        
        if origin and embed_token:
            # This is a direct embed submission - validate it
            from .embed_security import (
                validate_embed_token,
                validate_origin,
                set_cors_headers,
            )
            import logging as _logging
            _audit = _logging.getLogger("zopyx.surveyjs.embed.audit")
            remote_addr = self.request.get("REMOTE_ADDR", "")

            allowed_origins = list(
                getattr(self.context, "embed_direct_origins", []) or []
            )

            is_valid, normalized_origin, error_msg = validate_origin(
                origin, allowed_origins
            )

            # Only set CORS headers for allowlisted origins
            if is_valid and normalized_origin:
                set_cors_headers(self.request.response, normalized_origin)

            if not is_valid:
                _audit.info(
                    "embed.submission.rejected",
                    extra={"reason": "invalid_origin", "origin": origin, "remote_addr": remote_addr}
                )
                json_error(
                    self.request.response,
                    403,
                    "invalid_origin",
                    message=error_msg,
                    extra={"isSuccess": False},
                )
                return

            try:
                validate_embed_token(embed_token, normalized_origin, secret=None)
            except Exception as e:
                _audit.info(
                    "embed.submission.rejected",
                    extra={"reason": "invalid_token", "origin": origin, "remote_addr": remote_addr}
                )
                json_error(
                    self.request.response,
                    403,
                    "invalid_token",
                    message=str(e),
                    extra={"isSuccess": False},
                )
                return

            _audit.info(
                "embed.submission.accepted",
                extra={"origin": normalized_origin, "remote_addr": remote_addr}
            )
            # Embed validation passed — skip trusted access and auth token checks
            pass
        else:
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
        results = self._filter_results_by_date(storage.list_results(self.context))
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
        results = self._filter_results_by_date(storage.list_results(self.context))
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
        if self.can_manage_portal_content:
            return True
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
        settings = self._get_forms_settings()
        if not settings:
            return ""
        return (getattr(settings, "surveyjs_license_key", "") or "").strip()

    def _get_forms_settings(self):
        try:
            from plone.registry.interfaces import IRegistry
            from zope.component import getUtility
            from ..interfaces import IFormsSettings

            registry = getUtility(IRegistry)
            return registry.forInterface(IFormsSettings, check=False)
        except Exception:
            return None

    @property
    def features_enabled(self):
        settings = self._get_forms_settings()
        if not settings:
            return set()
        values = getattr(settings, "features_enabled", []) or []
        return set(values)

    def feature_enabled(self, feature_name):
        return feature_name in self.features_enabled

    def require_feature(self, feature_name):
        if self.feature_enabled(feature_name):
            return True
        target = f"{self.context.absolute_url()}/@@feature-disabled"
        self.request.response.redirect(target)
        return False

    @property
    def embedding_allowed(self):
        """Check if embedding is allowed for this survey."""
        return getattr(self.context, "embedding_mode", "none") == "iframe"

    @property
    def direct_embedding_allowed(self):
        """Check if direct DOM embedding is allowed for this survey."""
        return getattr(self.context, "embedding_mode", "none") == "direct"

    @property
    def embed_direct_demo_url(self):
        """URL for the direct embed demo page."""
        return f"{self.context.absolute_url()}/@@embed-direct-demo"

    def import_pdf_form(self):
        """Import a SurveyJS form from an uploaded PDF and generate SurveyJS JSON.

        Request/inputs
        - Expects a multipart form upload with a ``pdf_file`` field.
        - Reads the uploaded file as bytes to preserve PDF binary content.

        Processing pipeline (high-level)
        1) Validate upload: Ensure the PDF file is present; otherwise return 400.
        2) Temp workspace: Create a temporary directory to isolate intermediate
           artifacts and ensure they are removed automatically.
        3) Persist PDF: Write the uploaded bytes to ``uploaded.pdf``.
        4) Render all pages to PNG:
           - Uses ImageMagick ``convert`` with 300 DPI, white background, and
             alpha removal to produce clean raster images.
           - Output naming pattern (``uploaded.png``) expands to multiple files
             (e.g., ``uploaded-0.png``, ``uploaded-1.png``) when the PDF has
             multiple pages.
           - The resulting PNGs are collected via ``uploaded*.png``.
        5) Optionally extract PDF form representation (if pdfcpu validation enabled):
           - Runs ``pdfcpu form export`` through :class:`PDFFormExtractor`.
           - Stores the raw JSON payload to ``forms.json`` for traceability.
        6) Log assets:
           - Logs absolute paths to all PNGs and ``forms.json`` when available.
        7) Build LLM prompt:
           - Starts with a base instruction prompt to preserve layout and emit
             SurveyJS JSON only.
           - Appends extracted form JSON (when available) inside a triple-quoted
             block to provide the LLM with explicit field metadata and structure
             hints.
        8) Call LLM:
           - Uses ``generate_survey_json_from_assets`` to attach all PNG pages.
           - Provides the augmented prompt including embedded form JSON.
        9) Parse LLM response:
           - Removes any markdown wrapping via ``strip_markdown_json``.
           - Parses JSON and enforces an object payload.
        10) Respond:
           - Returns ``{\"success\": true, \"json\": <survey>}`` as JSON.

        Outputs
        - HTTP 200 with generated SurveyJS form JSON object on success.
        - HTTP 400/500 with JSON error payload on failure.

        Error handling (JSON responses)
        - Missing upload → 400 with ``No PDF uploaded``.
        - Missing LLM module → 500 with module error details.
        - ImageMagick conversion failure → 500 with stderr.
        - ``convert`` binary missing → 500 with tool missing message.
        - Invalid JSON from LLM → 500 with raw output for debugging.
        - Any other exception → 500 with error message.

        Dependencies
        - ImageMagick ``convert`` available on PATH.
        - ``pdfcpu`` available on PATH when validation is enabled.
        - ``llm`` package and configured model for AI generation.
        """
        uploaded_file = self.request.form.get("pdf_file")
        additional_prompt = self.request.form.get("additional_prompt")
        pdfcpu_validation_raw = self.request.form.get("pdfcpu_validation", "1")
        use_pdfcpu_validation = str(pdfcpu_validation_raw).strip().lower() not in (
            "0",
            "false",
            "off",
            "no",
            "",
        )

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
                generate_survey_json_from_assets,
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
                stdout_text = (
                    result.stdout.decode("utf-8", errors="ignore")
                    if isinstance(result.stdout, bytes)
                    else (result.stdout or "")
                )
                logger.info(
                    f"Convert command completed successfully. Output: {stdout_text}"
                )

                png_candidates = sorted(temp_path.glob("uploaded*.png"))
                if not png_candidates:
                    raise ValueError("PNG conversion failed: no output created")

                forms_json_text = None
                if use_pdfcpu_validation:
                    forms_json_path = temp_path / "forms.json"
                    extractor = PDFFormExtractor(str(pdf_path))
                    forms_json_text = extractor.extract()
                    forms_json_path.write_text(forms_json_text, encoding="utf-8")
                    logger.info(
                        "Extracted PDF assets: %s",
                        ", ".join(
                            [str(p) for p in png_candidates] + [str(forms_json_path)]
                        ),
                    )
                else:
                    logger.info(
                        "Extracted PDF assets: %s",
                        ", ".join([str(p) for p in png_candidates]),
                    )

                model_name, api_key, ollama_url = ai_service.load_ai_settings()

                prompt = (
                    "Convert this PDF to SurveyJS JSON. Keep the layout, "
                    "keep headers and footer, make JSON as close possible as possible, "
                    "return the form JSON only"
                )
                if additional_prompt:
                    prompt = f"{prompt}\nAdditional instructions: {additional_prompt}"
                if forms_json_text:
                    prompt = (
                        f"{prompt}. Here is the form represenation of the form as JSON:\n"
                        f'"""\n```\n{forms_json_text}\n```\n"""\n'
                    )
                survey_json_str = generate_survey_json_from_assets(
                    [str(p) for p in png_candidates],
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
            stderr_msg = (
                e.stderr.decode("utf-8", errors="ignore")
                if isinstance(e.stderr, bytes)
                else (e.stderr or str(e))
            )
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
        previous_versions = forms_service.sorted_form_versions(annos)
        previous_version = previous_versions[-1] if previous_versions else None
        data = forms_service.save_form_version(
            annos,
            survey_data,
            plone.api.user.get_current().getId(),
            locked=False,
        )
        audit_form_version_change(
            self.context,
            form_json=survey_data,
            source="store_pdf_form",
            new_version_id=data["id"],
            previous_version_id=previous_version["id"] if previous_version else None,
            previous_form_json=previous_version.get("form_json")
            if previous_version
            else None,
            locked=data.get("locked"),
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


class EmbeddedDemoView(BrowserView):
    """Manager-only demo page embedding a fixed survey via iframe."""

    @property
    def iframe_url(self):
        portal = plone.api.portal.get()
        return (
            f"{portal.absolute_url()}/de/demos/mental-health-survey-de/@@viewer-embed"
        )
