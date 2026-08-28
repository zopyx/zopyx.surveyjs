import os
import subprocess
import sys
import tempfile
import time
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
            mock.patch("validate_data._verify_binary_integrity") as verify_mock,
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
            command = run_mock.call_args.args[0]
            self.assertEqual(
                command[0],
                os.path.join(validate_data.PROJECT_DIR, "validate-linux"),
            )
            self.assertIn("--schema-json", command)
            self.assertIn("--form-json", command)
            self.assertIn("--result-json", command)
            self.assertEqual(
                run_mock.call_args.kwargs["timeout"],
                validate_data.DEFAULT_VALIDATION_TIMEOUT,
            )
            self.assertTrue(run_mock.call_args.kwargs["capture_output"])
            self.assertTrue(run_mock.call_args.kwargs["text"])
            if os.name == "posix":
                self.assertIs(
                    run_mock.call_args.kwargs["preexec_fn"],
                    validate_data._limit_resources,
                )
            else:  # pragma: no cover - non-POSIX runtime
                self.assertIsNone(run_mock.call_args.kwargs["preexec_fn"])
            verify_mock.assert_called_once()

    def test_validate_data_timeout_propagates(self) -> None:
        # A wedged validator must raise TimeoutExpired (views map it to a
        # distinct error reason) instead of blocking the caller forever.
        with (
            mock.patch("validate_data.platform.system", return_value="Linux"),
            mock.patch("validate_data.os.path.exists", return_value=True),
            mock.patch("validate_data._verify_binary_integrity"),
            mock.patch(
                "validate_data.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="validate-mac", timeout=1),
            ),
            mock.patch("validate_data.deno_build_targets"),
            self.assertRaises(subprocess.TimeoutExpired),
        ):
            validate_data.validate_data(
                schema_json="schema.json",
                form_json="form.json",
                result_json="result.json",
            )

    def test_validate_data_builds_when_missing(self) -> None:
        binary_path = os.path.join(validate_data.PROJECT_DIR, "validate-linux")
        exists_responses = [False, True]

        def exists_side_effect(_: str) -> bool:
            return exists_responses.pop(0)

        with (
            mock.patch("validate_data.platform.system", return_value="Linux"),
            mock.patch("validate_data.os.path.exists", side_effect=exists_side_effect),
            mock.patch("validate_data._verify_binary_integrity") as verify_mock,
            mock.patch(
                "validate_data.deno_build_targets", return_value=[binary_path]
            ) as build_mock,
            mock.patch("validate_data.subprocess.run") as run_mock,
        ):
            run_mock.return_value = mock.Mock(
                returncode=1, stderr="validation failed\n", stdout=""
            )

            exit_code = validate_data.validate_data()

            self.assertEqual(exit_code, 1)
            build_mock.assert_called_once_with(["linux"])
            run_mock.assert_called_once()
            verify_mock.assert_called_once()

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

    def test_integrity_fresh_marker_skips_hashing(self) -> None:
        # A recently verified binary must not be re-hashed per submission.
        with tempfile.TemporaryDirectory() as tmpdir:
            binary = os.path.join(tmpdir, "validate-linux")
            with open(binary, "wb") as handle:
                handle.write(b"x")
            marker = validate_data._integrity_marker_path(binary)
            with open(marker, "w") as handle:
                handle.write("digest\n")
            fresh = time.time() - 60
            os.utime(marker, (fresh, fresh))

            with mock.patch("validate_data._sha256_file") as sha_mock:
                validate_data._verify_binary_integrity(binary)
            sha_mock.assert_not_called()

    def test_integrity_rechecks_and_writes_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            binary = os.path.join(tmpdir, "validate-linux")
            with open(binary, "wb") as handle:
                handle.write(b"payload")
            digest = validate_data._sha256_file(binary)
            with open(binary + ".sha256", "w") as handle:
                handle.write(digest + "\n")
            old = time.time() - 2 * validate_data.INTEGRITY_CHECK_MAX_AGE_SECONDS
            marker = validate_data._integrity_marker_path(binary)
            with open(marker, "w") as handle:
                handle.write("stale\n")
            os.utime(marker, (old, old))

            validate_data._verify_binary_integrity(binary)

            self.assertTrue(os.path.exists(marker))
            with open(marker) as handle:
                self.assertEqual(handle.read().strip(), digest)

    def test_integrity_mismatch_raises_and_writes_no_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            binary = os.path.join(tmpdir, "validate-linux")
            with open(binary, "wb") as handle:
                handle.write(b"payload")
            with open(binary + ".sha256", "w") as handle:
                handle.write("0" * 64 + "\n")

            with self.assertRaisesRegex(RuntimeError, "integrity check failed"):
                validate_data._verify_binary_integrity(binary)
            self.assertFalse(
                os.path.exists(validate_data._integrity_marker_path(binary))
            )

    def test_integrity_missing_digest_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            binary = os.path.join(tmpdir, "validate-linux")
            with open(binary, "wb") as handle:
                handle.write(b"payload")

            with self.assertRaisesRegex(RuntimeError, "digest missing"):
                validate_data._verify_binary_integrity(binary)

    @unittest.skipUnless(os.name == "posix", "resource limits are POSIX-only")
    def test_limit_resources_disables_core_dumps(self) -> None:
        with mock.patch("validate_data.resource") as res_mock:
            validate_data._limit_resources()
        res_mock.setrlimit.assert_called_once_with(res_mock.RLIMIT_CORE, (0, 0))
