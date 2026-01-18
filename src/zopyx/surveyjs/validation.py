# -*- coding: utf-8 -*-
"""Strict server-side validation for SurveyJS submissions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import base64
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


MAX_REQUEST_BYTES = 2_000_000
MAX_JSON_BYTES = 1_000_000
MAX_TEXT_LENGTH = 2_000
MAX_FIELDS = 500
MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_BYTES = 2_000_000
MAX_TOTAL_ATTACHMENT_BYTES = 5_000_000
MAX_CHOICES = 50
ALLOWED_MIME_TYPES: Optional[Set[str]] = None

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    status: int
    reason: str
    field: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


def _choices_to_set(choices: Any) -> Optional[Set[str]]:
    if not choices:
        return None
    values: Set[str] = set()
    for item in choices:
        if isinstance(item, dict):
            value = item.get("value")
            if value is None:
                continue
            values.add(str(value))
        else:
            values.add(str(item))
    return values or None


def _parse_elements(
    elements: Iterable[Dict[str, Any]], fields: Dict[str, Dict[str, Any]]
) -> None:
    for element in elements or []:
        element_type = element.get("type")
        name = element.get("name")

        if element_type in ("panel", "paneldynamic"):
            template = element.get("elements") or element.get("templateElements") or []
            if element_type == "paneldynamic" and name:
                template_fields: Dict[str, Dict[str, Any]] = {}
                _parse_elements(template, template_fields)
                fields[name] = {
                    "type": "paneldynamic",
                    "required": bool(element.get("isRequired")),
                    "template": template_fields,
                    "maxItems": element.get("maxPanelCount"),
                }
            else:
                _parse_elements(template, fields)
            continue

        if not name:
            continue

        field: Dict[str, Any] = {
            "type": element_type,
            "required": bool(element.get("isRequired")),
            "requiredIf": element.get("requiredIf"),
            "visibleIf": element.get("visibleIf"),
            "inputType": element.get("inputType"),
            "maxLength": element.get("maxLength"),
            "minLength": element.get("minLength"),
            "min": element.get("min"),
            "max": element.get("max"),
            "minValue": element.get("minValue"),
            "maxValue": element.get("maxValue"),
            "rateMin": element.get("rateMin"),
            "rateMax": element.get("rateMax"),
            "choices": _choices_to_set(element.get("choices")),
            "rateValues": _choices_to_set(element.get("rateValues")),
            "maxSelectedChoices": element.get("maxSelectedChoices"),
            "minSelectedChoices": element.get("minSelectedChoices"),
            "validators": element.get("validators") or [],
        }

        if element_type in ("matrix", "matrixdropdown", "matrixdynamic"):
            field["rows"] = _choices_to_set(element.get("rows"))
            field["columns"] = _choices_to_set(element.get("columns"))
            field["columns_meta"] = element.get("columns") or []

        if element_type == "file":
            field["maxSize"] = element.get("maxSize")
            field["acceptedTypes"] = element.get("acceptedTypes")
            field["allowMultiple"] = bool(element.get("allowMultiple"))

        fields[name] = field


def build_schema_index(form_json: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    fields: Dict[str, Dict[str, Any]] = {}
    pages = form_json.get("pages") or []
    for page in pages:
        _parse_elements(page.get("elements") or [], fields)
    return fields


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, (list, tuple, dict)) and len(value) == 0:
        return True
    return False


def _parse_iso_date(value: str) -> bool:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _validate_text(value: Any, field: Dict[str, Any]) -> Optional[str]:
    if not isinstance(value, str):
        return "type_mismatch"
    min_len = field.get("minLength")
    if min_len is not None and len(value) < min_len:
        return "text_too_short"
    limit = field.get("maxLength") or MAX_TEXT_LENGTH
    if len(value) > limit:
        return "text_too_long"
    if any(ord(ch) < 9 for ch in value):
        return "invalid_control_chars"
    return None


def _validate_number(value: Any, field: Dict[str, Any]) -> Optional[str]:
    if isinstance(value, bool):
        return "type_mismatch"
    if isinstance(value, str):
        try:
            value = float(value) if "." in value else int(value)
        except ValueError:
            return "type_mismatch"
    if not isinstance(value, (int, float)):
        return "type_mismatch"
    min_value = (
        field.get("minValue") if field.get("minValue") is not None else field.get("min")
    )
    max_value = (
        field.get("maxValue") if field.get("maxValue") is not None else field.get("max")
    )
    if min_value is not None and value < min_value:
        return "out_of_range"
    if max_value is not None and value > max_value:
        return "out_of_range"
    return None


def _validate_rating(value: Any, field: Dict[str, Any]) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return "type_mismatch"
    if isinstance(value, str):
        if not value.isdigit():
            return "type_mismatch"
        value = int(value)
    min_value = field.get("rateMin")
    max_value = field.get("rateMax")
    if min_value is not None and value < min_value:
        return "out_of_range"
    if max_value is not None and value > max_value:
        return "out_of_range"
    choices = field.get("rateValues")
    if choices and str(value) not in choices:
        return "invalid_choice"
    return None


def _validate_choice(value: Any, field: Dict[str, Any]) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return "type_mismatch"
    choices = field.get("choices")
    if choices and str(value) not in choices:
        return "invalid_choice"
    return None


def _validate_checkbox(value: Any, field: Dict[str, Any]) -> Optional[str]:
    if not isinstance(value, list):
        return "type_mismatch"
    if len(value) > MAX_CHOICES:
        return "too_many_choices"
    min_sel = field.get("minSelectedChoices")
    if min_sel is not None and len(value) < min_sel:
        return "too_few_choices"
    max_sel = field.get("maxSelectedChoices")
    if max_sel is not None and len(value) > max_sel:
        return "too_many_choices"
    choices = field.get("choices")
    for item in value:
        if choices and str(item) not in choices:
            return "invalid_choice"
    return None


def _validate_boolean(value: Any) -> Optional[str]:
    if not isinstance(value, bool):
        return "type_mismatch"
    return None


def _validate_date(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return "type_mismatch"
    if not _parse_iso_date(value):
        return "invalid_date"
    return None


def _decode_base64(content: str) -> Optional[bytes]:
    if content.startswith("data:"):
        parts = content.split(",", 1)
        if len(parts) != 2:
            return None
        content = parts[1]
    try:
        return base64.b64decode(content, validate=True)
    except Exception:
        return None


def _validate_files(value: Any, field: Dict[str, Any]) -> Optional[str]:
    if not isinstance(value, list):
        return "type_mismatch"
    if len(value) > MAX_ATTACHMENTS:
        return "too_many_attachments"

    total_bytes = 0
    for entry in value:
        if not isinstance(entry, dict):
            return "invalid_attachment"
        name = entry.get("name")
        size = entry.get("size")
        mime = entry.get("type")
        content = entry.get("content")

        if not isinstance(name, str) or name.strip() == "":
            return "invalid_attachment"
        if size is not None and not isinstance(size, int):
            return "invalid_attachment"
        if mime is not None:
            if not isinstance(mime, str) or "/" not in mime or len(mime) > 255:
                return "invalid_attachment"
            if ALLOWED_MIME_TYPES and mime not in ALLOWED_MIME_TYPES:
                return "unsupported_mime"

        decoded = None
        if content:
            if not isinstance(content, str):
                return "invalid_attachment"
            decoded = _decode_base64(content)
            if decoded is None:
                return "invalid_base64"

        effective_size = size
        if decoded is not None:
            if size is not None and size != len(decoded):
                return "attachment_size_mismatch"
            effective_size = len(decoded)

        if effective_size is None:
            return "missing_attachment_size"

        if effective_size > (field.get("maxSize") or MAX_ATTACHMENT_BYTES):
            return "attachment_too_large"
        total_bytes += effective_size

    if total_bytes > MAX_TOTAL_ATTACHMENT_BYTES:
        return "attachments_too_large"
    if not field.get("allowMultiple") and len(value) > 1:
        return "too_many_attachments"
    return None


def _validate_matrix(value: Any, field: Dict[str, Any]) -> Optional[str]:
    if not isinstance(value, dict):
        return "type_mismatch"
    rows = field.get("rows")
    cols = field.get("columns")
    for row_key, col_value in value.items():
        if rows and str(row_key) not in rows:
            return "invalid_row"
        if cols and str(col_value) not in cols:
            return "invalid_choice"
    return None


def _validate_matrix_dropdown(value: Any, field: Dict[str, Any]) -> Optional[str]:
    if not isinstance(value, dict):
        return "type_mismatch"
    rows = field.get("rows")
    columns_meta = field.get("columns_meta") or []
    column_names = {col.get("name") for col in columns_meta if isinstance(col, dict)}
    for row_key, row_value in value.items():
        if rows and str(row_key) not in rows:
            return "invalid_row"
        if not isinstance(row_value, dict):
            return "type_mismatch"
        for col_key, cell_value in row_value.items():
            if column_names and col_key not in column_names:
                return "invalid_column"
            # basic scalar enforcement
            if isinstance(cell_value, (list, dict)):
                return "invalid_cell"
    return None


def _validate_paneldynamic(
    value: Any, field: Dict[str, Any]
) -> Optional[Tuple[str, Optional[str]]]:
    if not isinstance(value, list):
        return "type_mismatch", None
    max_items = field.get("maxItems")
    if max_items is not None and len(value) > max_items:
        return "too_many_items", None
    template_fields = field.get("template") or {}
    for item in value:
        if not isinstance(item, dict):
            return "type_mismatch", None
        result = _validate_fields(template_fields, item)
        if result is not None:
            return result
    return None


def _parse_literal(value: str) -> Any:
    trimmed = value.strip()
    if trimmed.startswith("'") and trimmed.endswith("'"):
        return trimmed[1:-1]
    if trimmed.startswith('"') and trimmed.endswith('"'):
        return trimmed[1:-1]
    lowered = trimmed.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in trimmed:
            return float(trimmed)
        return int(trimmed)
    except ValueError:
        return trimmed


def _evaluate_condition(expression: str, payload: Dict[str, Any]) -> Optional[bool]:
    expr = (expression or "").strip()
    if not expr:
        return None
    match = re.match(r"^\{([^}]+)\}\s*(=|!=|<>|>=|<=|>|<)\s*(.+)$", expr)
    if match:
        field_name, op, literal = match.groups()
        left = payload.get(field_name.strip())
        right = _parse_literal(literal)
        if op == "=":
            return left == right
        if op in {"!=", "<>"}:
            return left != right
        if op == ">":
            return left > right
        if op == "<":
            return left < right
        if op == ">=":
            return left >= right
        if op == "<=":
            return left <= right
    match = re.match(r"^\{([^}]+)\}\s*contains\s*(.+)$", expr, flags=re.IGNORECASE)
    if match:
        field_name, literal = match.groups()
        left = payload.get(field_name.strip())
        right = _parse_literal(literal)
        if isinstance(left, (list, tuple, set)):
            return right in left
        if isinstance(left, str):
            return str(right) in left
        return False
    return None


def _validator_kind(validator: Dict[str, Any]) -> Optional[str]:
    vtype = validator.get("type")
    if vtype:
        return str(vtype).lower()
    if "regex" in validator:
        return "regex"
    if "minValue" in validator or "maxValue" in validator:
        return "numeric"
    if "minLength" in validator or "maxLength" in validator:
        return "text"
    if "minCount" in validator or "maxCount" in validator:
        return "answercount"
    if "expression" in validator:
        return "expression"
    return None


def _apply_validators(
    value: Any, field: Dict[str, Any], payload: Dict[str, Any]
) -> Optional[str]:
    validators = field.get("validators") or []
    for validator in validators:
        if not isinstance(validator, dict):
            return "invalid_validator"
        kind = _validator_kind(validator)
        if kind == "numeric":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return "type_mismatch"
            min_value = validator.get("minValue")
            max_value = validator.get("maxValue")
            if min_value is not None and value < min_value:
                return "out_of_range"
            if max_value is not None and value > max_value:
                return "out_of_range"
        elif kind == "text":
            if not isinstance(value, str):
                return "type_mismatch"
            min_len = validator.get("minLength")
            max_len = validator.get("maxLength")
            if min_len is not None and len(value) < min_len:
                return "text_too_short"
            if max_len is not None and len(value) > max_len:
                return "text_too_long"
        elif kind == "answercount":
            if not isinstance(value, list):
                return "type_mismatch"
            min_count = validator.get("minCount")
            max_count = validator.get("maxCount")
            if min_count is not None and len(value) < min_count:
                return "too_few_choices"
            if max_count is not None and len(value) > max_count:
                return "too_many_choices"
        elif kind == "regex":
            if not isinstance(value, str):
                return "type_mismatch"
            pattern = validator.get("regex")
            if not isinstance(pattern, str):
                return "invalid_validator"
            flags = 0
            if validator.get("caseInsensitive") or validator.get("insensitive"):
                flags = re.IGNORECASE
            if re.search(pattern, value, flags=flags) is None:
                return "regex_mismatch"
        elif kind == "email":
            if not isinstance(value, str):
                return "type_mismatch"
            if re.match(r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", value) is None:
                return "invalid_email"
        elif kind == "expression":
            expression = validator.get("expression")
            if not isinstance(expression, str):
                return "invalid_validator"
            result = _evaluate_condition(expression, payload)
            if result is False:
                return "expression_failed"
            if result is None:
                return "unsupported_expression"
        else:
            return "unsupported_validator"
    return None


def _validate_fields(
    fields: Dict[str, Dict[str, Any]],
    payload: Dict[str, Any],
) -> Optional[Tuple[str, Optional[str]]]:
    if len(payload) > MAX_FIELDS:
        return "too_many_fields", None

    for key in payload.keys():
        if key not in fields:
            return "unknown_field", key

    for name, field in fields.items():
        required = field.get("required")
        visible_if = field.get("visibleIf")
        if visible_if:
            visible = _evaluate_condition(visible_if, payload)
            if visible is False:
                required = False
        required_if = field.get("requiredIf")
        if not required and required_if:
            cond = _evaluate_condition(required_if, payload)
            if cond is True:
                required = True
        if required and (name not in payload or _is_empty_value(payload.get(name))):
            logger.info("validation field=%s required_missing", name)
            return "missing_required", name

    for name, value in payload.items():
        field = fields[name]
        ftype = field.get("type")
        logger.info(
            "validation field=%s type=%s value_type=%s",
            name,
            ftype,
            type(value).__name__,
        )

        if ftype in ("text", "comment"):
            if field.get("inputType") == "number":
                error = _validate_number(value, field)
            else:
                error = _validate_text(value, field)
        elif ftype in ("radiogroup", "dropdown"):
            error = _validate_choice(value, field)
        elif ftype == "checkbox":
            error = _validate_checkbox(value, field)
        elif ftype in ("rating", "score"):
            error = _validate_rating(value, field)
        elif ftype in ("number", "numeric"):
            error = _validate_number(value, field)
        elif ftype in ("boolean", "switch"):
            error = _validate_boolean(value)
        elif ftype in ("date", "datetime"):
            error = _validate_date(value)
        elif ftype == "file":
            error = _validate_files(value, field)
        elif ftype == "matrix":
            error = _validate_matrix(value, field)
        elif ftype in ("matrixdropdown", "matrixdynamic"):
            error = _validate_matrix_dropdown(value, field)
        elif ftype == "paneldynamic":
            panel_error = _validate_paneldynamic(value, field)
            if panel_error is not None:
                reason, inner_field = panel_error
                logger.info(
                    "validation field=%s paneldynamic_error=%s inner_field=%s",
                    name,
                    reason,
                    inner_field,
                )
                if inner_field:
                    return reason, f"{name}.{inner_field}"
                return reason, name
            error = None
        else:
            logger.info("validation field=%s unsupported_type=%s", name, ftype)
            return "unsupported_field_type", name

        if error:
            logger.info("validation field=%s error=%s", name, error)
            return error, name
        validator_error = _apply_validators(value, field, payload)
        if validator_error:
            logger.info("validation field=%s validator_error=%s", name, validator_error)
            return validator_error, name
        logger.info("validation field=%s ok", name)

    return None


def validate_submission(
    form_json: Dict[str, Any], payload: Dict[str, Any]
) -> ValidationResult:
    if not isinstance(payload, dict):
        return ValidationResult(False, 400, "invalid_payload")

    fields = build_schema_index(form_json)
    error = _validate_fields(fields, payload)
    if error:
        reason, field = error
        return ValidationResult(False, 400, reason, field=field)
    return ValidationResult(True, 200, "ok")
