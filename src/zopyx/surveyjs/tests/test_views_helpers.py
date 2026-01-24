from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import orjson

from zopyx.surveyjs.browser.views import (
    _extract_json_object,
    _mask_storage_location,
    _run_external_validation,
)


class ViewsHelperTests(unittest.TestCase):
    def test_extract_json_object(self) -> None:
        self.assertIsNone(_extract_json_object("no json here"))
        extracted = _extract_json_object('prefix {"a": 1} suffix')
        self.assertEqual(extracted, '{"a": 1}')

    def test_mask_storage_location_hides_password(self) -> None:
        self.assertEqual(_mask_storage_location("zodb"), "Plone (ZODB)")
        masked = _mask_storage_location("postgresql://user:secret@localhost/db")
        self.assertIn("%2A%2A%2A%2A", masked)
        self.assertNotIn("secret", masked)

    def test_run_external_validation_success(self) -> None:
        def fake_run(*, schema_json, form_json, result_json):
            result_path = Path(result_json)
            result_path.write_bytes(orjson.dumps({"valid": True}))
            return 0

        with patch(
            "zopyx.surveyjs.browser.views.run_data_validation",
            side_effect=fake_run,
        ):
            result = _run_external_validation({"a": 1}, {"b": 2}, "hash-1")

        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "external_validation_ok")

    def test_run_external_validation_rejects_invalid_payload(self) -> None:
        def fake_run(*, schema_json, form_json, result_json):
            result_path = Path(result_json)
            result_path.write_bytes(orjson.dumps({"valid": False, "errors": ["bad"]}))
            return 0

        with patch(
            "zopyx.surveyjs.browser.views.run_data_validation",
            side_effect=fake_run,
        ):
            result = _run_external_validation({"a": 1}, {"b": 2}, "hash-2")

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "external_validation_failed")
        self.assertEqual(result["status"], 400)

    def test_run_external_validation_errors_when_binary_fails(self) -> None:
        def fake_run(*, schema_json, form_json, result_json):
            return 1

        with patch(
            "zopyx.surveyjs.browser.views.run_data_validation",
            side_effect=fake_run,
        ):
            result = _run_external_validation({"a": 1}, {"b": 2}, "hash-3")

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "external_validator_error")
