from __future__ import annotations

import base64

import pytest

from zopyx.surveyjs import validation as v


def _form_with_elements(elements):
    return {"pages": [{"elements": elements}]}


def test_validate_submission_accepts_number_input_type_string() -> None:
    form_json = _form_with_elements(
        [
            {"type": "text", "name": "age", "inputType": "number", "minValue": 1},
            {"type": "date", "name": "when"},
        ]
    )
    payload = {"age": "5", "when": "2024-01-01T10:00:00Z"}
    result = v.validate_submission(form_json, payload)
    assert result.ok is True


def test_required_if_and_visible_if_rules() -> None:
    form_json = _form_with_elements(
        [
            {"type": "text", "name": "q1"},
            {"type": "text", "name": "q2", "requiredIf": "{q1} = 'yes'"},
            {"type": "text", "name": "q3", "isRequired": True, "visibleIf": "{q1} = 'no'"},
        ]
    )
    result_missing = v.validate_submission(form_json, {"q1": "yes"})
    assert result_missing.ok is False
    assert result_missing.reason == "missing_required"
    assert result_missing.field == "q2"

    result_hidden = v.validate_submission(form_json, {"q1": "yes", "q2": "ok"})
    assert result_hidden.ok is True


def test_unknown_field_rejected() -> None:
    form_json = _form_with_elements([{"type": "text", "name": "q1"}])
    result = v.validate_submission(form_json, {"q2": "nope"})
    assert result.ok is False
    assert result.reason == "unknown_field"
    assert result.field == "q2"


def test_validators_apply_numeric_text_answercount_regex_email_expression() -> None:
    form_json = _form_with_elements(
        [
            {
                "type": "number",
                "name": "n1",
                "validators": [{"minValue": 1, "maxValue": 3}],
            },
            {
                "type": "text",
                "name": "t1",
                "validators": [{"minLength": 2, "maxLength": 4}],
            },
            {
                "type": "checkbox",
                "name": "c1",
                "validators": [{"minCount": 1, "maxCount": 2}],
                "choices": ["a", "b", "c"],
            },
            {
                "type": "text",
                "name": "r1",
                "validators": [{"regex": r"^hi", "caseInsensitive": True}],
            },
            {
                "type": "text",
                "name": "x1",
                "validators": [{"type": "expression", "expression": "{n1} >= 2"}],
            },
        ]
    )
    payload = {
        "n1": 2,
        "t1": "hey",
        "c1": ["a"],
        "r1": "Hi there",
        "x1": "ok",
    }
    result = v.validate_submission(form_json, payload)
    assert result.ok is True


def test_validator_failures_are_reported() -> None:
    form_json = _form_with_elements(
        [
            {"type": "text", "name": "t1", "validators": [{"regex": "^ok$"}]},
            {"type": "text", "name": "e1", "validators": [{"type": "email"}]},
            {"type": "text", "name": "x1", "validators": [{"type": "expression", "expression": "bad expr"}]},
        ]
    )
    result = v.validate_submission(form_json, {"t1": "nope", "e1": "not-an-email", "x1": "x"})
    assert result.ok is False
    assert result.reason in {"regex_mismatch", "invalid_email", "unsupported_expression"}


def test_invalid_and_unsupported_validators() -> None:
    form_json_invalid = _form_with_elements(
        [{"type": "text", "name": "t1", "validators": ["not-a-dict"]}]
    )
    result_invalid = v.validate_submission(form_json_invalid, {"t1": "ok"})
    assert result_invalid.reason == "invalid_validator"

    form_json_unsupported = _form_with_elements(
        [{"type": "text", "name": "t1", "validators": [{"type": "unknown"}]}]
    )
    result_unsupported = v.validate_submission(form_json_unsupported, {"t1": "ok"})
    assert result_unsupported.reason == "unsupported_validator"


