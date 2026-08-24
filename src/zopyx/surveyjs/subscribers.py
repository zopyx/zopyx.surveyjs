# -*- coding: utf-8 -*-
"""Event subscribers for zopyx.surveyjs.

This module contains two categories of subscribers:

1. Submission pipeline subscribers (``ISurveyJSFormSubmittedEvent``)
   These run after a survey submission has passed validation and was accepted.
   Each subscriber performs one side effect (store result, send emails, POST to an
   endpoint, etc.). The functions are intentionally independent so deployments can
   reason about each side effect in isolation and failures are easier to diagnose.

2. Content modification audit subscribers (``IObjectModifiedEvent``)
   These track editor changes to Survey content metadata. The project uses
   ``zopyx.plone.persistentlogger`` to persist audit entries on the object, which
   complements normal application logging (``logging``) that is often ephemeral.

Operational notes:

- Submission subscribers should never mutate unrelated content state.
- Side effects should fail safely: exceptions are logged and should not break the
  request path that already accepted the submission.
- Audit payloads should be compact and privacy-aware. Do not persist full survey
  answers or full content object dumps in the persistent logger.
"""

import logging
import os
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
from email.message import EmailMessage

import zope.component
import plone.api
from plone.behavior.interfaces import IBehaviorAssignable
from plone.dexterity.interfaces import IDexterityFTI, IDexterityContent

from .constants import FORM_VERSIONS_KEY
from .storage import _get_storage_location, get_result_storage
from .utils import ensure_timezone_aware, resolve_mail_settings
from .audit import audit_metadata_update, audit_controlpanel_change
from .content.survey import Counter
from .converters.cli import SurveyConverter
from .interfaces import IFormsSettings

logger = logging.getLogger(__name__)


def _get_all_fields(context):
    """Return all schema and behavior fields for a Dexterity object.

    ``IObjectModifiedEvent`` descriptions do not always carry enough information to
    map changed attribute names back to their schema definitions. This helper builds
    a complete field map so we can intersect event field names with real fields and
    safely read the current values for a compact audit payload.
    """
    schema = zope.component.getUtility(
        IDexterityFTI, name=context.portal_type
    ).lookupSchema()
    fields = dict((fieldname, schema[fieldname]) for fieldname in schema)

    assignable = IBehaviorAssignable(context)
    for behavior in assignable.enumerateBehaviors():
        behavior_schema = behavior.interface
        fields.update((name, behavior_schema[name]) for name in behavior_schema)

    return fields


def log_survey_submission(context, event):
    """Debug-only sample listener that prints accepted submissions to stdout.

    This is useful during local development but should not be treated as the audit
    trail; persistent audit logging for editor actions uses ``IPersistentLogger``.
    """
    context_info = getattr(context, "absolute_url", lambda: repr(context))()
    logger.info("Survey submission received: context=%s", context_info)


def _normalize_field_name(name: str | None) -> str | None:
    if not name:
        return None
    value = str(name).strip()
    if not value:
        return None
    if "." in value:
        return value.split(".")[-1]
    return value


def _extract_changed_fields(event) -> set[str]:
    """Extract normalized field names from lifecycle event descriptions.

    Plone/Zope lifecycle events may expose changes via ``attributes``, ``name`` or
    ``attribute`` depending on the event description type. This helper merges those
    forms into a single normalized field-name set.
    """
    changed: set[str] = set()
    for description in getattr(event, "descriptions", []) or []:
        attributes = getattr(description, "attributes", None)
        if attributes:
            for attr in attributes:
                normalized = _normalize_field_name(attr)
                if normalized:
                    changed.add(normalized)
        name = getattr(description, "name", None) or getattr(
            description, "attribute", None
        )
        normalized = _normalize_field_name(name)
        if normalized:
            changed.add(normalized)
    return changed


