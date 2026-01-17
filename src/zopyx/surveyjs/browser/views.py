from BTrees.OOBTree import OOBTree
from datetime import datetime, timezone
from string import Formatter
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import platform
import time
import csv
import io
import hashlib
import logging
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.annotation.interfaces import IAnnotations
from zope.event import notify
import plone.api
import httpx

from .. import _
from ..events import SurveyJSFormSubmitted
from ..validation import validate_submission

import orjson
import uuid


logger = logging.getLogger(__name__)

RESULTS_KEY = "zopyx.surveyjs.results"
FORM_VERSIONS_KEY = "zopyx.surveyjs.form_versions"
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


def ensure_timezone_aware(dt):
    """Convert naive datetime to UTC-aware datetime"""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        # Naive datetime - assume it's UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _extract_json_object(raw_text: str) -> str | None:
    """Best-effort extraction of a JSON object from noisy text."""
    if not raw_text:
        return None
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return raw_text[start : end + 1]


def _resolve_validation_binary() -> Path | None:
    binary_suffix = None
    system_name = platform.system().lower()
    if system_name == "darwin":
        binary_suffix = "macos"
    elif system_name == "linux":
        binary_suffix = "linux"
    if not binary_suffix:
        return None

    for parent in Path(__file__).resolve().parents:
        dist_dir = parent / "data-validation" / "dist"
        if dist_dir.is_dir():
            candidate = dist_dir / f"survey-validate-{binary_suffix}-deno"
            if candidate.exists():
                return candidate
    return None


