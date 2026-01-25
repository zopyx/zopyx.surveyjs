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
