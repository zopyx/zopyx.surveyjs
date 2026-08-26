import argparse
import contextlib
import fcntl
import hashlib
import hmac
import multiprocessing
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
JS_ENTRYPOINT = os.path.join(PROJECT_DIR, "validate.mjs")
MAX_AGE_SECONDS = 5 * 24 * 60 * 60

# Pinned Deno toolchain. The download URL targets an immutable release tag
# and every artifact must match the SHA-256 recorded here before it is
# extracted or executed. To bump the version: update DENO_VERSION and the
# four checksums from the official
# https://github.com/denoland/deno/releases/download/v<VERSION>/<asset>.sha256sum files.
DENO_VERSION = "2.9.5"
DENO_SHA256 = {
    "aarch64-apple-darwin": (
        "b796aadd131f6930560c1ee040cf0d6f53933fbb987464e9ff46bd7ea4830615"
    ),
    "x86_64-apple-darwin": (
        "c1b8b89a81e91b2a8b3f96def3195d08cfe3a105651da7908d53061f7140510d"
    ),
    "aarch64-unknown-linux-gnu": (
        "6b7cae3a8fc4385a59dea3146fcb8bad7fea4230e0ad36a8c692afacbc254be0"
    ),
    "x86_64-unknown-linux-gnu": (
        "8b010a3b1a4a0188a67cdb8a7a27348b2a501af78aec7fc74f2ace167368d530"
    ),
}
DENO_DOWNLOAD_TIMEOUT_SECONDS = 120

# The validator reads caller-supplied JSON inputs and writes one result file,
# so read/write must stay broad; everything else is explicitly denied. These
# flags are baked into the compiled binary and confine a potential
# survey-core escape to filesystem access only (no network exfiltration,
# no process spawning, no environment access).
COMPILE_PERMISSION_FLAGS = [
    "--allow-read",
    "--allow-write",
    "--deny-net",
    "--deny-run",
    "--deny-env",
    "--deny-ffi",
    "--no-prompt",
]

# Exact pin (no semver range) matching bun.lock so both build paths resolve
# the identical survey-core release.
SURVEY_CORE_PIN = "npm:survey-core@3.0.0"

BUILD_LOCK_PATH = os.path.join(PROJECT_DIR, ".validate-build.lock")


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextlib.contextmanager
def _build_lock():
    """Serialize builds across processes to avoid racing binary installs."""
    lock_fd = os.open(BUILD_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(lock_fd)


def _compile_target_key() -> str:
    return _compile_target(platform.system().lower(), platform.machine())


def _deno_download_url() -> str:
    target = _compile_target_key()
    return (
        f"https://github.com/denoland/deno/releases/download/"
        f"v{DENO_VERSION}/deno-{target}.zip"
    )


def _binary_name(system: str) -> str:
    if system == "darwin":
        return "validate-mac"
    if system == "linux":
        return "validate-linux"
    raise RuntimeError(f"Unsupported platform: {system}")


def _normalize_machine(machine: str) -> str:
    machine = machine.lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("arm64", "aarch64"):
        return "aarch64"
    raise RuntimeError(f"Unsupported architecture: {machine}")


def _compile_target(system: str, machine: str) -> str:
    machine = _normalize_machine(machine)
    if system == "darwin":
        return f"{machine}-apple-darwin"
    if system == "linux":
        return f"{machine}-unknown-linux-gnu"
    raise RuntimeError(f"Unsupported target system: {system}")


def _is_stale(path: str) -> bool:
    if not os.path.exists(path):
        return True
    age_seconds = time.time() - os.path.getmtime(path)
    return age_seconds > MAX_AGE_SECONDS


def _download_deno(dest_dir: str) -> str:
    url = _deno_download_url()
    zip_path = os.path.join(dest_dir, "deno.zip")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"zopyx.surveyjs-deno-build/{DENO_VERSION}"},
    )
    with urllib.request.urlopen(
        request, timeout=DENO_DOWNLOAD_TIMEOUT_SECONDS
    ) as response, open(zip_path, "wb") as handle:
        shutil.copyfileobj(response, handle)

    expected = DENO_SHA256.get(_compile_target_key())
    if expected is None:
        raise RuntimeError(
            f"No pinned checksum for Deno artifact {_compile_target_key()}"
        )
    actual = _sha256_file(zip_path)
    if not hmac.compare_digest(actual, expected):
        os.unlink(zip_path)
        raise RuntimeError(
            "Deno download failed SHA-256 verification "
            f"(expected {expected}, got {actual}). Refusing to extract."
        )

    with zipfile.ZipFile(zip_path) as zip_file:
        zip_file.extractall(dest_dir)
    deno_path = os.path.join(dest_dir, "deno")
    if not os.path.exists(deno_path):
        raise RuntimeError("Deno binary not found after extraction.")
    os.chmod(deno_path, os.stat(deno_path).st_mode | stat.S_IEXEC)
    return deno_path


