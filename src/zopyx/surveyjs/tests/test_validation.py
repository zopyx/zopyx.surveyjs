from __future__ import annotations

import base64
import unittest
from unittest.mock import patch

from zopyx.surveyjs import validation as v


def _form_with_elements(elements):
    return {"pages": [{"elements": elements}]}


class ValidationTests(unittest.TestCase):
    def test_validate_submission_accepts_number_input_type_string(self) -> None:
        form_json = _form_with_elements(
            [
                {"type": "text", "name": "age", "inputType": "number", "minValue": 1},
                {"type": "date", "name": "when"},
            ]
        )
        payload = {"age": "5", "when": "2024-01-01T10:00:00Z"}
        result = v.validate_submission(form_json, payload)
        self.assertTrue(result.ok)

    def test_required_if_and_visible_if_rules(self) -> None:
        form_json = _form_with_elements(
            [
                {"type": "text", "name": "q1"},
                {"type": "text", "name": "q2", "requiredIf": "{q1} = 'yes'"},
                {"type": "text", "name": "q3", "isRequired": True, "visibleIf": "{q1} = 'no'"},
            ]
        )
        result_missing = v.validate_submission(form_json, {"q1": "yes"})
        self.assertFalse(result_missing.ok)
        self.assertEqual(result_missing.reason, "missing_required")
        self.assertEqual(result_missing.field, "q2")

        result_hidden = v.validate_submission(form_json, {"q1": "yes", "q2": "ok"})
        self.assertTrue(result_hidden.ok)

    def test_unknown_field_rejected(self) -> None:
        form_json = _form_with_elements([{"type": "text", "name": "q1"}])
        result = v.validate_submission(form_json, {"q2": "nope"})
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "unknown_field")
        self.assertEqual(result.field, "q2")

    def test_validators_apply_numeric_text_answercount_regex_expression(self) -> None:
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
        self.assertTrue(result.ok)

    def test_validator_failures_are_reported(self) -> None:
        form_json = _form_with_elements(
            [
                {"type": "text", "name": "t1", "validators": [{"regex": "^ok$"}]},
                {"type": "text", "name": "e1", "validators": [{"type": "email"}]},
                {
                    "type": "text",
                    "name": "x1",
                    "validators": [{"type": "expression", "expression": "bad expr"}],
                },
            ]
        )
        result = v.validate_submission(
            form_json, {"t1": "nope", "e1": "not-an-email", "x1": "x"}
        )
        self.assertFalse(result.ok)
        self.assertIn(
            result.reason, {"regex_mismatch", "invalid_email", "unsupported_expression"}
        )

    def test_invalid_and_unsupported_validators(self) -> None:
        form_json_invalid = _form_with_elements(
            [{"type": "text", "name": "t1", "validators": ["not-a-dict"]}]
        )
        result_invalid = v.validate_submission(form_json_invalid, {"t1": "ok"})
        self.assertEqual(result_invalid.reason, "invalid_validator")

        form_json_unsupported = _form_with_elements(
            [{"type": "text", "name": "t1", "validators": [{"type": "unknown"}]}]
        )
        result_unsupported = v.validate_submission(form_json_unsupported, {"t1": "ok"})
        self.assertEqual(result_unsupported.reason, "unsupported_validator")

    def test_file_validation_paths(self) -> None:
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
        with patch.object(v, "ALLOWED_MIME_TYPES", {"image/png"}):
            payload_bad_mime = {
                "f1": [
                    {
                        "name": "a.txt",
                        "type": "text/plain",
                        "size": 1,
                        "content": "YWJj",
                    }
                ]
            }
            result_bad_mime = v.validate_submission(form_json, payload_bad_mime)
            self.assertEqual(result_bad_mime.reason, "unsupported_mime")

        payload_invalid_b64 = {
            "f1": [
                {
                    "name": "a.bin",
                    "type": "application/octet-stream",
                    "content": "not-base64",
                }
            ]
        }
        result_invalid_b64 = v.validate_submission(form_json, payload_invalid_b64)
        self.assertEqual(result_invalid_b64.reason, "invalid_base64")

        b64 = base64.b64encode(b"abc").decode("ascii")
        payload_mismatch = {
            "f1": [
                {
                    "name": "a.bin",
                    "type": "application/octet-stream",
                    "content": b64,
                    "size": 2,
                }
            ]
        }
        result_mismatch = v.validate_submission(form_json, payload_mismatch)
        self.assertEqual(result_mismatch.reason, "attachment_size_mismatch")

        payload_too_many = {
            "f1": [
                {
                    "name": "a.bin",
                    "type": "application/octet-stream",
                    "content": b64,
                    "size": 3,
                },
                {
                    "name": "b.bin",
                    "type": "application/octet-stream",
                    "content": b64,
                    "size": 3,
                },
            ]
        }
        result_too_many = v.validate_submission(form_json, payload_too_many)
        self.assertEqual(result_too_many.reason, "too_many_attachments")

    def test_matrix_and_matrixdropdown_validation(self) -> None:
        form_json = _form_with_elements(
            [
                {"type": "matrix", "name": "m1", "rows": ["r1"], "columns": ["c1"]},
                {
                    "type": "matrixdropdown",
                    "name": "m2",
                    "rows": ["r1"],
                    "columns": [{"name": "c1"}],
                },
            ]
        )
        result_row = v.validate_submission(
            form_json, {"m1": {"r2": "c1"}, "m2": {"r1": {"c1": "ok"}}}
        )
        self.assertEqual(result_row.reason, "invalid_row")

        result_col = v.validate_submission(
            form_json, {"m1": {"r1": "c2"}, "m2": {"r1": {"c1": "ok"}}}
        )
        self.assertEqual(result_col.reason, "invalid_choice")

        result_cell = v.validate_submission(
            form_json, {"m1": {"r1": "c1"}, "m2": {"r1": {"bad": []}}}
        )
        self.assertIn(result_cell.reason, {"invalid_column", "invalid_cell"})

    def test_paneldynamic_field_path(self) -> None:
        form_json = _form_with_elements(
            [
                {
                    "type": "paneldynamic",
                    "name": "panel",
                    "templateElements": [
                        {"type": "text", "name": "inner", "isRequired": True}
                    ],
                }
            ]
        )
        result = v.validate_submission(form_json, {"panel": [{}]})
        self.assertEqual(result.reason, "missing_required")
        self.assertEqual(result.field, "panel.inner")

    def test_unsupported_field_type_and_payload_type(self) -> None:
        form_json = _form_with_elements([{"type": "unknown", "name": "q1"}])
        result = v.validate_submission(form_json, {"q1": "x"})
        self.assertEqual(result.reason, "unsupported_field_type")
        self.assertEqual(result.field, "q1")

        result_invalid = v.validate_submission(form_json, ["bad"])
        self.assertEqual(result_invalid.reason, "invalid_payload")

    def test_internal_helpers_are_exercised(self) -> None:
        self.assertIsNone(v._choices_to_set([]))
        self.assertEqual(v._choices_to_set([{"value": 1}, {"value": None}, "x"]), {"1", "x"})

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
        self.assertIn("inside", fields)
        self.assertEqual(fields["dyn"]["type"], "paneldynamic")

        self.assertTrue(v._is_empty_value(None))
        self.assertTrue(v._is_empty_value(""))
        self.assertTrue(v._is_empty_value([]))
        self.assertTrue(v._is_empty_value({}))
        self.assertFalse(v._is_empty_value("x"))

        self.assertEqual(v._parse_literal("'yes'"), "yes")
        self.assertEqual(v._parse_literal('"yes"'), "yes")
        self.assertTrue(v._parse_literal("true"))
        self.assertEqual(v._parse_literal("1"), 1)
        self.assertEqual(v._parse_literal("1.5"), 1.5)
        self.assertEqual(v._parse_literal("hello"), "hello")

        self.assertIsNone(v._evaluate_condition("", {"a": "b"}))
        self.assertTrue(v._evaluate_condition("{a} = 'b'", {"a": "b"}))
        self.assertTrue(v._evaluate_condition("{a} != 'b'", {"a": "c"}))
        self.assertTrue(v._evaluate_condition("{a} >= 2", {"a": 2}))
        self.assertTrue(v._evaluate_condition("{a} <= 1", {"a": 1}))
        self.assertTrue(v._evaluate_condition("{a} > 1", {"a": 2}))
        self.assertTrue(v._evaluate_condition("{a} < 1", {"a": 0}))
        self.assertTrue(v._evaluate_condition("{a} contains 'x'", {"a": ["x", "y"]}))
        self.assertTrue(v._evaluate_condition("{a} contains 'x'", {"a": "x-ray"}))
        self.assertFalse(v._evaluate_condition("{a} contains 'x'", {"a": 1}))
        self.assertIsNone(v._evaluate_condition("unsupported expression", {"a": "b"}))

        self.assertEqual(v._validator_kind({"type": "email"}), "email")
        self.assertEqual(v._validator_kind({"regex": "x"}), "regex")
        self.assertEqual(v._validator_kind({"minValue": 1}), "numeric")
        self.assertEqual(v._validator_kind({"minLength": 1}), "text")
        self.assertEqual(v._validator_kind({"minCount": 1}), "answercount")
        self.assertEqual(v._validator_kind({"expression": "x"}), "expression")
        self.assertIsNone(v._validator_kind({}))

    def test_validate_text_number_rating_choice_checkbox_boolean_date_paths(self) -> None:
        self.assertEqual(v._validate_text(1, {}), "type_mismatch")
        self.assertEqual(v._validate_text("a", {"minLength": 2}), "text_too_short")
        self.assertEqual(v._validate_text("abcd", {"maxLength": 3}), "text_too_long")
        self.assertEqual(v._validate_text("bad\x07", {}), "invalid_control_chars")
        self.assertIsNone(v._validate_text("ok", {}))

        self.assertEqual(v._validate_number(True, {}), "type_mismatch")
        self.assertEqual(v._validate_number("nope", {}), "type_mismatch")
        self.assertEqual(v._validate_number(["x"], {}), "type_mismatch")
        self.assertEqual(v._validate_number("5.1", {"maxValue": 5}), "out_of_range")
        self.assertEqual(v._validate_number(0, {"minValue": 1}), "out_of_range")
        self.assertIsNone(v._validate_number(2, {"minValue": 1, "maxValue": 3}))

        self.assertEqual(v._validate_rating([], {}), "type_mismatch")
        self.assertEqual(v._validate_rating("x", {}), "type_mismatch")
        self.assertEqual(v._validate_rating(1, {"rateMin": 2}), "out_of_range")
        self.assertEqual(v._validate_rating(5, {"rateMax": 4}), "out_of_range")
        self.assertEqual(v._validate_rating(2, {"rateValues": {"1", "3"}}), "invalid_choice")
        self.assertIsNone(v._validate_rating("2", {"rateMin": 1, "rateMax": 3}))

        self.assertEqual(v._validate_choice(True, {}), "type_mismatch")
        self.assertEqual(v._validate_choice("x", {"choices": {"y"}}), "invalid_choice")
        self.assertIsNone(v._validate_choice("x", {"choices": {"x"}}))

        self.assertEqual(v._validate_checkbox("x", {}), "type_mismatch")
        self.assertEqual(
            v._validate_checkbox(list(range(v.MAX_CHOICES + 1)), {}),
            "too_many_choices",
        )
        self.assertEqual(v._validate_checkbox([], {"minSelectedChoices": 1}), "too_few_choices")
        self.assertEqual(
            v._validate_checkbox(["a", "b"], {"maxSelectedChoices": 1}),
            "too_many_choices",
        )
        self.assertEqual(v._validate_checkbox(["x"], {"choices": {"y"}}), "invalid_choice")
        self.assertIsNone(v._validate_checkbox(["x"], {"choices": {"x"}}))

        self.assertEqual(v._validate_boolean("true"), "type_mismatch")
        self.assertIsNone(v._validate_boolean(True))

        self.assertEqual(v._validate_date(123), "type_mismatch")
        self.assertEqual(v._validate_date("2024-13-01"), "invalid_date")
        self.assertIsNone(v._validate_date("2024-01-01T00:00:00Z"))

    def test_base64_and_file_validation_helpers(self) -> None:
        self.assertIsNone(v._decode_base64("data:text/plain;base64"))
        self.assertIsNone(v._decode_base64("not-base64"))
        data_url = "data:text/plain;base64," + base64.b64encode(b"ok").decode("ascii")
        self.assertEqual(v._decode_base64(data_url), b"ok")
        self.assertEqual(v._decode_base64(base64.b64encode(b"ok").decode("ascii")), b"ok")

        self.assertEqual(v._validate_files("x", {}), "type_mismatch")
        self.assertEqual(
            v._validate_files([{}] * (v.MAX_ATTACHMENTS + 1), {}),
            "too_many_attachments",
        )
        self.assertEqual(v._validate_files(["not-a-dict"], {}), "invalid_attachment")
        self.assertEqual(v._validate_files([{"name": ""}], {}), "invalid_attachment")
        self.assertEqual(v._validate_files([{"name": "a", "size": "1"}], {}), "invalid_attachment")
        self.assertEqual(v._validate_files([{"name": "a", "type": "bad"}], {}), "invalid_attachment")
        self.assertEqual(v._validate_files([{"name": "a", "content": 123}], {}), "invalid_attachment")
        self.assertEqual(v._validate_files([{"name": "a", "content": "not-base64"}], {}), "invalid_base64")
        self.assertEqual(
            v._validate_files(
                [{"name": "a", "content": base64.b64encode(b"abc").decode("ascii"), "size": 2}],
                {},
            ),
            "attachment_size_mismatch",
        )
        self.assertEqual(v._validate_files([{"name": "a"}], {}), "missing_attachment_size")
        self.assertEqual(
            v._validate_files([{"name": "a", "size": v.MAX_ATTACHMENT_BYTES + 1}], {}),
            "attachment_too_large",
        )

        with patch.object(v, "MAX_TOTAL_ATTACHMENT_BYTES", 1):
            self.assertEqual(
                v._validate_files([{"name": "a", "size": 1}, {"name": "b", "size": 1}], {}),
                "attachments_too_large",
            )

        with patch.object(v, "ALLOWED_MIME_TYPES", {"image/png"}):
            self.assertEqual(
                v._validate_files([{"name": "a", "type": "text/plain", "size": 1}], {}),
                "unsupported_mime",
            )

        self.assertEqual(
            v._validate_files(
                [{"name": "a", "size": 1}, {"name": "b", "size": 1}],
                {"allowMultiple": False},
            ),
            "too_many_attachments",
        )

    def test_matrix_and_panel_helpers(self) -> None:
        self.assertEqual(v._validate_matrix([], {}), "type_mismatch")
        self.assertEqual(
            v._validate_matrix({"r2": "c1"}, {"rows": {"r1"}, "columns": {"c1"}}),
            "invalid_row",
        )
        self.assertEqual(
            v._validate_matrix({"r1": "c2"}, {"rows": {"r1"}, "columns": {"c1"}}),
            "invalid_choice",
        )
        self.assertIsNone(
            v._validate_matrix({"r1": "c1"}, {"rows": {"r1"}, "columns": {"c1"}})
        )

        self.assertEqual(v._validate_matrix_dropdown([], {}), "type_mismatch")
        self.assertEqual(
            v._validate_matrix_dropdown({"r2": {}}, {"rows": {"r1"}, "columns_meta": []}),
            "invalid_row",
        )
        self.assertEqual(
            v._validate_matrix_dropdown({"r1": "x"}, {"rows": {"r1"}, "columns_meta": []}),
            "type_mismatch",
        )
        self.assertEqual(
            v._validate_matrix_dropdown(
                {"r1": {"bad": "x"}},
                {"rows": {"r1"}, "columns_meta": [{"name": "c1"}]},
            ),
            "invalid_column",
        )
        self.assertEqual(
            v._validate_matrix_dropdown(
                {"r1": {"c1": []}},
                {"rows": {"r1"}, "columns_meta": [{"name": "c1"}]},
            ),
            "invalid_cell",
        )
        self.assertIsNone(
            v._validate_matrix_dropdown(
                {"r1": {"c1": "ok"}},
                {"rows": {"r1"}, "columns_meta": [{"name": "c1"}]},
            )
        )

        self.assertEqual(v._validate_paneldynamic({}, {}), ("type_mismatch", None))
        self.assertEqual(v._validate_paneldynamic([{}], {"maxItems": 0}), ("too_many_items", None))
        self.assertEqual(v._validate_paneldynamic([[]], {}), ("type_mismatch", None))
        template_fields = {"inner": {"type": "text", "required": True}}
        self.assertEqual(
            v._validate_paneldynamic([{}], {"template": template_fields}),
            ("missing_required", "inner"),
        )
        self.assertIsNone(
            v._validate_paneldynamic([{"inner": "ok"}], {"template": template_fields})
        )

    def test_paneldynamic_error_without_inner_field(self) -> None:
        form_json = _form_with_elements([{"type": "paneldynamic", "name": "p"}])
        result = v.validate_submission(form_json, {"p": {}})
        self.assertEqual(result.reason, "type_mismatch")
        self.assertEqual(result.field, "p")

    def test_paneldynamic_success_path(self) -> None:
        form_json = _form_with_elements(
            [
                {
                    "type": "paneldynamic",
                    "name": "p",
                    "templateElements": [
                        {"type": "text", "name": "inner", "isRequired": True}
                    ],
                }
            ]
        )
        result = v.validate_submission(form_json, {"p": [{"inner": "ok"}]})
        self.assertTrue(result.ok)

    def test_apply_validators_branches(self) -> None:
        self.assertEqual(v._apply_validators(1, {"validators": ["bad"]}, {}), "invalid_validator")
        self.assertEqual(v._apply_validators(True, {"validators": [{"minValue": 1}]}, {}), "type_mismatch")
        self.assertEqual(v._apply_validators(0, {"validators": [{"minValue": 1}]}, {}), "out_of_range")
        self.assertEqual(v._apply_validators(2, {"validators": [{"maxValue": 1}]}, {}), "out_of_range")
        self.assertIsNone(v._apply_validators(1, {"validators": [{"minValue": 1, "maxValue": 2}]}, {}))

        self.assertEqual(v._apply_validators(1, {"validators": [{"minLength": 2}]}, {}), "type_mismatch")
        self.assertEqual(v._apply_validators("a", {"validators": [{"minLength": 2}]}, {}), "text_too_short")
        self.assertEqual(v._apply_validators("abcd", {"validators": [{"maxLength": 2}]}, {}), "text_too_long")

        self.assertEqual(v._apply_validators("x", {"validators": [{"minCount": 1}]}, {}), "type_mismatch")
        self.assertEqual(v._apply_validators([], {"validators": [{"minCount": 1}]}, {}), "too_few_choices")
        self.assertEqual(v._apply_validators(["a", "b"], {"validators": [{"maxCount": 1}]}, {}), "too_many_choices")

        self.assertEqual(v._apply_validators(1, {"validators": [{"regex": "^x"}]}, {}), "type_mismatch")
        self.assertEqual(v._apply_validators("x", {"validators": [{"regex": 123}]}, {}), "invalid_validator")
        self.assertEqual(v._apply_validators("y", {"validators": [{"regex": "^x"}]}, {}), "regex_mismatch")

        self.assertEqual(v._apply_validators(1, {"validators": [{"type": "email"}]}, {}), "type_mismatch")
        self.assertEqual(v._apply_validators("nope", {"validators": [{"type": "email"}]}, {}), "invalid_email")

        self.assertEqual(
            v._apply_validators("x", {"validators": [{"type": "expression", "expression": 1}]}, {}),
            "invalid_validator",
        )
        self.assertEqual(
            v._apply_validators("x", {"validators": [{"type": "expression", "expression": "{a} = 1"}]}, {"a": 2}),
            "expression_failed",
        )
        self.assertEqual(
            v._apply_validators("x", {"validators": [{"type": "expression", "expression": "bad"}]}, {}),
            "unsupported_expression",
        )

        self.assertEqual(v._apply_validators("x", {"validators": [{"foo": "bar"}]}, {}), "unsupported_validator")

    def test_validate_fields_all_types(self) -> None:
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
                {
                    "type": "matrixdynamic",
                    "name": "md",
                    "rows": ["r1"],
                    "columns": [{"name": "c1"}],
                },
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
        self.assertTrue(v.validate_submission(form_json, payload).ok)

        with patch.object(v, "MAX_FIELDS", 1):
            too_many = {"a": 1, "b": 2}
            fields = {"a": {"type": "text"}}
            self.assertEqual(v._validate_fields(fields, too_many)[0], "too_many_fields")


if __name__ == "__main__":
    unittest.main()
