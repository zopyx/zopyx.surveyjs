"""Security validation and normalization for new survey submissions.

This module runs before the submission event is emitted.  It deliberately
validates only data that can cross an output boundary: arbitrary text remains
text, while file objects and URL-like values are constrained to safe forms.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from typing import Any


DEFAULT_MAX_FILE_BYTES = 1024 * 1024
DEFAULT_MAX_FILES = 10

_ALLOWED_FILE_MIME_TYPES = frozenset(
    {
        "application/msword",
        "application/pdf",
        "application/rtf",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
        "text/csv",
        "text/plain",
    }
)

_FILE_KEYS = frozenset({"name", "type", "content"})
_CONTAINER_TYPES = frozenset({"html", "page", "panel", "survey"})
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SCRIPT_MARKUP = re.compile(r"<\s*/?\s*script\b", re.IGNORECASE)
_DANGEROUS_URL = re.compile(r"^(?:javascript|vbscript):", re.IGNORECASE)
_DATA_URL = re.compile(
    r"^data:(?P<mime>[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*);base64,"
    r"(?P<encoded>[A-Za-z0-9+/]*={0,2})$",
    re.IGNORECASE,
)
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,127}$")

_IMAGE_SIGNATURES = {
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


@dataclass(frozen=True)
class SubmissionValidationError(ValueError):
    """A client-correctable submission validation failure."""

    code: str
    field: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        message = self.code
        if self.field:
            message = f"{message}: {self.field}"
        if self.detail:
            message = f"{message} ({self.detail})"
        ValueError.__init__(self, message)


def validate_and_normalize_submission(
    form_schema: dict[str, Any],
    poll_result: Any,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_files: int = DEFAULT_MAX_FILES,
) -> dict[str, Any]:
    """Validate and normalize a new submission or raise an explicit error.

    The returned value is a deep copy.  File objects are reduced to the three
    supported keys and their data URLs are canonicalized.  No caller-owned
    object is mutated.
    """
    if not isinstance(form_schema, dict):
        raise SubmissionValidationError("invalid_form_schema")
    if not isinstance(poll_result, dict):
        raise SubmissionValidationError("payload_not_object")
    if max_file_bytes < 1 or max_files < 1:
        raise ValueError("file limits must be positive")

    field_types = _collect_field_types(form_schema)
    unknown_fields = [field for field in poll_result if field not in field_types]
    if unknown_fields:
        raise SubmissionValidationError("unknown_field", unknown_fields[0])

    file_count = 0
    normalized: dict[str, Any] = {}
    for field_name, value in poll_result.items():
        if field_types[field_name] == "file":
            normalized_value, used_files = _normalize_file_value(
                field_name,
                value,
                max_file_bytes=max_file_bytes,
                remaining_files=max_files - file_count,
            )
            file_count += used_files
            normalized[field_name] = normalized_value
        else:
            normalized[field_name] = _validate_generic_value(value, field_name)

    return normalized


def _collect_field_types(form_schema: dict[str, Any]) -> dict[str, str]:
    """Collect question names and types from nested SurveyJS schema nodes."""
    fields: dict[str, str] = {}

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict):
            return

        field_type = node.get("type")
        name = node.get("name")
        if isinstance(name, str) and name and field_type not in _CONTAINER_TYPES:
            fields[name] = str(field_type or "")

        for key in ("pages", "elements", "questions", "templateElements"):
            visit(node.get(key))

    visit(form_schema)
    return fields


def _validate_generic_value(value: Any, field: str) -> Any:
    """Validate scalar URL/markup hazards while preserving user text."""
    if isinstance(value, str):
        _validate_string(value, field)
        return value
    if isinstance(value, list):
        return [_validate_generic_value(item, field) for item in value]
    if isinstance(value, dict):
        return {
            key: _validate_generic_value(item, f"{field}.{key}")
            for key, item in value.items()
        }
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise SubmissionValidationError("invalid_value", field)


def _validate_string(value: str, field: str) -> None:
    if _CONTROL_CHARACTERS.search(value):
        raise SubmissionValidationError("control_character", field)
    if _DANGEROUS_URL.match(value):
        raise SubmissionValidationError("dangerous_url", field)
    if value.lower().startswith("data:text/html"):
        raise SubmissionValidationError("dangerous_url", field)
    if _SCRIPT_MARKUP.search(value):
        raise SubmissionValidationError("html_markup", field)


def _normalize_file_value(
    field: str,
    value: Any,
    *,
    max_file_bytes: int,
    remaining_files: int,
) -> tuple[list[dict[str, str]], int]:
    if not isinstance(value, list):
        raise SubmissionValidationError("invalid_file", field)
    if len(value) > remaining_files:
        raise SubmissionValidationError("too_many_files", field)

    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) - _FILE_KEYS:
            raise SubmissionValidationError("invalid_file", field)

        name = item.get("name")
        declared_type = item.get("type")
        content = item.get("content")
        if not all(isinstance(value, str) for value in (name, declared_type, content)):
            raise SubmissionValidationError("invalid_file", field)
        name = str(name)
        declared_type = str(declared_type)
        content = str(content)
        if not _SAFE_FILENAME.fullmatch(name):
            raise SubmissionValidationError("unsafe_filename", field)
        if declared_type not in _ALLOWED_FILE_MIME_TYPES:
            raise SubmissionValidationError("disallowed_mime_type", field)

        data_match = _DATA_URL.fullmatch(content)
        if not data_match:
            raise SubmissionValidationError("invalid_data_url", field)
        data_mime = data_match.group("mime").lower()
        encoded = data_match.group("encoded")
        if data_mime != declared_type.lower():
            raise SubmissionValidationError("mime_mismatch", field)

        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise SubmissionValidationError("invalid_base64", field) from exc
        if len(decoded) > max_file_bytes:
            raise SubmissionValidationError("file_too_large", field)
        if declared_type in _IMAGE_SIGNATURES and not _matches_image_signature(
            declared_type, decoded
        ):
            raise SubmissionValidationError("invalid_image_content", field)

        canonical = base64.b64encode(decoded).decode("ascii")
        normalized.append(
            {"name": name, "type": declared_type.lower(), "content": f"data:{data_mime};base64,{canonical}"}
        )

    return normalized, len(normalized)


def _matches_image_signature(mime_type: str, content: bytes) -> bool:
    if mime_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return any(content.startswith(signature) for signature in _IMAGE_SIGNATURES[mime_type])
