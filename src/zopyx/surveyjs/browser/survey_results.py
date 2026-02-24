from datetime import datetime
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import orjson
import plone.api
from zope.annotation.interfaces import IAnnotations

from .. import _
from ..storage import _get_storage_location, get_result_storage
from ..utils import ensure_timezone_aware, resolve_mail_settings
from .services import results as results_service
from .services.http import json_error, json_response, parse_json_body
from .views import Views

logger = logging.getLogger(__name__)


class SurveyResults(Views):
    @property
    def results(self):
        """Get all poll results sorted by creation date (newest first)."""
        storage = get_result_storage(self.context)
        return storage.list_results(self.context)

    def get_paginated_results(self):
        """Return paginated results."""
        return results_service.get_paginated_results(self.results, self.request)

    def _parse_tabulator_param(self, name):
        return results_service.parse_tabulator_param(self.request, name)

    def _results_row(self, entry):
        return results_service.results_row(entry)

    def _results_apply_filters(self, rows, filters):
        return results_service.results_apply_filters(rows, filters)

    def results_data(self):
        payload = results_service.build_results_payload(self.results, self.request)
        json_response(self.request.response, payload)

    def view_result_json(self):
        """Return JSON for a specific poll result for viewing."""
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
        from ..converters.cli import SurveyConverter
        from ..converters.html import build_html

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

        mail_settings = resolve_mail_settings(
            self.context,
            [
                "email_to",
                "email_subject",
                "email_body",
                "email_sender",
                "email_cc",
                "email_bcc",
            ],
        )
        email_to = mail_settings.get("email_to")
        email_subject = mail_settings.get("email_subject")
        email_body = mail_settings.get("email_body", "") or ""
        email_sender = mail_settings.get("email_sender")
        email_cc = mail_settings.get("email_cc") or []
        email_bcc = mail_settings.get("email_bcc") or []

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

        payload = parse_json_body(self.request)
        if isinstance(payload, dict):
            poll_ids = payload.get("poll_ids") or []

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
