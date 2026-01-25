import os
import sys
import unittest
from unittest import mock


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import validate_data


class ValidateDataTests(unittest.TestCase):
    def test_validate_data_uses_existing_binary(self) -> None:
        with (
            mock.patch("validate_data.platform.system", return_value="Linux"),
            mock.patch("validate_data.os.path.exists", return_value=True),
            mock.patch("validate_data.subprocess.run") as run_mock,
            mock.patch("validate_data.deno_build_targets") as build_mock,
        ):
            run_mock.return_value = mock.Mock(returncode=0)

            exit_code = validate_data.validate_data(
                schema_json="schema.json",
                form_json="form.json",
                result_json="result.json",
            )

            self.assertEqual(exit_code, 0)
            build_mock.assert_not_called()
            run_mock.assert_called_once()
            command = run_mock.call_args[0][0]
            self.assertEqual(
                command[0],
                os.path.join(validate_data.PROJECT_DIR, "validate-linux"),
            )
            self.assertIn("--schema-json", command)
            self.assertIn("--form-json", command)
            self.assertIn("--result-json", command)

    def test_validate_data_builds_when_missing(self) -> None:
        binary_path = os.path.join(validate_data.PROJECT_DIR, "validate-linux")
        exists_responses = [False, True]

        def exists_side_effect(_: str) -> bool:
            return exists_responses.pop(0)

        with (
            mock.patch("validate_data.platform.system", return_value="Linux"),
            mock.patch("validate_data.os.path.exists", side_effect=exists_side_effect),
            mock.patch(
                "validate_data.deno_build_targets", return_value=[binary_path]
            ) as build_mock,
            mock.patch("validate_data.subprocess.run") as run_mock,
        ):
            run_mock.return_value = mock.Mock(returncode=1)

            exit_code = validate_data.validate_data()

            self.assertEqual(exit_code, 1)
            build_mock.assert_called_once_with(["linux"])
            run_mock.assert_called_once()

    def test_main_parses_args(self) -> None:
        with mock.patch("validate_data.validate_data", return_value=0) as validate_mock:
            exit_code = validate_data.main(
                [
                    "--schema-json",
                    "schema.json",
                    "--form-json",
                    "form.json",
                    "--result-json",
                    "result.json",
                ]
            )

            self.assertEqual(exit_code, 0)
            validate_mock.assert_called_once_with(
                schema_json="schema.json",
                form_json="form.json",
                result_json="result.json",
            )