def test_file_validation_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    form_json = _form_with_elements(
        [
            {
                "type": "file",
                "name": "f1",
                "allowMultiple": False,
                "maxSize": 10,
            }
        ]
    )
    # Unsupported mime when allowlist is set
    monkeypatch.setattr(v, "ALLOWED_MIME_TYPES", {"image/png"})
    payload_bad_mime = {"f1": [{"name": "a.txt", "type": "text/plain", "size": 1, "content": "YWJj"}]}
    result_bad_mime = v.validate_submission(form_json, payload_bad_mime)
    assert result_bad_mime.reason == "unsupported_mime"

    # Invalid base64 and missing size
    monkeypatch.setattr(v, "ALLOWED_MIME_TYPES", None)
    payload_invalid_b64 = {"f1": [{"name": "a.bin", "type": "application/octet-stream", "content": "not-base64"}]}
    result_invalid_b64 = v.validate_submission(form_json, payload_invalid_b64)
    assert result_invalid_b64.reason == "invalid_base64"

    # Size mismatch
    b64 = base64.b64encode(b"abc").decode("ascii")
    payload_mismatch = {"f1": [{"name": "a.bin", "type": "application/octet-stream", "content": b64, "size": 2}]}
    result_mismatch = v.validate_submission(form_json, payload_mismatch)
    assert result_mismatch.reason == "attachment_size_mismatch"

    # Too many attachments for single file field
    payload_too_many = {
        "f1": [
            {"name": "a.bin", "type": "application/octet-stream", "content": b64, "size": 3},
            {"name": "b.bin", "type": "application/octet-stream", "content": b64, "size": 3},
        ]
    }
    result_too_many = v.validate_submission(form_json, payload_too_many)
    assert result_too_many.reason == "too_many_attachments"


def test_matrix_and_matrixdropdown_validation() -> None:
    form_json = _form_with_elements(
        [
            {"type": "matrix", "name": "m1", "rows": ["r1"], "columns": ["c1"]},
            {"type": "matrixdropdown", "name": "m2", "rows": ["r1"], "columns": [{"name": "c1"}]},
        ]
    )
    result_row = v.validate_submission(form_json, {"m1": {"r2": "c1"}, "m2": {"r1": {"c1": "ok"}}})
    assert result_row.reason == "invalid_row"

    result_col = v.validate_submission(form_json, {"m1": {"r1": "c2"}, "m2": {"r1": {"c1": "ok"}}})
    assert result_col.reason == "invalid_choice"

    result_cell = v.validate_submission(form_json, {"m1": {"r1": "c1"}, "m2": {"r1": {"bad": []}}})
    assert result_cell.reason in {"invalid_column", "invalid_cell"}


def test_paneldynamic_field_path() -> None:
    form_json = _form_with_elements(
        [
            {
                "type": "paneldynamic",
                "name": "panel",
                "templateElements": [{"type": "text", "name": "inner", "isRequired": True}],
            }
        ]
    )
    result = v.validate_submission(form_json, {"panel": [{}]})
    assert result.reason == "missing_required"
    assert result.field == "panel.inner"


def test_unsupported_field_type_and_payload_type() -> None:
    form_json = _form_with_elements([{"type": "unknown", "name": "q1"}])
    result = v.validate_submission(form_json, {"q1": "x"})
    assert result.reason == "unsupported_field_type"
    assert result.field == "q1"

    result_invalid = v.validate_submission(form_json, ["bad"])
    assert result_invalid.reason == "invalid_payload"


