"""Security validation and normalization for new survey submissions."""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, cast


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
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
        "text/csv",
        "text/plain",
    }
)
_SAFE_DATA_IMAGE_MIMES = frozenset({"image/jpeg", "image/png"})
_FILE_KEYS = frozenset({"name", "type", "content"})
_CONTAINER_TYPES = frozenset({"html", "page", "panel", "survey"})
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_UNSAFE_MARKUP = re.compile(
    r"<\s*/?\s*(?:script|svg|iframe|object|embed)\b|\bon[a-z]+\s*=",
    re.IGNORECASE,
)
_DANGEROUS_URL = re.compile(r"^(?:javascript|vbscript):", re.IGNORECASE)
_DATA_URL = re.compile(
    r"^data:(?P<mime>[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*);base64,"
    r"(?P<encoded>[A-Za-z0-9+/]*={0,2})$",
    re.IGNORECASE,
)
_SAFE_FILENAME_CHARACTERS = frozenset("._ -()")

_IMAGE_SIGNATURES = {
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}
_FILE_SIGNATURES = {
    "application/msword": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "application/pdf": (b"%PDF-",),
    "application/rtf": (b"{\\rtf",),
    "application/vnd.ms-excel": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (b"PK\x03\x04",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (b"PK\x03\x04",),
    "application/zip": (b"PK\x03\x04",),
}


@dataclass
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
    enforce_required_fields: bool = False,
) -> dict[str, Any]:
    """Validate and normalize a submission or raise an explicit error.

    Check order is deterministic: payload/schema, field names/comments,
    required values, generic values, then file shape/name/MIME/data URL/MIME
    match/base64/size/content signature. The returned value is a deep copy.
    """
    if not isinstance(form_schema, dict):
        raise SubmissionValidationError("invalid_form_schema")
    if not isinstance(poll_result, dict):
        raise SubmissionValidationError("payload_not_object")
    if max_file_bytes < 1 or max_files < 1:
        raise ValueError("file limits must be positive")

    field_types, required_fields, comment_limits = _collect_field_types(form_schema)
    comment_prefix = form_schema.get("commentPrefix", "-Comment")
    if not isinstance(comment_prefix, str) or not comment_prefix:
        raise SubmissionValidationError("invalid_comment_prefix")

    unknown_fields = [
        field
        for field in poll_result
        if field not in field_types and not field.endswith(comment_prefix)
    ]
    for field in poll_result:
        if field.endswith(comment_prefix):
            base_field = field[: -len(comment_prefix)]
            if base_field in field_types:
                field_types[field] = "__comment__"
            else:
                unknown_fields.append(field)
    if unknown_fields:
        raise SubmissionValidationError("unknown_field", unknown_fields[0])

    if enforce_required_fields:
        for required_field in required_fields:
            if required_field not in poll_result or _is_empty_required_value(
                poll_result[required_field]
            ):
                raise SubmissionValidationError("missing_required", required_field)

    file_count = 0
    normalized: dict[str, Any] = {}
    for field_name, value in poll_result.items():
        field_type = field_types[field_name]
        if field_type == "file":
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
            if field_type == "__comment__":
                base_field = field_name[: -len(comment_prefix)]
                max_comment_length = comment_limits.get(base_field)
                if max_comment_length is None:
                    max_comment_length = form_schema.get("maxCommentLength")
                if max_comment_length is not None:
                    if type(max_comment_length) is not int or max_comment_length < 0:
                        raise SubmissionValidationError(
                            "invalid_comment_length", field_name
                        )
                    if not isinstance(value, str) or len(value) > max_comment_length:
                        raise SubmissionValidationError("comment_too_long", field_name)

    return normalized


def _collect_field_types(
    form_schema: dict[str, Any],
) -> tuple[dict[str, str], set[str], dict[str, Any]]:
    """Collect question names/types and required fields recursively."""
    fields: dict[str, str] = {}
    required: set[str] = set()
    comment_limits: dict[str, Any] = {}

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
            if node.get("isRequired") is True:
                required.add(name)
            if "maxCommentLength" in node:
                comment_limits[name] = node["maxCommentLength"]

        for key in ("pages", "elements", "questions", "templateElements"):
            visit(node.get(key))

    visit(form_schema)
    return fields, required, comment_limits


def _is_empty_required_value(value: Any) -> bool:
    return value is None or value == "" or value == []


def _validate_generic_value(value: Any, field: str) -> Any:
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

    normalized_prefix = "".join(
        char
        for char in value.lstrip()[:64]
        if not char.isspace() and ord(char) >= 0x20
    ).lower()
    if _DANGEROUS_URL.match(normalized_prefix):
        raise SubmissionValidationError("dangerous_url", field)

    if value.lstrip().lower().startswith("data:"):
        match = _DATA_URL.fullmatch(value.strip())
        if not match or match.group("mime").lower() not in _SAFE_DATA_IMAGE_MIMES:
            raise SubmissionValidationError("dangerous_url", field)
        try:
            base64.b64decode(match.group("encoded"), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise SubmissionValidationError("dangerous_url", field) from exc

    if _UNSAFE_MARKUP.search(value):
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
        if not isinstance(item, dict):
            raise SubmissionValidationError("invalid_file", field)

        name = item.get("name")
        declared_type = item.get("type")
        content = item.get("content")
        if not all(isinstance(item_value, str) for item_value in (name, declared_type, content)):
            raise SubmissionValidationError("invalid_file", field)
        name = cast(str, name)
        declared_type = cast(str, declared_type)
        content = cast(str, content)
        normalized_name = _normalize_filename(name)
        if normalized_name is None:
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

        if declared_type in _IMAGE_SIGNATURES:
            valid_content = _matches_image_signature(declared_type, decoded)
        elif declared_type in _FILE_SIGNATURES:
            valid_content = any(
                decoded.startswith(signature)
                for signature in _FILE_SIGNATURES[declared_type]
            )
        elif declared_type in {"text/csv", "text/plain"}:
            try:
                decoded.decode("utf-8")
                valid_content = b"\x00" not in decoded
            except UnicodeDecodeError:
                valid_content = False
        else:
            valid_content = True
        if not valid_content:
            raise SubmissionValidationError("invalid_file_content", field)

        canonical = base64.b64encode(decoded).decode("ascii")
        normalized.append(
            {
                "name": normalized_name,
                "type": declared_type.lower(),
                "content": f"data:{data_mime};base64,{canonical}",
            }
        )

    return normalized, len(normalized)


def _matches_image_signature(mime_type: str, content: bytes) -> bool:
    if mime_type == "image/webp":
        return (
            len(content) >= 12
            and content[:4] == b"RIFF"
            and content[8:12] == b"WEBP"
        )
    return any(content.startswith(signature) for signature in _IMAGE_SIGNATURES[mime_type])


def _normalize_filename(value: str) -> str | None:
    value = unicodedata.normalize("NFC", value)
    if not value or len(value) > 128 or len(value.encode("utf-8")) > 512:
        return None
    if not (value[0].isalnum() and unicodedata.category(value[0])[0] in {"L", "N"}):
        return None
    for char in value:
        if char in "/\\\"'<>" or ord(char) < 0x20 or char == "\x7f":
            return None
        if not (char.isalnum() or char in _SAFE_FILENAME_CHARACTERS):
            return None
    return value
