"""Python wrapper for the platform-specific validate binary.

The validate binary exposes the following CLI (see `--help`):
  --schema-json <path>
  --form-json <path>
  --result-json <path>

This module mirrors those arguments in validate_data().
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys

try:
    from .deno_build import deno_build_targets
except ImportError:  # pragma: no cover - fallback for standalone usage
    from deno_build import deno_build_targets

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCHEMA_JSON = "./survey.json"
DEFAULT_FORM_JSON = "./data-valid.json"
DEFAULT_RESULT_JSON = "output.json"

_BINARY_NAMES = {
    "darwin": "validate-mac",
    "linux": "validate-linux",
}


def _platform_key() -> str:
    system = platform.system().lower()
    if system not in _BINARY_NAMES:
        raise RuntimeError(f"Unsupported platform: {platform.system()}")
    return system


def _binary_path(system: str) -> str:
    return os.path.join(PROJECT_DIR, _BINARY_NAMES[system])


def _ensure_binary(system: str) -> str:
    path = _binary_path(system)
    if os.path.exists(path):
        return path

    built_paths = deno_build_targets([system])
    for built_path in built_paths:
        if os.path.exists(built_path):
            return built_path

    raise FileNotFoundError(f"Validation binary not found after build: {path}")


def _build_command(
    binary_path: str,
    schema_json: str,
    form_json: str,
    result_json: str,
) -> list[str]:
    return [
        binary_path,
        "--schema-json",
        schema_json,
        "--form-json",
        form_json,
        "--result-json",
        result_json,
    ]


def validate_data(
    schema_json: str = DEFAULT_SCHEMA_JSON,
    form_json: str = DEFAULT_FORM_JSON,
    result_json: str = DEFAULT_RESULT_JSON,
) -> int:
    """Run validation using the native binary for the current platform.

    Args:
        schema_json: Path to the survey schema JSON file.
        form_json: Path to the form response JSON file.
        result_json: Path to write validation results.
    Returns:
        The exit code from the validate binary (0 for success).
    """
    system = _platform_key()
    binary_path = _ensure_binary(system)
    command = _build_command(binary_path, schema_json, form_json, result_json)
    completed = subprocess.run(command, check=False)
    return completed.returncode


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate survey data using the native binary."
    )
    parser.add_argument(
        "--schema-json",
        default=DEFAULT_SCHEMA_JSON,
        help="Path to the survey schema JSON file.",
    )
    parser.add_argument(
        "--form-json",
        default=DEFAULT_FORM_JSON,
        help="Path to the form response JSON file.",
    )
    parser.add_argument(
        "--result-json",
        default=DEFAULT_RESULT_JSON,
        help="Path to write validation results.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """CLI entrypoint for uvx usage."""
    args = _parse_args(argv)
    return validate_data(
        schema_json=args.schema_json,
        form_json=args.form_json,
        result_json=args.result_json,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
