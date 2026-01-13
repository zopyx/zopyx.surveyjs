# -*- coding: utf-8 -*-
"""Event subscribers for zopyx.surveyjs."""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from string import Formatter
from tempfile import TemporaryDirectory
from typing import List

import orjson
from BTrees.OOBTree import OOBTree
from zope.annotation.interfaces import IAnnotations
from zope.component import getUtility
from zope.globalrequest import getRequest
import httpx
from plone.registry.interfaces import IRegistry

from .browser.views import FORM_VERSIONS_KEY, RESULTS_KEY, ensure_timezone_aware
from .content.survey import Counter
from .converters.cli import SurveyConverter
from .interfaces import IFormsSettings

logger = logging.getLogger(__name__)


def log_survey_submission(context, event):
    """Sample listener that logs form submissions to stdout."""
    context_info = getattr(context, "absolute_url", lambda: repr(context))()
    print(f"SurveyJSFormSubmitted: context={context_info} data={event.form_data}")


def _interpolate_text(text: str | None, mapping: dict) -> str | None:
    """Interpolate placeholders in strings; ignore missing keys."""
    if not text:
        return text
    formatter = Formatter()
    try:
        return formatter.vformat(text, (), mapping)
    except KeyError:
        return text


def _latest_form_json(annos) -> dict:
    form_versions = [d for d in annos.get(FORM_VERSIONS_KEY, {}).values()]
    form_versions = sorted(
        form_versions, key=lambda x: ensure_timezone_aware(x["created"])
    )
    return form_versions[-1]["form_json"] if form_versions else {}


def _serialize_result_entry(result_entry: dict) -> dict:
    serialized = dict(result_entry)
    created = serialized.get("created")
    if isinstance(created, datetime):
        serialized["created"] = ensure_timezone_aware(created).isoformat()
    return serialized


def _get_converter_format(format_key: str):
    from .browser.views import CONVERTER_FORMATS

    for key, label, ext, content_type in CONVERTER_FORMATS:
        if key == format_key:
            return dict(key=key, label=label, ext=ext, content_type=content_type)
    return None


def _write_export(
    format_key: str,
    poll_id: str,
    items,
    attachments,
    creator,
    created,
    output_dir: Path,
):
    output_path = None
    if format_key == "text":
        from .converters import write_text

        output_path = write_text(items, output_dir / f"{poll_id}.txt", creator, created)
    elif format_key == "md":
        from .converters import write_markdown

        output_path = write_markdown(
            items, poll_id, output_dir / f"{poll_id}.md", creator, created
        )
    elif format_key == "html":
        from .converters import build_markdown, write_html

        markdown_body = build_markdown(items, poll_id, creator, created)
        output_path = write_html(
            markdown_body, attachments, output_dir / f"{poll_id}.html"
        )
    elif format_key == "pdf":
        from .converters import build_markdown, write_pdf
        from .converters.html import build_html

        markdown_body = build_markdown(items, poll_id, creator, created)
        html_body = build_html(markdown_body, attachments)
        output_path = write_pdf(
            html_body, output_dir / f"{poll_id}.pdf", creator, created
        )
    elif format_key == "csv":
        from .converters import write_csv, build_table_rows

        rows = build_table_rows(items)
        output_path = write_csv(rows, output_dir / f"{poll_id}.csv")
    elif format_key == "xlsx":
        from .converters import write_xlsx, build_table_rows

        rows = build_table_rows(items)
        output_path = write_xlsx(rows, output_dir / f"{poll_id}.xlsx")
    elif format_key == "docx":
        from .converters import write_docx

        output_path = write_docx(
            items, output_dir / f"{poll_id}.docx", poll_id, creator, created
        )
    elif format_key == "xml":
        from .converters import write_xml

        output_path = write_xml(items, poll_id, output_dir / f"{poll_id}.xml")
    elif format_key == "json":
        from .converters import write_json

        output_path = write_json(
            items, poll_id, output_dir / f"{poll_id}.json", creator, created
        )
    return output_path