def test_internal_helpers_are_exercised() -> None:
    assert v._choices_to_set([]) is None
    assert v._choices_to_set([{"value": 1}, {"value": None}, "x"]) == {"1", "x"}

    fields = {}
    v._parse_elements(
        [
            {"type": "panel", "elements": [{"type": "text", "name": "inside"}]},
            {
                "type": "paneldynamic",
                "name": "dyn",
                "templateElements": [{"type": "text", "name": "inner"}],
            },
            {"type": "text"},
        ],
        fields,
    )
    assert "inside" in fields
    assert fields["dyn"]["type"] == "paneldynamic"

    assert v._is_empty_value(None) is True
    assert v._is_empty_value("") is True
    assert v._is_empty_value([]) is True
    assert v._is_empty_value({}) is True
    assert v._is_empty_value("x") is False

    assert v._parse_literal("'yes'") == "yes"
    assert v._parse_literal('"yes"') == "yes"
    assert v._parse_literal("true") is True
    assert v._parse_literal("1") == 1
    assert v._parse_literal("1.5") == 1.5
    assert v._parse_literal("hello") == "hello"

    assert v._evaluate_condition("", {"a": "b"}) is None
    assert v._evaluate_condition("{a} = 'b'", {"a": "b"}) is True
    assert v._evaluate_condition("{a} != 'b'", {"a": "c"}) is True
    assert v._evaluate_condition("{a} >= 2", {"a": 2}) is True
    assert v._evaluate_condition("{a} <= 1", {"a": 1}) is True
    assert v._evaluate_condition("{a} > 1", {"a": 2}) is True
    assert v._evaluate_condition("{a} < 1", {"a": 0}) is True
    assert v._evaluate_condition("{a} contains 'x'", {"a": ["x", "y"]}) is True
    assert v._evaluate_condition("{a} contains 'x'", {"a": "x-ray"}) is True
    assert v._evaluate_condition("{a} contains 'x'", {"a": 1}) is False
    assert v._evaluate_condition("unsupported expression", {"a": "b"}) is None

    assert v._validator_kind({"type": "email"}) == "email"
    assert v._validator_kind({"regex": "x"}) == "regex"
    assert v._validator_kind({"minValue": 1}) == "numeric"
    assert v._validator_kind({"minLength": 1}) == "text"
    assert v._validator_kind({"minCount": 1}) == "answercount"
    assert v._validator_kind({"expression": "x"}) == "expression"
    assert v._validator_kind({}) is None


def test_validate_text_number_rating_choice_checkbox_boolean_date_paths() -> None:
    assert v._validate_text(1, {}) == "type_mismatch"
    assert v._validate_text("a", {"minLength": 2}) == "text_too_short"
    assert v._validate_text("abcd", {"maxLength": 3}) == "text_too_long"
    assert v._validate_text("bad\x07", {}) == "invalid_control_chars"
    assert v._validate_text("ok", {}) is None

    assert v._validate_number(True, {}) == "type_mismatch"
    assert v._validate_number("nope", {}) == "type_mismatch"
    assert v._validate_number(["x"], {}) == "type_mismatch"
    assert v._validate_number("5.1", {"maxValue": 5}) == "out_of_range"
    assert v._validate_number(0, {"minValue": 1}) == "out_of_range"
    assert v._validate_number(2, {"minValue": 1, "maxValue": 3}) is None

    assert v._validate_rating([], {}) == "type_mismatch"
    assert v._validate_rating("x", {}) == "type_mismatch"
    assert v._validate_rating(1, {"rateMin": 2}) == "out_of_range"
    assert v._validate_rating(5, {"rateMax": 4}) == "out_of_range"
    assert v._validate_rating(2, {"rateValues": {"1", "3"}}) == "invalid_choice"
    assert v._validate_rating("2", {"rateMin": 1, "rateMax": 3}) is None

    assert v._validate_choice(True, {}) == "type_mismatch"
    assert v._validate_choice("x", {"choices": {"y"}}) == "invalid_choice"
    assert v._validate_choice("x", {"choices": {"x"}}) is None

    assert v._validate_checkbox("x", {}) == "type_mismatch"
    assert v._validate_checkbox(list(range(v.MAX_CHOICES + 1)), {}) == "too_many_choices"
    assert v._validate_checkbox([], {"minSelectedChoices": 1}) == "too_few_choices"
    assert v._validate_checkbox(["a", "b"], {"maxSelectedChoices": 1}) == "too_many_choices"
    assert v._validate_checkbox(["x"], {"choices": {"y"}}) == "invalid_choice"
    assert v._validate_checkbox(["x"], {"choices": {"x"}}) is None

    assert v._validate_boolean("true") == "type_mismatch"
    assert v._validate_boolean(True) is None

    assert v._validate_date(123) == "type_mismatch"
    assert v._validate_date("2024-13-01") == "invalid_date"
    assert v._validate_date("2024-01-01T00:00:00Z") is None


