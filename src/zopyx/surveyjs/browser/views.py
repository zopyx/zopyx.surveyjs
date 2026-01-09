from BTrees.OOBTree import OOBTree
from datetime import datetime, timezone
from string import Formatter
from pathlib import Path
from tempfile import TemporaryDirectory
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.annotation.interfaces import IAnnotations
import plone.api

from .. import _

import orjson
import uuid


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


class Views(BrowserView):
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
        )

        annos[FORM_VERSIONS_KEY][data["id"]] = data

        result = dict(isSuccess=True)
        self.request.response.setStatus(200)
        self.request.response.setHeader("content-type", "application/json")
        self.request.response.write(orjson.dumps(result))

    def save_poll(self):
        poll_result = orjson.loads(self.request.form["pollResult"])

        actions = getattr(self.context, "actions", set()) or set()
        if "store" not in actions:
            result = dict(
                isSuccess=True,
                stored=False,
                message="Storage action disabled; result not persisted.",
            )
            self.request.response.setStatus(200)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(result))
            return

        annos = IAnnotations(self.context)
        if FORM_VERSIONS_KEY not in annos:
            annos[FORM_VERSIONS_KEY] = OOBTree()
        if RESULTS_KEY not in annos:
            annos[RESULTS_KEY] = OOBTree()

        form_versions = [d for d in annos[FORM_VERSIONS_KEY].values()]
        form_versions = sorted(
            form_versions, key=lambda x: ensure_timezone_aware(x["created"])
        )
        form_version_id = form_versions[-1]["id"] if form_versions else None

        data = dict(
            poll_id=str(uuid.uuid1()),
            created=datetime.now(timezone.utc),
            user=plone.api.user.get_current().getId(),
            form_version=form_version_id,
            result=poll_result,
        )

        annos[RESULTS_KEY][data["poll_id"]] = data

        result = dict(isSuccess=True)
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
            dict(key=key, label=label)
            for key, label, _ext, _content_type in CONVERTER_FORMATS
        ]

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
        )

        annos[FORM_VERSIONS_KEY][new_version["id"]] = new_version

        plone.api.portal.show_message(
            _("Version restored successfully. A new version has been created."),
            type="info",
        )
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
                result_uuid = ""
                result_payload = result.get("result") or {}
                if isinstance(result_payload, dict):
                    result_uuid = (result_payload.get("uuid") or "").lower()
                return q in user or q in poll_id or q in result_uuid

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
    def storing_enabled(self):
        """Return True if the survey actions include store."""
        actions = getattr(self.context, "actions", set()) or set()
        return "store" in actions

    @property
    def plone_api(self):
        return plone.api

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

            # Get configured model and API key
            model_name = getattr(settings, "ai_model", None)
            api_key = getattr(settings, "ai_api_key", None)

            # Strip whitespace from settings
            if model_name:
                model_name = model_name.strip()
            if api_key:
                api_key = api_key.strip()

            # Generate the survey JSON using LLM with configured settings
            survey_json_str = generate_survey_json(
                prompt, model_name=model_name or None, api_key=api_key or None
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
        use_existing = (
            self.request.form.get("use_existing", "").strip().lower()
            in {"1", "true", "yes", "on"}
        )
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

            # Get configured model and API key
            model_name = getattr(settings, "ai_model", None)
            api_key = getattr(settings, "ai_api_key", None)

            # Strip whitespace from settings
            if model_name:
                model_name = model_name.strip()
            if api_key:
                api_key = api_key.strip()

            # Generate the refined survey JSON using LLM with configured settings
            refined_json_str = refine_survey_json(
                current_json,
                refinement_prompt,
                model_name=model_name or None,
                api_key=api_key or None,
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