def send_submission_email(context, event):
    """Send submission email when the mail action is enabled."""
    actions = getattr(context, "actions", set()) or set()
    if "mail" not in actions:
        return

    email_to = getattr(context, "email_to", None)
    email_subject = getattr(context, "email_subject", None)
    email_body = getattr(context, "email_body", "") or ""
    email_sender = getattr(context, "email_sender", None)
    email_cc = getattr(context, "email_cc", None) or []
    email_bcc = getattr(context, "email_bcc", None) or []
    email_formats = getattr(context, "email_formats", None) or set()
    if not email_formats:
        email_formats = {"pdf"}
    if "md" in email_formats:
        email_formats = {fmt for fmt in email_formats if fmt != "md"}
        email_formats.add("pdf")

    if not email_to or not email_subject:
        logger.info(
            "Mail action enabled but email settings incomplete (To/Subject) for %s",
            getattr(context, "absolute_url", lambda: repr(context))(),
        )
        return

    poll_entry = event.form_data or {}
    poll_id = poll_entry.get("poll_id") or str(uuid.uuid1())
    entry_result = poll_entry.get("result") or {}
    creator = poll_entry.get("user")
    created = poll_entry.get("created")
    created_value = created
    if isinstance(created, datetime):
        created_value = ensure_timezone_aware(created).isoformat()

    annos = IAnnotations(context)
    if FORM_VERSIONS_KEY not in annos:
        annos[FORM_VERSIONS_KEY] = OOBTree()
    if RESULTS_KEY not in annos:
        annos[RESULTS_KEY] = OOBTree()

    form_json = _latest_form_json(annos)
    if not form_json:
        logger.info(
            "Mail action enabled but no form version available; skipping email for %s",
            getattr(context, "absolute_url", lambda: repr(context))(),
        )
        return

    try:
        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            data_path = tmpdir_path / "data.json"
            form_path = tmpdir_path / "form.json"
            output_dir = tmpdir_path / "output"

            data_payload = [
                _serialize_result_entry(dict(poll_entry, created=created_value))
            ]
            data_path.write_bytes(orjson.dumps(data_payload))
            form_path.write_bytes(orjson.dumps(form_json))

            converter = SurveyConverter(data_path, form_path, output_dir)
            items, attachments = converter.collect_items(entry_result, poll_id)

            output_paths: List[Path] = []
            format_labels: List[str] = []
            for fmt in email_formats:
                format_key = (fmt or "").lower()
                format_info = _get_converter_format(format_key)
                if not format_info:
                    logger.warning("Unknown mail export format '%s'; skipping", fmt)
                    continue
                output_path = _write_export(
                    format_key,
                    poll_id,
                    items,
                    attachments,
                    creator,
                    created_value,
                    output_dir,
                )
                if output_path is None:
                    logger.warning(
                        "Failed to render format '%s' for poll %s", fmt, poll_id
                    )
                    continue
                output_paths.append(output_path)
                format_labels.append(format_info["label"])

            if not output_paths:
                logger.info(
                    "Mail action enabled but no exports produced for poll %s; skipping email",
                    poll_id,
                )
                return

            saved_attachments = converter.save_attachments(attachments)
            formats_label = ", ".join(format_labels) if format_labels else ""

            subject = _interpolate_text(email_subject, {"poll_id": poll_id})
            body = _interpolate_text(
                email_body,
                {
                    "created": created_value or "",
                    "creator": creator or "",
                    "formats": formats_label,
                },
            )

            converter.send_email_mailhost(
                email_to,
                output_paths,
                poll_id,
                creator,
                created_value,
                saved_attachments,
                sender=email_sender,
                subject=subject,
                body=body or None,
                cc=email_cc,
                bcc=email_bcc,
            )
            logger.info("Submission mail sent for poll %s to %s", poll_id, email_to)
    except Exception:
        logger.exception("Failed to send submission mail for poll %s", poll_id)


def post_submission_payload(context, event):
    """POST submission to external endpoint when the post action is enabled."""
    actions = getattr(context, "actions", set()) or set()
    if "post" not in actions:
        return

    endpoint_url = getattr(context, "post_endpoint_url", None)
    if not endpoint_url:
        logger.info(
            "POST action enabled but no endpoint configured for %s",
            getattr(context, "absolute_url", lambda: repr(context))(),
        )
        return

    poll_entry = event.form_data or {}
    poll_id = poll_entry.get("poll_id") or str(uuid.uuid1())
    created = poll_entry.get("created")
    if isinstance(created, datetime):
        created = ensure_timezone_aware(created).isoformat()

    annos = IAnnotations(context)
    form_json = _latest_form_json(annos)
    if not form_json:
        logger.info(
            "POST action enabled but no form version available; skipping POST for %s",
            getattr(context, "absolute_url", lambda: repr(context))(),
        )
        return

    payload = {
        "poll": dict(poll_entry, poll_id=poll_id, created=created),
        "form": form_json,
        "survey_url": getattr(context, "absolute_url", lambda: "")(),
    }

    try:
        response = httpx.post(endpoint_url, json=payload, timeout=10.0)
        response.raise_for_status()
        logger.info(
            "Submission POSTed for poll %s to %s with status %s",
            poll_id,
            endpoint_url,
            response.status_code,
        )
    except Exception:
        logger.exception(
            "Failed to POST submission for poll %s to %s", poll_id, endpoint_url
        )


def store_submission_result(context, event):
    """Store submission data when the store action is enabled."""
    actions = getattr(context, "actions", set()) or set()
    if "store" not in actions:
        return

    annos = IAnnotations(context)
    annos.setdefault(FORM_VERSIONS_KEY, OOBTree())
    annos.setdefault(RESULTS_KEY, OOBTree())

    form_data = event.form_data or {}
    registry = getUtility(IRegistry)
    settings = registry.forInterface(IFormsSettings, check=False)
    request = getRequest()
    if request is not None:
        if getattr(settings, "log_ip_addresses", False):
            client_ip = getattr(request, "getClientAddr", None)
            if callable(client_ip):
                client_ip = client_ip()
            else:
                client_ip = request.get("REMOTE_ADDR")
            if client_ip:
                form_data = dict(form_data, ip_address=client_ip)
        if getattr(settings, "log_user_agent", False):
            user_agent = getattr(request, "getHeader", None)
            if callable(user_agent):
                user_agent = user_agent("User-Agent")
            else:
                user_agent = request.get("HTTP_USER_AGENT")
            if user_agent:
                form_data = dict(form_data, user_agent=user_agent)
    poll_id = form_data.get("poll_id") or str(uuid.uuid1())
    form_version = form_data.get("form_version")
    seq_counter = getattr(context, "seq_no", None)
    if seq_counter is None:
        seq_counter = Counter()
        context.seq_no = seq_counter
    seq_no = seq_counter.increment()

    if not form_version:
        form_versions = [d for d in annos[FORM_VERSIONS_KEY].values()]
        form_versions = sorted(
            form_versions, key=lambda x: ensure_timezone_aware(x["created"])
        )
        form_version = form_versions[-1]["id"] if form_versions else None

    annos[RESULTS_KEY][poll_id] = dict(
        form_data, poll_id=poll_id, form_version=form_version, seq_no=seq_no
    )
    logger.info("Stored survey submission for poll %s", poll_id)