def test_base64_and_file_validation_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    assert v._decode_base64("data:text/plain;base64") is None
    assert v._decode_base64("not-base64") is None
    assert v._decode_base64("data:text/plain;base64," + base64.b64encode(b"ok").decode("ascii")) == b"ok"
    assert v._decode_base64(base64.b64encode(b"ok").decode("ascii")) == b"ok"

    assert v._validate_files("x", {}) == "type_mismatch"
    assert v._validate_files([{}] * (v.MAX_ATTACHMENTS + 1), {}) == "too_many_attachments"
    assert v._validate_files(["not-a-dict"], {}) == "invalid_attachment"
    assert v._validate_files([{"name": ""}], {}) == "invalid_attachment"
    assert v._validate_files([{"name": "a", "size": "1"}], {}) == "invalid_attachment"
    assert v._validate_files([{"name": "a", "type": "bad"}], {}) == "invalid_attachment"
    assert v._validate_files([{"name": "a", "content": 123}], {}) == "invalid_attachment"
    assert v._validate_files([{"name": "a", "content": "not-base64"}], {}) == "invalid_base64"
    assert (
        v._validate_files([{"name": "a", "content": base64.b64encode(b"abc").decode("ascii"), "size": 2}], {})
        == "attachment_size_mismatch"
    )
    assert v._validate_files([{"name": "a"}], {}) == "missing_attachment_size"
    assert v._validate_files([{"name": "a", "size": v.MAX_ATTACHMENT_BYTES + 1}], {}) == "attachment_too_large"

    monkeypatch.setattr(v, "MAX_TOTAL_ATTACHMENT_BYTES", 1)
    assert v._validate_files([{"name": "a", "size": 1}, {"name": "b", "size": 1}], {}) == "attachments_too_large"
    monkeypatch.setattr(v, "MAX_TOTAL_ATTACHMENT_BYTES", 5_000_000)

    monkeypatch.setattr(v, "ALLOWED_MIME_TYPES", {"image/png"})
    assert (
        v._validate_files([{"name": "a", "type": "text/plain", "size": 1}], {})
        == "unsupported_mime"
    )
    monkeypatch.setattr(v, "ALLOWED_MIME_TYPES", None)

    assert v._validate_files([{"name": "a", "size": 1}, {"name": "b", "size": 1}], {"allowMultiple": False}) == "too_many_attachments"


def test_matrix_and_panel_helpers() -> None:
    assert v._validate_matrix([], {}) == "type_mismatch"
    assert v._validate_matrix({"r2": "c1"}, {"rows": {"r1"}, "columns": {"c1"}}) == "invalid_row"
    assert v._validate_matrix({"r1": "c2"}, {"rows": {"r1"}, "columns": {"c1"}}) == "invalid_choice"
    assert v._validate_matrix({"r1": "c1"}, {"rows": {"r1"}, "columns": {"c1"}}) is None

    assert v._validate_matrix_dropdown([], {}) == "type_mismatch"
    assert v._validate_matrix_dropdown({"r2": {}}, {"rows": {"r1"}, "columns_meta": []}) == "invalid_row"
    assert v._validate_matrix_dropdown({"r1": "x"}, {"rows": {"r1"}, "columns_meta": []}) == "type_mismatch"
    assert (
        v._validate_matrix_dropdown({"r1": {"bad": "x"}}, {"rows": {"r1"}, "columns_meta": [{"name": "c1"}]})
        == "invalid_column"
    )
    assert (
        v._validate_matrix_dropdown({"r1": {"c1": []}}, {"rows": {"r1"}, "columns_meta": [{"name": "c1"}]})
        == "invalid_cell"
    )
    assert (
        v._validate_matrix_dropdown({"r1": {"c1": "ok"}}, {"rows": {"r1"}, "columns_meta": [{"name": "c1"}]})
        is None
    )

    assert v._validate_paneldynamic({}, {}) == ("type_mismatch", None)
    assert v._validate_paneldynamic([{}], {"maxItems": 0}) == ("too_many_items", None)
    assert v._validate_paneldynamic([[]], {}) == ("type_mismatch", None)
    template_fields = {"inner": {"type": "text", "required": True}}
    assert v._validate_paneldynamic([{}], {"template": template_fields}) == ("missing_required", "inner")
    assert v._validate_paneldynamic([{"inner": "ok"}], {"template": template_fields}) is None


def test_paneldynamic_error_without_inner_field() -> None:
    form_json = _form_with_elements([{"type": "paneldynamic", "name": "p"}])
    result = v.validate_submission(form_json, {"p": {}})
    assert result.reason == "type_mismatch"
    assert result.field == "p"