def _run_external_validation(form_json, poll_result, submission_hash: str):
    binary_path = _resolve_validation_binary()
    if not binary_path:
        logger.info(
            "Survey external validation missing binary: submission=%s",
            submission_hash,
        )
        return dict(ok=False, status=500, reason="external_validator_missing")

    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        schema_path = tmpdir_path / "schema.json"
        data_path = tmpdir_path / "data.json"
        result_path = tmpdir_path / "validation.json"

        schema_bytes = orjson.dumps(form_json)
        data_bytes = orjson.dumps(poll_result)
        schema_path.write_bytes(schema_bytes)
        data_path.write_bytes(data_bytes)

        cmd = [
            str(binary_path),
            "--schema-json",
            str(schema_path),
            "--form-json",
            str(data_path),
            "--result-json",
            str(result_path),
        ]

        logger.info(
            "Survey external validation start: binary=%s schema_bytes=%s data_bytes=%s submission=%s",
            binary_path,
            len(schema_bytes),
            len(data_bytes),
            submission_hash,
        )

        start_time = time.monotonic()
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        duration = time.monotonic() - start_time

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        logger.info(
            "Survey external validation done: rc=%s duration=%.3fs stdout=%s stderr=%s submission=%s",
            completed.returncode,
            duration,
            stdout,
            stderr,
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

        if completed.returncode != 0 and not result_data:
            return dict(ok=False, status=500, reason="external_validator_error")

        if result_data and not result_data.get("valid", True):
            return dict(
                ok=False,
                status=400,
                reason="external_validation_failed",
                details=result_data,
            )

        if completed.returncode != 0:
            return dict(ok=False, status=500, reason="external_validator_error")

        return dict(ok=True, status=200, reason="external_validation_ok", details=result_data)


class Views(BrowserView):
    def format_created(self, created):
        if isinstance(created, str):
            value = created.strip()
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            try:
                created = datetime.fromisoformat(value)
            except ValueError:
                return created
        if isinstance(created, datetime):
            created = ensure_timezone_aware(created).replace(tzinfo=None)
            return created.replace(microsecond=0).isoformat()
        return created

    def get_form_json(self):
        """JSON for SurveyJS renderer"""

        annos = IAnnotations(self.context)
        if FORM_VERSIONS_KEY not in annos:
            return {}

        form_versions = [d for d in annos[FORM_VERSIONS_KEY].values()]
        form_versions = sorted(
            form_versions, key=lambda x: ensure_timezone_aware(x["created"])
        )

        form_data = {}
        if form_versions:
            form_data = form_versions[-1]["form_json"]

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(form_data))

    def save_form_json(self):
        json_form = orjson.loads(self.request.form["surveyText"])

        annos = IAnnotations(self.context)

        data = dict(
            id=str(uuid.uuid4()),
            created=datetime.now(timezone.utc),
            user=plone.api.user.get_current().getId(),
            form_json=json_form,
            locked=False,
        )

        annos[FORM_VERSIONS_KEY][data["id"]] = data

        result = dict(isSuccess=True)
        self.request.response.setStatus(200)
        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(result))

    def save_poll(self):
        raw_poll = self.request.form.get("pollResult")
        if raw_poll is None:
            logger.warning("Survey save failed: status=400 reason=missing_poll_result")
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(
                orjson.dumps(
                    {"isSuccess": False, "error": "missing_poll_result"}
                )
            )
            return

        if isinstance(raw_poll, bytes):
            raw_bytes = raw_poll
        elif isinstance(raw_poll, str):
            raw_bytes = raw_poll.encode("utf-8")
        else:
            logger.warning("Survey save failed: status=400 reason=invalid_payload")
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(
                orjson.dumps({"isSuccess": False, "error": "invalid_payload"})
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
                    logger.warning("Survey save failed: status=413 reason=request_too_large")
                    self.request.response.setStatus(413)
                    self.request.response.setHeader("content-type", "application/json")
                    self.request.response.write(
                        orjson.dumps(
                            {"isSuccess": False, "error": "request_too_large"}
                        )
                    )
                    return
            except ValueError:
                pass
        elif len(raw_bytes) > max_payload_bytes:
            logger.warning("Survey save failed: status=413 reason=request_too_large")
            self.request.response.setStatus(413)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(
                orjson.dumps({"isSuccess": False, "error": "request_too_large"})
            )
            return

        if len(raw_bytes) > max_payload_bytes:
            logger.warning("Survey save failed: status=413 reason=json_too_large")
            self.request.response.setStatus(413)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(
                orjson.dumps({"isSuccess": False, "error": "json_too_large"})
            )
            return

        try:
            poll_result = orjson.loads(raw_bytes)
        except orjson.JSONDecodeError:
            logger.warning("Survey save failed: status=400 reason=invalid_json")
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(
                orjson.dumps({"isSuccess": False, "error": "invalid_json"})
            )
            return

        actions = getattr(self.context, "actions", set()) or set()
        annos = IAnnotations(self.context)
        if FORM_VERSIONS_KEY not in annos:
            annos[FORM_VERSIONS_KEY] = OOBTree()

        form_versions = [d for d in annos[FORM_VERSIONS_KEY].values()]
        form_versions = sorted(
            form_versions, key=lambda x: ensure_timezone_aware(x["created"])
        )
        form_version_id = form_versions[-1]["id"] if form_versions else None
        form_json = form_versions[-1]["form_json"] if form_versions else {}

        if not form_json:
            logger.warning("Survey save failed: status=400 reason=missing_form_schema")
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(
                orjson.dumps({"isSuccess": False, "error": "missing_form_schema"})
            )
            return

        submission_hash = hashlib.sha256(raw_bytes).hexdigest()[:12]
        if getattr(self.context, "validation_enabled", False):
            validation = validate_submission(form_json, poll_result)
            if not validation.ok:
                logger.warning(
                    "Survey validation failed: ok=%s reason=%s field=%s size=%s submission=%s",
                    validation.ok,
                    validation.reason,
                    validation.field,
                    len(raw_bytes),
                    submission_hash,
                )
                payload = {"isSuccess": False, "error": validation.reason}
                if validation.field:
                    payload["field"] = validation.field
                self.request.response.setStatus(validation.status)
                self.request.response.setHeader("content-type", "application/json")
                self.request.response.write(orjson.dumps(payload))
                return
            logger.info(
                "Survey validation ok: ok=%s size=%s submission=%s",
                validation.ok,
                len(raw_bytes),
                submission_hash,
            )
        else:
            logger.info(
                "Survey validation skipped: enabled=%s size=%s submission=%s",
                False,
                len(raw_bytes),
                submission_hash,
            )

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
                self.request.response.setStatus(external_validation.get("status", 500))
                self.request.response.setHeader("content-type", "application/json")
                self.request.response.write(orjson.dumps(payload))
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
        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(result))

    def clear_results(self):
        annos = IAnnotations(self.context)
        annos[RESULTS_KEY] = OOBTree()

        plone.api.portal.show_message(_("Results cleared"))
        self.request.response.redirect(self.context.absolute_url() + "/view")

    def get_polls_json(self):
        """get polls"""

        annos = IAnnotations(self.context)

        results = list(annos[RESULTS_KEY].values())
        results = sorted(
            results, key=lambda x: ensure_timezone_aware(x["created"]), reverse=True
        )

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(results))

    def get_polls_json2(self):
        """get polls"""

        annos = IAnnotations(self.context)

        # Initialize if doesn't exist
        if RESULTS_KEY not in annos:
            annos[RESULTS_KEY] = OOBTree()

        results = list(annos[RESULTS_KEY].values())
        results = [d["result"] for d in results]

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(results))

    def download_form_json(self):
        """Download current form JSON as attachment"""
        annos = IAnnotations(self.context)

        # Initialize if doesn't exist
        if FORM_VERSIONS_KEY not in annos:
            annos[FORM_VERSIONS_KEY] = OOBTree()

        form_versions = [d for d in annos[FORM_VERSIONS_KEY].values()]
        form_versions = sorted(
            form_versions, key=lambda x: ensure_timezone_aware(x["created"])
        )

        form_data = {}
        if form_versions:
            form_data = form_versions[-1]["form_json"]

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
        annos = IAnnotations(self.context)
        annos.setdefault(RESULTS_KEY, OOBTree())

        results = list(annos[RESULTS_KEY].values())
        results = sorted(
            results, key=lambda x: ensure_timezone_aware(x["created"]), reverse=True
        )

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
        annos = IAnnotations(self.context)

        # Initialize if doesn't exist
        if RESULTS_KEY not in annos:
            annos[RESULTS_KEY] = OOBTree()

        results = list(annos[RESULTS_KEY].values())
        results = sorted(
            results, key=lambda x: ensure_timezone_aware(x["created"]), reverse=True
        )

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
        form_versions = [d for d in annos.get(FORM_VERSIONS_KEY, {}).values()]
        form_versions = sorted(
            form_versions, key=lambda x: ensure_timezone_aware(x["created"])
        )
        return form_versions[-1]["form_json"] if form_versions else {}

    def _serialize_result_entry(self, result_entry):
        serialized = dict(result_entry)
        created = serialized.get("created")
        if isinstance(created, datetime):
            serialized["created"] = ensure_timezone_aware(created).isoformat()
        return serialized

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
        output_path = None
        if format_key == "text":
            from ..converters import write_text

            output_path = write_text(
                items, output_dir / f"{poll_id}.txt", creator, created
            )
        elif format_key == "md":
            from ..converters import write_markdown

            output_path = write_markdown(
                items, poll_id, output_dir / f"{poll_id}.md", creator, created
            )
        elif format_key == "html":
            from ..converters import build_markdown, write_html

            markdown_body = build_markdown(items, poll_id, creator, created)
            output_path = write_html(
                markdown_body, attachments, output_dir / f"{poll_id}.html"
            )
        elif format_key == "pdf":
            from ..converters import build_markdown, write_pdf
            from ..converters.html import build_html

            markdown_body = build_markdown(items, poll_id, creator, created)
            html_body = build_html(markdown_body, attachments)
            output_path = write_pdf(
                html_body, output_dir / f"{poll_id}.pdf", creator, created
            )
        elif format_key in {"csv", "xlsx"}:
            from ..converters import build_table_rows, write_csv, write_xlsx

            table_rows = build_table_rows(items)
            if format_key == "csv":
                output_path = write_csv(table_rows, output_dir / f"{poll_id}.csv")
            else:
                output_path = write_xlsx(table_rows, output_dir / f"{poll_id}.xlsx")
        elif format_key == "xml":
            from ..converters import write_xml

            output_path = write_xml(items, poll_id, output_dir / f"{poll_id}.xml")
        elif format_key == "docx":
            from ..converters import write_docx

            output_path = write_docx(
                items,
                output_dir / f"{poll_id}.docx",
                poll_id,
                creator,
                created,
            )
        elif format_key == "json":
            from ..converters import write_json

            output_path = write_json(
                items, poll_id, output_dir / f"{poll_id}.json", creator, created
            )
        return output_path

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

        annos = IAnnotations(self.context)
        results = annos.get(RESULTS_KEY, {})
        result_data = results.get(poll_id)

        if not result_data:
            plone.api.portal.show_message(_("Poll result not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/results"
            )

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

        annos = IAnnotations(self.context)
        results = annos.get(RESULTS_KEY, {})
        result_data = results.get(poll_id)

        if not result_data:
            plone.api.portal.show_message(_("Poll result not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/results"
            )

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

        annos = IAnnotations(self.context)
        results = annos.get(RESULTS_KEY, {})
        result_data = results.get(poll_id)

        if not result_data:
            plone.api.portal.show_message(_("Poll result not found"), type="error")
            return self.request.response.redirect(
                self.context.absolute_url() + "/results"
            )

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
        if FORM_VERSIONS_KEY not in annos:
            annos[FORM_VERSIONS_KEY] = OOBTree()

        # Get all versions
        form_versions = list(annos[FORM_VERSIONS_KEY].values())

        # Sort by created date, newest first
        return sorted(
            form_versions,
            key=lambda x: ensure_timezone_aware(x["created"]),
            reverse=True,
        )

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
        new_version = dict(
            id=str(uuid.uuid4()),
            created=datetime.now(timezone.utc),
            user=plone.api.user.get_current().getId(),
            form_json=old_version["form_json"],
            locked=False,
        )

        annos[FORM_VERSIONS_KEY][new_version["id"]] = new_version

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

        message = _("Version locked") if version_data["locked"] else _("Version unlocked")
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
        if FORM_VERSIONS_KEY not in annos:
            annos[FORM_VERSIONS_KEY] = OOBTree()

        new_version = dict(
            id=str(uuid.uuid4()),
            created=datetime.now(timezone.utc),
            user=plone.api.user.get_current().getId(),
            form_json=json_data,
            locked=False,
        )

        annos[FORM_VERSIONS_KEY][new_version["id"]] = new_version

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

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(result, option=orjson.OPT_INDENT_2))

    @property
    def results(self):
        """Get all poll results sorted by creation date (newest first)"""
        annos = IAnnotations(self.context)

        # Initialize if doesn't exist
        if RESULTS_KEY not in annos:
            annos[RESULTS_KEY] = OOBTree()

        # Get all results
        results = list(annos[RESULTS_KEY].values())

        # Sort by created date, newest first
        return sorted(
            results, key=lambda x: ensure_timezone_aware(x["created"]), reverse=True
        )

    def get_paginated_results(self):
        """Return paginated results"""
        q = self.request.form.get("q", "").lower()
        b_start = int(self.request.form.get("b_start", 0))
        pagesize = 10

        all_results = self.results
        if q:

            def _matches_query(result):
                user = (result.get("user") or "").lower()
                poll_id = (result.get("poll_id") or "").lower()
                created = (self.format_created(result.get("created")) or "").lower()
                result_uuid = ""
                result_payload = result.get("result") or {}
                if isinstance(result_payload, dict):
                    result_uuid = (result_payload.get("uuid") or "").lower()
                return q in user or q in poll_id or q in result_uuid or q in created

            all_results = [r for r in all_results if _matches_query(r)]

        total = len(all_results)
        numpages = total // pagesize
        if total % pagesize > 0:
            numpages += 1
        page = b_start // pagesize + 1
        return dict(
            items=all_results[b_start : b_start + pagesize],
            total=total,
            numpages=numpages,
            page=page,
            pagesize=pagesize,
            q=q,
        )

    def view_result_json(self):
        """Return JSON for a specific poll result for viewing"""
        poll_id = self.request.form.get("poll_id")

        annos = IAnnotations(self.context)
        results = annos.get(RESULTS_KEY, {})

        result_data = results.get(poll_id)
        if not result_data:
            result = {"error": "Poll result not found"}
        else:
            result = result_data["result"]

        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(result, option=orjson.OPT_INDENT_2))

    def result_detail(self):
        """Build HTML detail view data for a specific poll result."""
        poll_id = self.request.form.get("poll_id")
        if not poll_id:
            return {"error": "Poll ID is required"}

        annos = IAnnotations(self.context)
        results = annos.get(RESULTS_KEY, {})
        result_data = results.get(poll_id)
        if not result_data:
            return {"error": "Poll result not found"}

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

        annos = IAnnotations(self.context)
        annos.setdefault(RESULTS_KEY, OOBTree())
        results = annos[RESULTS_KEY]

        poll_ids = []

        # Accept JSON payload
        raw_body = self.request.get("BODY", b"")
        if isinstance(raw_body, str):
            raw_body = raw_body.encode("utf-8")
        if raw_body:
            try:
                payload = orjson.loads(raw_body)
                if isinstance(payload, dict):
                    poll_ids = payload.get("poll_ids") or []
            except orjson.JSONDecodeError:
                pass

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
        deleted = []
        missing = []

        for pid in poll_ids:
            if pid in results:
                del results[pid]
                deleted.append(pid)
            else:
                missing.append(pid)

        if not poll_ids:
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(
                orjson.dumps({"error": "No poll IDs provided for deletion"})
            )
            return

        self.request.response.setStatus(200)
        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(
            orjson.dumps({"deleted": deleted, "missing": missing})
        )

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
            return (getattr(settings, "surveyjs_licence_key", "") or "").strip()
        except Exception:
            return ""

    @property
    def embedding_allowed(self):
        """Check if embedding is allowed for this survey"""
        return getattr(self.context, "allow_embedding", False)

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
            # Get AI settings from registry
            from plone.registry.interfaces import IRegistry
            from zope.component import getUtility
            from ..interfaces import IFormsSettings

            registry = getUtility(IRegistry)
            settings = registry.forInterface(IFormsSettings, check=False)

            # Get configured model, API key, and Ollama URL
            model_name = getattr(settings, "ai_model", None)
            api_key = getattr(settings, "ai_api_key", None)
            ollama_url = getattr(settings, "ollama_url", None)

            # Strip whitespace from settings
            if model_name:
                model_name = model_name.strip()
            if api_key:
                api_key = api_key.strip()
            if ollama_url:
                ollama_url = ollama_url.strip()

            # Generate the survey JSON using LLM with configured settings
            survey_json_str = generate_survey_json(
                prompt,
                model_name=model_name or None,
                api_key=api_key or None,
                ollama_url=ollama_url or None,
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
            if FORM_VERSIONS_KEY not in annos:
                annos[FORM_VERSIONS_KEY] = OOBTree()

            data = dict(
                id=str(uuid.uuid4()),
                created=datetime.now(timezone.utc),
                user=plone.api.user.get_current().getId(),
                form_json=json_form,
                locked=False,
            )

            annos[FORM_VERSIONS_KEY][data["id"]] = data

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

            # Get AI settings from registry
            from plone.registry.interfaces import IRegistry
            from zope.component import getUtility
            from ..interfaces import IFormsSettings

            registry = getUtility(IRegistry)
            settings = registry.forInterface(IFormsSettings, check=False)

            # Get configured model, API key, and Ollama URL
            model_name = getattr(settings, "ai_model", None)
            api_key = getattr(settings, "ai_api_key", None)
            ollama_url = getattr(settings, "ollama_url", None)

            # Strip whitespace from settings
            if model_name:
                model_name = model_name.strip()
            if api_key:
                api_key = api_key.strip()
            if ollama_url:
                ollama_url = ollama_url.strip()

            # Generate the refined survey JSON using LLM with configured settings
            refined_json_str = refine_survey_json(
                current_json,
                refinement_prompt,
                model_name=model_name or None,
                api_key=api_key or None,
                ollama_url=ollama_url or None,
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
                logger.info(f"Executing ImageMagick convert command: {' '.join(command)}")
                result = subprocess.run(command, check=True, capture_output=True)
                logger.info(f"Convert command completed successfully. Output: {result.stdout.decode('utf-8', errors='ignore')}")

                image_path = png_path
                if not image_path.exists():
                    candidates = sorted(temp_path.glob("uploaded*.png"))
                    if not candidates:
                        raise ValueError("PNG conversion failed: no output created")
                    image_path = candidates[0]

                from plone.registry.interfaces import IRegistry
                from zope.component import getUtility
                from ..interfaces import IFormsSettings

                registry = getUtility(IRegistry)
                settings = registry.forInterface(IFormsSettings, check=False)

                model_name = getattr(settings, "ai_model", None)
                api_key = getattr(settings, "ai_api_key", None)
                ollama_url = getattr(settings, "ollama_url", None)

                if model_name:
                    model_name = model_name.strip()
                if api_key:
                    api_key = api_key.strip()
                if ollama_url:
                    ollama_url = ollama_url.strip()

                prompt = (
                    "Convert this PDF to SurveyJS JSON. Keep the layout, "
                    "keep headers and footer, make JSON as close possible as possible, "
                    "return the form JSON only"
                )

                survey_json_str = generate_survey_json_from_image(
                    str(image_path),
                    prompt,
                    model_name=model_name or None,
                    api_key=api_key or None,
                    ollama_url=ollama_url or None,
                )

            cleaned_json_str = strip_markdown_json(survey_json_str)
            survey_data = orjson.loads(cleaned_json_str)
            if not isinstance(survey_data, dict):
                raise ValueError("Form JSON must be an object")

            annos = IAnnotations(self.context)
            if FORM_VERSIONS_KEY not in annos:
                annos[FORM_VERSIONS_KEY] = OOBTree()

            data = dict(
                id=str(uuid.uuid4()),
                created=datetime.now(timezone.utc),
                user=plone.api.user.get_current().getId(),
                form_json=survey_data,
            )

            annos[FORM_VERSIONS_KEY][data["id"]] = data

            result = {
                "success": True,
                "json": survey_data,
                "version_id": data["id"],
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


class EmbedViewer(Views):
    """View for embedding surveys in iframes"""

    index = ViewPageTemplateFile("viewer_embed.pt")

    def __call__(self):
        """Set appropriate headers for iframe embedding"""
        # Check if embedding is allowed
        if self.embedding_allowed:
            # Remove X-Frame-Options to allow iframe embedding
            # Note: Setting to empty string removes the header
            self.request.response.setHeader("X-Frame-Options", "")

            # Use Content-Security-Policy frame-ancestors instead
            # This is more modern and flexible
            self.request.response.setHeader(
                "Content-Security-Policy", "frame-ancestors *"
            )

            # Set CORS headers to allow cross-origin requests
            self.request.response.setHeader("Access-Control-Allow-Origin", "*")
            self.request.response.setHeader(
                "Access-Control-Allow-Methods", "GET, POST, OPTIONS"
            )
            self.request.response.setHeader(
                "Access-Control-Allow-Headers", "Content-Type"
            )

        # Render the template
        return self.index()
