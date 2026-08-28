import json
import os
import sys
import tempfile
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

    def test_build_target_passes_compile_timeout(self) -> None:
        # A hung `deno compile` must not stall site setup forever: the
        # compile subprocess has an explicit upper bound.
        with (
            mock.patch("deno_build._is_stale", return_value=True),
            mock.patch("deno_build.shutil.copy2"),
            mock.patch("deno_build.open", mock.mock_open()),
            mock.patch(
                "deno_build.subprocess.run",
                return_value=mock.Mock(returncode=0),
            ) as run_mock,
            mock.patch("deno_build._atomic_install_binary"),
            mock.patch("deno_build.tempfile.TemporaryDirectory") as td_mock,
        ):
            td_mock.return_value.__enter__.return_value = "/tmp/fake-build-dir"
            deno_build._build_target(("linux", "/tmp/deno", True))

        call_kwargs = run_mock.call_args.kwargs
        self.assertEqual(
            call_kwargs["timeout"], deno_build.DENO_COMPILE_TIMEOUT_SECONDS
        )
        self.assertTrue(call_kwargs["check"])
        self.assertIn("compile", run_mock.call_args.args[0])

    def test_is_stale_uses_manifest_not_age(self) -> None:
        # Rebuild policy is deterministic: the binary is stale only when
        # validate.mjs or the pinned toolchain changed -- never on age.
        with tempfile.TemporaryDirectory() as tmpdir:
            binary = os.path.join(tmpdir, "validate-linux")
            with open(binary, "wb") as handle:
                handle.write(b"binary")

            # No manifest (pre-manifest binary or interrupted install) -> stale
            self.assertTrue(deno_build._is_stale(binary))

            manifest = {
                "deno_version": deno_build.DENO_VERSION,
                "survey_core_pin": deno_build.SURVEY_CORE_PIN,
                "js_sha256": deno_build._sha256_file(deno_build.JS_ENTRYPOINT),
            }
            with open(deno_build._manifest_path(binary), "w") as handle:
                json.dump(manifest, handle)
            self.assertFalse(deno_build._is_stale(binary))

            # Toolchain pin changed -> stale
            manifest["deno_version"] = "0.0.0"
            with open(deno_build._manifest_path(binary), "w") as handle:
                json.dump(manifest, handle)
            self.assertTrue(deno_build._is_stale(binary))

            # Corrupt manifest -> stale (fail closed)
            with open(deno_build._manifest_path(binary), "w") as handle:
                handle.write("{not json")
            self.assertTrue(deno_build._is_stale(binary))

            # Missing binary -> stale
            os.unlink(binary)
            self.assertTrue(deno_build._is_stale(binary))

    def test_atomic_install_writes_digest_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "src")
            target = os.path.join(tmpdir, "validate-linux")
            with open(source, "wb") as handle:
                handle.write(b"payload")

            deno_build._atomic_install_binary(source, target)

            with open(target + ".sha256") as handle:
                digest = handle.read().strip()
            self.assertEqual(digest, deno_build._sha256_file(target))
            with open(deno_build._manifest_path(target)) as handle:
                manifest = json.load(handle)
            self.assertEqual(manifest["deno_version"], deno_build.DENO_VERSION)
            self.assertEqual(
                manifest["survey_core_pin"], deno_build.SURVEY_CORE_PIN
            )
            self.assertEqual(
                manifest["js_sha256"],
                deno_build._sha256_file(deno_build.JS_ENTRYPOINT),
            )
            self.assertFalse(deno_build._is_stale(target))

    def test_download_deno_retries_and_fails_closed(self) -> None:
        # All attempts fail -> RuntimeError naming the attempt count, never
        # a raw socket exception leaking out of the build.
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch(
                    "deno_build._deno_download_url",
                    return_value="https://example.invalid/deno.zip",
                ),
                mock.patch(
                    "deno_build.urllib.request.urlopen",
                    side_effect=TimeoutError("read timed out"),
                ) as urlopen_mock,
                mock.patch("deno_build.time.sleep"),
            ):
                with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
                    deno_build._download_deno(tmpdir)
            self.assertEqual(urlopen_mock.call_count, deno_build.DENO_DOWNLOAD_ATTEMPTS)

    def test_download_deno_recovers_after_transient_failure(self) -> None:
        expected = deno_build.DENO_SHA256[deno_build._compile_target_key()]
        calls = {"n": 0}

        def flaky_urlopen(request, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("read timed out")
            return mock.MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch(
                    "deno_build._deno_download_url",
                    return_value="https://example.invalid/deno.zip",
                ),
                mock.patch(
                    "deno_build.urllib.request.urlopen", side_effect=flaky_urlopen
                ),
                mock.patch("deno_build.shutil.copyfileobj"),
                mock.patch("deno_build._sha256_file", return_value=expected),
                mock.patch("deno_build.zipfile.ZipFile"),
                mock.patch("deno_build.os.chmod"),
                mock.patch(
                    "deno_build.os.stat",
                    return_value=mock.Mock(st_mode=0o100644),
                ),
                mock.patch(
                    "deno_build.os.path.exists",
                    side_effect=lambda path: path == os.path.join(tmpdir, "deno"),
                ),
                mock.patch("deno_build._verify_deno_version"),
                mock.patch("deno_build.time.sleep"),
            ):
                deno_path = deno_build._download_deno(tmpdir)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(deno_path, os.path.join(tmpdir, "deno"))