def log_metadata_changes(context, event):
    """Persist a compact audit record for Dexterity metadata/content edits.

    Trigger:
        ``IObjectModifiedEvent`` for any ``IDexterityContent`` (registered in
        ``configure.zcml``).

    Behavior:
        - Determine which fields changed from event descriptions.
        - Intersect with actual schema/behavior fields on the object.
        - Read current values only for the changed fields.
        - Write a compact, redacted persistent log entry.

    We intentionally avoid persisting the full object state because Survey objects
    can contain large/sensitive text fields (email bodies, endpoint URLs, etc.).
    """

    if not IDexterityContent.providedBy(context):
        return

    changed_fields = _extract_changed_fields(event)
    if not changed_fields:
        return

    fields = _get_all_fields(context)
    matched = sorted(changed_fields & set(fields.keys()))
    if not matched:
        return

    values: dict[str, object] = {}
    for name in matched:
        value = getattr(context, name, None)
        if callable(value):
            try:
                value = value()
            except Exception:
                value = None
        values[name] = value

    audit_metadata_update(context, matched, values)


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
    """Return the most recent stored form JSON from annotations."""
    form_versions = [d for d in annos.get(FORM_VERSIONS_KEY, {}).values()]
    form_versions = sorted(
        form_versions, key=lambda x: ensure_timezone_aware(x["created"])
    )
    return form_versions[-1]["form_json"] if form_versions else {}


def _serialize_result_entry(result_entry: dict) -> dict:
    """Convert result entry fields (mainly datetimes) to JSON-safe values."""
    serialized = dict(result_entry)
    created = serialized.get("created")
    if isinstance(created, datetime):
        serialized["created"] = ensure_timezone_aware(created).isoformat()
    return serialized


def _get_converter_format(format_key: str):
    """Resolve converter metadata from ``CONVERTER_FORMATS`` by key."""
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
    """Render one export format and return the output path if successful."""
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
    """Send exported submission artifacts by email when the ``mail`` action is set.

    Expected event payload:
        ``event.form_data`` contains ``poll_id``, ``result``, ``user`` and
        ``created`` (as assembled by the submit endpoint).

    Side effects:
        - Reads latest form JSON version from annotations.
        - Renders one or more export formats via ``SurveyConverter``.
        - Sends email through MailHost.

    Failures are logged and swallowed so a mail problem does not break accepted
    submissions.
    """
    actions = getattr(context, "actions", set()) or set()
    if "mail" not in actions:
        return

    mail_settings = resolve_mail_settings(
        context,
        [
            "email_to",
            "email_subject",
            "email_body",
            "email_sender",
            "email_cc",
            "email_bcc",
            "email_formats",
        ],
    )
    email_to = mail_settings.get("email_to")
    email_subject = mail_settings.get("email_subject")
    email_body = mail_settings.get("email_body", "") or ""
    email_sender = mail_settings.get("email_sender")
    email_cc = mail_settings.get("email_cc") or []
    email_bcc = mail_settings.get("email_bcc") or []
    email_formats = mail_settings.get("email_formats") or set()
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


