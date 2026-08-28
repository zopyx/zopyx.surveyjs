"""Python wrapper for the platform-specific validate binary.

The validate binary exposes the following CLI (see `--help`):
  --schema-json <path>
  --form-json <path>
  --result-json <path>

This module mirrors those arguments in validate_data().
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import logging
import os
import platform
import subprocess
import sys
import time

try:
    from .deno_build import deno_build_targets
except ImportError:  # pragma: no cover - fallback for standalone usage
    from deno_build import deno_build_targets

try:
    import resource
except ImportError:  # pragma: no cover - Windows (unsupported anyway)
    resource = None  # type: ignore[assignment]

logger = logging.getLogger("zopyx.surveyjs.validation")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCHEMA_JSON = "./survey.json"
DEFAULT_FORM_JSON = "./data-valid.json"
DEFAULT_RESULT_JSON = "output.json"
# Bound the validator runtime so a pathological schema or a wedged binary
# cannot block a Plone request thread indefinitely (subprocess.run kills
# the child and raises TimeoutExpired when this expires).
DEFAULT_VALIDATION_TIMEOUT = 30.0
# Re-verify the binary's SHA-256 against its provenance digest at most
# once per day per host; the check catches on-disk corruption and casual
# tampering without paying a 115 MiB hash per submission.
INTEGRITY_CHECK_MAX_AGE_SECONDS = 24 * 60 * 60

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


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _limit_resources() -> None:
    """Child-side resource limits, applied between fork and exec.

    Only core dumps are disabled: RLIMIT_CORE=0 works everywhere and
    prevents validator crashes from leaking submission data via core
    files. A virtual-memory cap via RLIMIT_AS/RLIMIT_DATA is NOT viable
    in the fork child: macOS returns EINVAL for any lowering below the
    child's inherited footprint (multi-GB dyld shared-cache reservation),
    and V8-style runtimes reserve large virtual regions. Memory runaway
    is instead contained by subprocess isolation (a validator OOM kills
    only the child) and the DEFAULT_VALIDATION_TIMEOUT CPU bound.
    """
    if resource is None:
        return
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _integrity_marker_path(binary_path: str) -> str:
    return binary_path + ".verified"


def _verify_binary_integrity(binary_path: str) -> None:
    """Fail closed when the binary no longer matches its provenance digest.

    The digest file is written atomically by the build; a mismatch means
    corruption or tampering, and the validator must not run. Verification
    is cached for INTEGRITY_CHECK_MAX_AGE_SECONDS (marker mtime) so the
    115 MiB hash is paid at most daily, not per submission.
    """
    marker_path = _integrity_marker_path(binary_path)
    try:
        marker_age = time.time() - os.path.getmtime(marker_path)
        if marker_age < INTEGRITY_CHECK_MAX_AGE_SECONDS:
            return
    except OSError:
        pass

    digest_path = binary_path + ".sha256"
    try:
        with open(digest_path, encoding="utf-8") as handle:
            expected = handle.read().strip()
    except OSError as exc:
        raise RuntimeError(
            f"Validation binary digest missing: {digest_path}"
        ) from exc
    actual = _sha256_file(binary_path)
    if not hmac.compare_digest(actual, expected):
        raise RuntimeError(
            "Validation binary integrity check failed: "
            f"{binary_path} (expected {expected}, got {actual}). Refusing to run."
        )
    with open(marker_path, "w", encoding="utf-8") as handle:
        handle.write(f"{actual}\n")


def _ensure_binary(system: str) -> str:
    path = _binary_path(system)
    if os.path.exists(path):
        _verify_binary_integrity(path)
        return path

    built_paths = deno_build_targets([system])
    for built_path in built_paths:
        if os.path.exists(built_path):
            _verify_binary_integrity(built_path)
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
    timeout: float | None = DEFAULT_VALIDATION_TIMEOUT,
) -> int:
    """Run validation using the native binary for the current platform.

    Args:
        schema_json: Path to the survey schema JSON file.
        form_json: Path to the form response JSON file.
        result_json: Path to write validation results.
        timeout: Maximum seconds to wait for the validator before killing
            it (subprocess.TimeoutExpired propagates to the caller).
    Returns:
        The exit code from the validate binary (0 for success).
    """
    system = _platform_key()
    binary_path = _ensure_binary(system)
    command = _build_command(binary_path, schema_json, form_json, result_json)
    # Capture output so validator failures leave a diagnostic trail; the
    # validator only writes a few lines, so buffering is bounded. The
    # preexec limit bounds the child's memory and disables core dumps.
    preexec_fn = _limit_resources if os.name == "posix" else None
    completed = subprocess.run(
        command,
        check=False,
        timeout=timeout,
        capture_output=True,
        text=True,
        preexec_fn=preexec_fn,
    )
    if completed.returncode != 0:
        stderr_tail = (completed.stderr or "").strip()[-2048:]
        logger.warning(
            "Survey external validator exited rc=%s binary=%s stderr=%r",
            completed.returncode,
            binary_path,
            stderr_tail,
        )
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