def test_paneldynamic_success_path() -> None:
    form_json = _form_with_elements(
        [
            {
                "type": "paneldynamic",
                "name": "p",
                "templateElements": [{"type": "text", "name": "inner", "isRequired": True}],
            }
        ]
    )
    result = v.validate_submission(form_json, {"p": [{"inner": "ok"}]})
    assert result.ok is True


def test_apply_validators_branches() -> None:
    assert v._apply_validators(1, {"validators": ["bad"]}, {}) == "invalid_validator"
    assert v._apply_validators(True, {"validators": [{"minValue": 1}]}, {}) == "type_mismatch"
    assert v._apply_validators(0, {"validators": [{"minValue": 1}]}, {}) == "out_of_range"
    assert v._apply_validators(2, {"validators": [{"maxValue": 1}]}, {}) == "out_of_range"
    assert v._apply_validators(1, {"validators": [{"minValue": 1, "maxValue": 2}]}, {}) is None

    assert v._apply_validators(1, {"validators": [{"minLength": 2}]}, {}) == "type_mismatch"
    assert v._apply_validators("a", {"validators": [{"minLength": 2}]}, {}) == "text_too_short"
    assert v._apply_validators("abcd", {"validators": [{"maxLength": 2}]}, {}) == "text_too_long"

    assert v._apply_validators("x", {"validators": [{"minCount": 1}]}, {}) == "type_mismatch"
    assert v._apply_validators([], {"validators": [{"minCount": 1}]}, {}) == "too_few_choices"
    assert v._apply_validators(["a", "b"], {"validators": [{"maxCount": 1}]}, {}) == "too_many_choices"

    assert v._apply_validators(1, {"validators": [{"regex": "^x"}]}, {}) == "type_mismatch"
    assert v._apply_validators("x", {"validators": [{"regex": 123}]}, {}) == "invalid_validator"
    assert v._apply_validators("y", {"validators": [{"regex": "^x"}]}, {}) == "regex_mismatch"

    assert v._apply_validators(1, {"validators": [{"type": "email"}]}, {}) == "type_mismatch"
    assert v._apply_validators("nope", {"validators": [{"type": "email"}]}, {}) == "invalid_email"

    assert v._apply_validators("x", {"validators": [{"type": "expression", "expression": 1}]}, {}) == "invalid_validator"
    assert v._apply_validators("x", {"validators": [{"type": "expression", "expression": "{a} = 1"}]}, {"a": 2}) == "expression_failed"
    assert v._apply_validators("x", {"validators": [{"type": "expression", "expression": "bad"}]}, {}) == "unsupported_expression"

    assert v._apply_validators("x", {"validators": [{"foo": "bar"}]}, {}) == "unsupported_validator"


def test_validate_fields_all_types(monkeypatch: pytest.MonkeyPatch) -> None:
    form_json = _form_with_elements(
        [
            {"type": "radiogroup", "name": "r", "choices": ["a"]},
            {"type": "dropdown", "name": "d", "choices": ["a"]},
            {"type": "rating", "name": "rate", "rateMin": 1, "rateMax": 3},
            {"type": "score", "name": "score", "rateMin": 1, "rateMax": 3},
            {"type": "number", "name": "n", "minValue": 1, "maxValue": 3},
            {"type": "numeric", "name": "num", "min": 1, "max": 3},
            {"type": "boolean", "name": "b"},
            {"type": "switch", "name": "s"},
            {"type": "datetime", "name": "dt"},
            {"type": "file", "name": "f", "allowMultiple": True},
            {"type": "matrixdynamic", "name": "md", "rows": ["r1"], "columns": [{"name": "c1"}]},
        ]
    )
    payload = {
        "r": "a",
        "d": "a",
        "rate": 2,
        "score": 2,
        "n": 2,
        "num": 2,
        "b": True,
        "s": False,
        "dt": "2024-01-01T00:00:00Z",
        "f": [{"name": "a", "size": 1}],
        "md": {"r1": {"c1": "ok"}},
    }
    assert v.validate_submission(form_json, payload).ok is True

    monkeypatch.setattr(v, "MAX_FIELDS", 1)
    too_many = {"a": 1, "b": 2}
    fields = {"a": {"type": "text"}}
    assert v._validate_fields(fields, too_many)[0] == "too_many_fields"
    monkeypatch.setattr(v, "MAX_FIELDS", 500)
