"""Persistent audit logging helpers with redaction and compact summaries."""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import logging
from typing import Any

import orjson
import plone.api
from zopyx.plone.persistentlogger.logger import IPersistentLogger
from zope.globalrequest import getRequest

logger = logging.getLogger(__name__)

_REDACTED_FIELDS = {
    "email_body",
    "email_notification_body",
    "email_subject",
    "email_notification_subject",
    "email_to",
    "email_cc",
    "email_bcc",
    "email_sender",
    "post_endpoint_url",
}
_REDACTED_NAME_PARTS = {"password", "secret", "token", "apikey", "api_key"}


def _context_url(context) -> str:
    return getattr(context, "absolute_url", lambda: "")() or ""


def _context_path(context) -> str:
    try:
        return "/".join(context.getPhysicalPath())
    except Exception:
        return ""


def _current_user_id() -> str | None:
    try:
        user = plone.api.user.get_current()
        return user.getId() if user else None
    except Exception:
        return None


def _request_info() -> dict[str, str | None]:
    request = getRequest()
    if request is None:
        return {"source_view": None, "request_method": None}
    source_view = request.get("PATH_INFO") or request.get("URL")
    method = request.get("REQUEST_METHOD")
    return {"source_view": source_view, "request_method": method}


def _truncate(text: str, limit: int = 200) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _is_redacted_field(name: str) -> bool:
    lowered = (name or "").lower()
    if lowered in _REDACTED_FIELDS:
        return True
    return any(part in lowered for part in _REDACTED_NAME_PARTS)


def summarize_value(name: str, value: Any) -> Any:
    """Return a JSON-safe compact representation for metadata values."""
    if _is_redacted_field(name):
        if isinstance(value, str):
            return {"redacted": True, "length": len(value)}
        if isinstance(value, (list, tuple, set)):
            return {"redacted": True, "count": len(value)}
        return {"redacted": True, "type": type(value).__name__}

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, bytes):
        return {"type": "bytes", "size": len(value)}

    if isinstance(value, str):
        return _truncate(value)

    if isinstance(value, (list, tuple, set)):
        items = list(value)
        sample = [summarize_value(name, item) for item in items[:10]]
        return {"type": type(value).__name__, "count": len(items), "sample": sample}

    if isinstance(value, dict):
        keys = [str(k) for k in list(value.keys())[:20]]
        return {"type": "dict", "count": len(value), "keys": sorted(keys)}

    return _truncate(repr(value))


def _base_details(context) -> dict[str, Any]:
    details = {
        "path": _context_path(context),
        "portal_type": getattr(context, "portal_type", None),
        "title": summarize_value("title", getattr(context, "title", None)),
        "user_id": _current_user_id(),
    }
    details.update(_request_info())
    return details


def persistent_audit_log(
    context,
    comment: str,
    *,
    action: str,
    details: dict[str, Any] | None = None,
    level: str = "info",
) -> bool:
    """Write a persistent audit log entry without breaking the caller.

    Return ``True`` when the entry was written and ``False`` when the audit
    backend was unavailable. Audit logging is deliberately fail-open, but the
    failure remains observable through the dedicated audit logger.
    """
    payload = _base_details(context)
    payload["action"] = action
    if details:
        payload.update(details)

    try:
        adapter = IPersistentLogger(context)
        adapter.log(
            comment,
            level=level,
            info_url=_context_url(context),
            details=payload,
        )
        return True
    except Exception:
        logger.exception(
            "Persistent audit logging failed: action=%s path=%s",
            action,
            payload.get("path"),
            extra={
                "audit_failure": True,
                "audit_action": action,
                "audit_path": payload.get("path"),
            },
        )
        return False


def audit_metadata_update(
    context, changed_fields: list[str], field_values: dict[str, Any]
) -> None:
    safe_values = {
        name: summarize_value(name, field_values.get(name)) for name in changed_fields
    }
    persistent_audit_log(
        context,
        "Metadata updated: " + ", ".join(changed_fields),
        action="metadata.update",
        details={"changed_fields": changed_fields, "values": safe_values},
    )


def _walk_elements(items) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return found
    for item in items:
        if not isinstance(item, dict):
            continue
        found.append(item)
        found.extend(_walk_elements(item.get("elements")))
        # Matrix/compound question structures can nest arrays as well.
        for key in ("templateElements",):
            found.extend(_walk_elements(item.get(key)))
    return found


def _leaf_element_names(form_json: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    pages = form_json.get("pages")
    for item in _walk_elements(pages if isinstance(pages, list) else []):
        name = item.get("name")
        if not name or not isinstance(name, str):
            continue
        if isinstance(item.get("elements"), list):
            continue
        names.add(name)
    return names


def summarize_form_json(form_json: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = orjson.dumps(form_json, option=orjson.OPT_SORT_KEYS)
    except Exception:
        payload = orjson.dumps({})

    pages = form_json.get("pages")
    page_count = len(pages) if isinstance(pages, list) else 0
    elements = _walk_elements(pages if isinstance(pages, list) else [])
    leaf_names = _leaf_element_names(form_json)

    return {
        "json_sha256": hashlib.sha256(payload).hexdigest()[:16],
        "json_size_bytes": len(payload),
        "page_count": page_count,
        "element_count": len(elements),
        "question_count": len(leaf_names),
        "question_names_sample": sorted(list(leaf_names))[:20],
    }


def audit_form_version_change(
    context,
    *,
    form_json: dict[str, Any],
    source: str,
    new_version_id: str,
    previous_version_id: str | None = None,
    previous_form_json: dict[str, Any] | None = None,
    locked: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    details = {
        "source": source,
        "new_version_id": new_version_id,
        "previous_version_id": previous_version_id or None,
    }
    if locked is not None:
        details["locked"] = bool(locked)
    details.update(summarize_form_json(form_json))

    if isinstance(previous_form_json, dict):
        before = _leaf_element_names(previous_form_json)
        after = _leaf_element_names(form_json)
        details["question_names_added"] = sorted(list(after - before))[:20]
        details["question_names_removed"] = sorted(list(before - after))[:20]
        details["question_delta"] = len(after) - len(before)
    if extra:
        details.update(extra)

    persistent_audit_log(
        context,
        f"Form version saved ({source})",
        action="form.version.create",
        details=details,
    )


def audit_form_version_state_change(
    context,
    *,
    action: str,
    comment: str,
    version_id: str,
    source: str,
    extra: dict[str, Any] | None = None,
) -> None:
    details = {"version_id": version_id, "source": source}
    if extra:
        details.update(extra)
    persistent_audit_log(context, comment, action=action, details=details)


def audit_controlpanel_change(
    context,
    changed_fields: list[str],
    field_values: dict[str, Any],
) -> None:
    """Log controlpanel settings changes via persistent logger.

    Args:
        context: The context object (usually the site root or controlpanel)
        changed_fields: List of field names that were modified
        field_values: Dictionary of field names to their new values
    """
    safe_values = {
        name: summarize_value(name, field_values.get(name)) for name in changed_fields
    }
    persistent_audit_log(
        context,
        "Controlpanel settings updated: " + ", ".join(changed_fields),
        action="controlpanel.update",
        details={"changed_fields": changed_fields, "values": safe_values},
    )