def send_submission_notification(context, event):
    """Send a lightweight notification email when ``mail-notification`` is enabled.

    Unlike ``send_submission_email`` this subscriber does not generate attachments;
    it sends a link to the submission detail page.
    """
    actions = getattr(context, "actions", set()) or set()
    if "mail-notification" not in actions:
        return

    mail_settings = resolve_mail_settings(
        context,
        [
            "email_to",
            "email_sender",
            "email_cc",
            "email_bcc",
            "email_notification_subject",
            "email_notification_body",
        ],
    )
    email_to = mail_settings.get("email_to")
    if not email_to:
        logger.info(
            "Mail notification enabled but no recipient configured for %s",
            getattr(context, "absolute_url", lambda: repr(context))(),
        )
        return

    poll_entry = event.form_data or {}
    poll_id = poll_entry.get("poll_id") or str(uuid.uuid1())
    survey_title = getattr(context, "Title", lambda: getattr(context, "title", ""))()
    detail_url = (
        f"{getattr(context, 'absolute_url', lambda: '')()}"
        f"/@@result-detail?poll_id={poll_id}"
    )

    subject_template = mail_settings.get("email_notification_subject") or (
        "Form submitted ({title})"
    )
    body_template = mail_settings.get("email_notification_body") or (
        "Hello,\n\n"
        'A new form submission was received for "{title}".\n'
        "You can review the submitted data here:\n"
        "{detail_url}\n\n"
        "Regards,\n"
        "Privacy Forms Studio\n"
    )
    mapping = {"title": survey_title, "detail_url": detail_url, "poll_id": poll_id}
    subject = _interpolate_text(subject_template, mapping) or subject_template
    body = _interpolate_text(body_template, mapping) or body_template

    try:
        from plone import api as plone_api

        portal = plone_api.portal.get()
        email_sender = mail_settings.get("email_sender")
        sender = (
            email_sender
            or portal.getProperty("email_from_address", None)
            or f"surveyjs@{os.uname().nodename}"
        )
        recipients = SurveyConverter._normalize_recipients(email_to)
        cc_recipients = SurveyConverter._normalize_recipients(
            mail_settings.get("email_cc") or []
        )
        bcc_recipients = SurveyConverter._normalize_recipients(
            mail_settings.get("email_bcc") or []
        )
        all_recipients = recipients + cc_recipients + bcc_recipients
        if not all_recipients:
            logger.info(
                "Mail notification enabled but no valid recipients for %s",
                getattr(context, "absolute_url", lambda: repr(context))(),
            )
            return

        message = EmailMessage()
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        if cc_recipients:
            message["Cc"] = ", ".join(cc_recipients)
        message["Subject"] = subject
        message.set_content(body)

        mailhost = plone_api.portal.get_tool("MailHost")
        mailhost.send(
            message.as_string(),
            mto=all_recipients,
            mfrom=sender,
            subject=subject,
            charset="utf-8",
        )
        logger.info("Notification mail sent for poll %s to %s", poll_id, all_recipients)
    except Exception:
        logger.exception("Failed to send notification mail for poll %s", poll_id)


def post_submission_payload(context, event):
    """POST the accepted submission plus latest form schema to an external endpoint.

    This is useful for integrating with downstream systems while preserving enough
    context (survey URL + form schema + poll payload) for external processing.
    """
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
    """Persist accepted submission data when the ``store`` action is enabled.

    Optional request metadata (IP/user-agent) is included only when enabled via
    registry settings. Sequence numbers are generated per survey object.
    """
    actions = getattr(context, "actions", set()) or set()
    if "store" not in actions:
        return

    annos = IAnnotations(context)
    annos.setdefault(FORM_VERSIONS_KEY, OOBTree())

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

    storage = get_result_storage(context)
    storage.store_result(
        context,
        dict(form_data, poll_id=poll_id, form_version=form_version, seq_no=seq_no),
    )
    logger.info(
        "Stored survey submission for poll %s in %s", poll_id, _get_storage_location()
    )


# Controlpanel audit logging


# Prefix for our settings in the registry
FORMS_SETTINGS_PREFIX = "zopyx.surveyjs.interfaces.IFormsSettings."


def log_controlpanel_change(event):
    """Log changes to Forms controlpanel settings via persistent logger.

    This subscriber listens for IRecordModifiedEvent and logs changes
    to settings defined in IFormsSettings.
    """
    record = event.record

    # Only log changes to our settings
    if not record.interfaceName or not record.interfaceName.endswith("IFormsSettings"):
        return

    field_name = record.fieldName
    if not field_name:
        return

    try:
        portal = plone.api.portal.get()
        # Get the old value if available
        old_value = getattr(event, "oldValue", None)
        new_value = record.value

        # Skip if value hasn't actually changed
        if old_value == new_value:
            return

        field_values = {field_name: new_value}
        if old_value is not None:
            field_values["_previous_value"] = old_value

        audit_controlpanel_change(
            portal,
            [field_name],
            field_values,
        )
    except Exception:
        logger.exception("Failed to log controlpanel change for %s", field_name)