def _provenance_digest_path(target_path: str) -> str:
    return target_path + ".sha256"


def _atomic_install_binary(temp_output: str, target_path: str) -> None:
    staged_binary = f"{target_path}.{os.getpid()}.staged"
    shutil.copy2(temp_output, staged_binary)
    digest = _sha256_file(staged_binary)
    staged_digest = f"{_provenance_digest_path(target_path)}.{os.getpid()}.staged"
    with open(staged_digest, "w", encoding="utf-8") as handle:
        handle.write(f"{digest}\n")
    os.chmod(staged_binary, os.stat(staged_binary).st_mode | stat.S_IEXEC)
    # Binary first, digest second: an interrupted install leaves a digest
    # mismatch (fail-closed) instead of an untracked executable.
    os.replace(staged_binary, target_path)
    os.replace(staged_digest, _provenance_digest_path(target_path))


def _build_target(args: tuple[str, str, bool]) -> str:
    system, deno_path, force = args
    target_name = _binary_name(system)
    target_path = os.path.join(PROJECT_DIR, target_name)
    if not force and not _is_stale(target_path):
        return target_path

    with tempfile.TemporaryDirectory(prefix=f"deno-build-{system}-") as temp_dir:
        temp_js = os.path.join(temp_dir, "validate.mjs")
        shutil.copy2(JS_ENTRYPOINT, temp_js)
        import_map_path = os.path.join(temp_dir, "import_map.json")
        with open(import_map_path, "w", encoding="utf-8") as handle:
            handle.write('{"imports":{"survey-core":"%s"}}' % SURVEY_CORE_PIN)
        temp_output = os.path.join(temp_dir, target_name)
        env = os.environ.copy()
        env["DENO_DIR"] = os.path.join(temp_dir, "deno-dir")
        compile_target = _compile_target(system, platform.machine())
        subprocess.run(
            [
                deno_path,
                "compile",
                *COMPILE_PERMISSION_FLAGS,
                "--no-check",
                "--import-map",
                import_map_path,
                "--target",
                compile_target,
                "--output",
                temp_output,
                temp_js,
            ],
            env=env,
            check=True,
        )
        _atomic_install_binary(temp_output, target_path)
    return target_path


def deno_build(force: bool = False) -> str:
    system = platform.system().lower()
    with _build_lock(), tempfile.TemporaryDirectory(prefix="deno-build-") as temp_dir:
        deno_path = _download_deno(temp_dir)
        return _build_target((system, deno_path, force))


def deno_build_targets(targets: list[str], force: bool = False) -> list[str]:
    with _build_lock():
        build_targets = []
        results = []
        for system in targets:
            target_name = _binary_name(system)
            target_path = os.path.join(PROJECT_DIR, target_name)
            if not force and not _is_stale(target_path):
                results.append(target_path)
            else:
                build_targets.append(system)

        if not build_targets:
            return results

        with tempfile.TemporaryDirectory(prefix="deno-build-") as temp_dir:
            deno_path = _download_deno(temp_dir)
            if len(build_targets) == 1:
                # Build single targets directly: multiprocessing spawn re-executes
                # the __main__ module, which breaks under `bin/instance run` (the
                # buildout interpreter wrapper) -- the spawned child chokes on the
                # wrapper's argv handling with a SyntaxError and the Pool respawns
                # crashed workers forever, hanging the build.
                for system in build_targets:
                    results.append(_build_target((system, deno_path, force)))
            else:
                ctx = multiprocessing.get_context("spawn")
                pool_size = min(len(build_targets), os.cpu_count() or 1)
                with ctx.Pool(processes=pool_size) as pool:
                    built_paths = pool.map(
                        _build_target,
                        [(system, deno_path, force) for system in build_targets],
                    )
                results.extend(built_paths)
        return results


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a native Deno binary for validate.mjs."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild the binary even if it is newer than 5 days.",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=("darwin", "linux", "current"),
        default=("darwin", "linux"),
        help="Targets to build (default: darwin linux).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    targets = []
    for target in args.targets:
        if target == "current":
            target = platform.system().lower()
        if target not in ("darwin", "linux"):
            raise RuntimeError(f"Unsupported target: {target}")
        if target not in targets:
            targets.append(target)

    paths = deno_build_targets(targets, force=args.force)
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
