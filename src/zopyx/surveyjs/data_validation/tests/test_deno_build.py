import os
import sys
import unittest
from unittest import mock


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import deno_build


class DummyPool:
    def __init__(self, processes: int) -> None:
        self.processes = processes

    def __enter__(self) -> "DummyPool":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def map(self, func, iterable):
        return [func(item) for item in iterable]


class DummyContext:
    def Pool(self, processes: int) -> DummyPool:
        return DummyPool(processes)


class DenoBuildTests(unittest.TestCase):
    def test_deno_url_is_versioned_and_selects_architecture(self) -> None:
        with (
            mock.patch.object(deno_build.platform, "system", return_value="Darwin"),
            mock.patch.object(deno_build.platform, "machine", return_value="arm64"),
        ):
            url = deno_build._deno_download_url()

        self.assertIn("/releases/download/v2.9.5/", url)
        self.assertTrue(url.endswith("deno-aarch64-apple-darwin.zip"))

    def test_all_supported_artifacts_have_sha256_digests(self) -> None:
        self.assertEqual(
            set(deno_build.DENO_SHA256),
            {
                "x86_64-apple-darwin",
                "aarch64-apple-darwin",
                "x86_64-unknown-linux-gnu",
                "aarch64-unknown-linux-gnu",
            },
        )
        for digest in deno_build.DENO_SHA256.values():
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_deno_version_mismatch_is_rejected(self) -> None:
        completed = mock.Mock(stdout="deno 2.9.4\nv8 13\ntypescript 5\n", stderr="")
        with mock.patch("deno_build.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "expected 2.9.5, got 2.9.4"):
                deno_build._verify_deno_version("/tmp/deno")

    def test_normalize_machine(self) -> None:
        self.assertEqual(deno_build._normalize_machine("amd64"), "x86_64")
        self.assertEqual(deno_build._normalize_machine("x86_64"), "x86_64")
        self.assertEqual(deno_build._normalize_machine("arm64"), "aarch64")

    def test_compile_target(self) -> None:
        self.assertEqual(
            deno_build._compile_target("darwin", "arm64"), "aarch64-apple-darwin"
        )
        self.assertEqual(
            deno_build._compile_target("linux", "x86_64"),
            "x86_64-unknown-linux-gnu",
        )

    def test_deno_build_targets_parallel_path(self) -> None:
        def fake_build_target(args: tuple[str, str, bool]) -> str:
            system, _, _ = args
            return os.path.join(deno_build.PROJECT_DIR, deno_build._binary_name(system))

        with (
            mock.patch("deno_build._is_stale", return_value=True),
            mock.patch("deno_build._download_deno", return_value="/tmp/deno"),
            mock.patch(
                "deno_build.multiprocessing.get_context", return_value=DummyContext()
            ),
            mock.patch(
                "deno_build._build_target", side_effect=fake_build_target
            ) as build_mock,
        ):
            results = deno_build.deno_build_targets(["darwin", "linux"])

            expected = [
                os.path.join(deno_build.PROJECT_DIR, "validate-mac"),
                os.path.join(deno_build.PROJECT_DIR, "validate-linux"),
            ]
            self.assertCountEqual(results, expected)
            build_mock.assert_any_call(("darwin", "/tmp/deno", False))
            build_mock.assert_any_call(("linux", "/tmp/deno", False))

    def test_deno_build_targets_single_target_skips_multiprocessing(self) -> None:
        # Regression test: pre-building a single target (as done during
        # add-on install) must NOT use multiprocessing spawn -- the spawned
        # child re-executes the __main__ module, which breaks under
        # `bin/instance run` (buildout interpreter wrapper) with a SyntaxError
        # and an endless worker respawn loop that hangs the Docker build.
        def fake_build_target(args: tuple[str, str, bool]) -> str:
            system, _, _ = args
            return os.path.join(deno_build.PROJECT_DIR, deno_build._binary_name(system))

        with (
            mock.patch("deno_build._is_stale", return_value=True),
            mock.patch("deno_build._download_deno", return_value="/tmp/deno"),
            mock.patch("deno_build.multiprocessing.get_context") as ctx_mock,
            mock.patch(
                "deno_build._build_target", side_effect=fake_build_target
            ) as build_mock,
        ):
            results = deno_build.deno_build_targets(["linux"])

            self.assertEqual(
                results, [os.path.join(deno_build.PROJECT_DIR, "validate-linux")]
            )
            build_mock.assert_called_once_with(("linux", "/tmp/deno", False))
            ctx_mock.assert_not_called()
