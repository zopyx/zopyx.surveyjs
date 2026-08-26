import argparse
import hashlib
import hmac
import json
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
RELEASE_MANIFEST = os.path.join(PROJECT_DIR, "deno_releases.json")
MAX_AGE_SECONDS = 5 * 24 * 60 * 60
DOWNLOAD_TIMEOUT_SECONDS = 60
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


def _release_manifest() -> dict:
    with open(RELEASE_MANIFEST, encoding="utf-8") as handle:
        manifest = json.load(handle)
    version = manifest.get("version")
    artifacts = manifest.get("artifacts")
    if not isinstance(version, str) or not artifacts:
        raise RuntimeError("Invalid Deno release manifest.")
    for key, artifact in artifacts.items():
        digest = artifact.get("sha256", "")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise RuntimeError(f"Invalid SHA256 digest for Deno artifact {key}.")
    return manifest


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


def _artifact(system: str, machine: str) -> dict:
    key = f"{system}-{_normalize_machine(machine)}"
    try:
        return _release_manifest()["artifacts"][key]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported Deno artifact: {key}") from exc


def _deno_download_url(system: str | None = None, machine: str | None = None) -> str:
    system = (system or platform.system()).lower()
    machine = machine or platform.machine()
    artifact = _artifact(system, machine)
    version = _release_manifest()["version"]
    return (
        f"https://github.com/denoland/deno/releases/download/v{version}/"
        f"{artifact['asset']}"
    )


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
    if os.path.getmtime(JS_ENTRYPOINT) > os.path.getmtime(path):
        return True
    age_seconds = time.time() - os.path.getmtime(path)
    return age_seconds > MAX_AGE_SECONDS


def _verify_deno_version(deno_path: str, expected_version: str | None = None) -> None:
    expected_version = expected_version or _release_manifest()["version"]
    completed = subprocess.run(
        [deno_path, "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
    )
    version_line = (completed.stdout + "\n" + completed.stderr).splitlines()
    actual_version = next(
        (line.split()[1] for line in version_line if line.startswith("deno ")), None
    )
    if actual_version != expected_version:
        raise RuntimeError(
            f"Deno version mismatch: expected {expected_version}, got {actual_version or 'unknown'}."
        )


def _download_deno(dest_dir: str) -> str:
    manifest = _release_manifest()
    system = platform.system().lower()
    machine = platform.machine()
    artifact = _artifact(system, machine)
    url = _deno_download_url(system, machine)
    zip_path = os.path.join(dest_dir, "deno.zip")
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response, open(
        zip_path, "wb"
    ) as handle:
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise RuntimeError("Deno download exceeds the maximum allowed size.")
            digest.update(chunk)
            handle.write(chunk)
    if not hmac.compare_digest(digest.hexdigest(), artifact["sha256"]):
        raise RuntimeError(
            f"Deno SHA256 mismatch for {artifact['asset']} (release {manifest['version']})."
        )
    with zipfile.ZipFile(zip_path) as zip_file:
        names = zip_file.namelist()
        if names != ["deno"]:
            raise RuntimeError("Unexpected contents in the Deno archive.")
        zip_file.extract("deno", dest_dir)
    deno_path = os.path.join(dest_dir, "deno")
    if not os.path.exists(deno_path):
        raise RuntimeError("Deno binary not found after extraction.")
    os.chmod(deno_path, os.stat(deno_path).st_mode | stat.S_IEXEC)
    _verify_deno_version(deno_path, manifest["version"])
    return deno_path


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
            handle.write('{"imports":{"survey-core":"npm:survey-core@^3.0.0"}}')
        temp_output = os.path.join(temp_dir, target_name)
        env = os.environ.copy()
        env["DENO_DIR"] = os.path.join(temp_dir, "deno-dir")
        compile_target = _compile_target(system, platform.machine())
        subprocess.run(
            [
                deno_path,
                "compile",
                "-A",
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
        temporary_target = f"{target_path}.tmp"
        shutil.copy2(temp_output, temporary_target)
        os.replace(temporary_target, target_path)
    return target_path


def deno_build(force: bool = False) -> str:
    system = platform.system().lower()
    with tempfile.TemporaryDirectory(prefix="deno-build-") as temp_dir:
        deno_path = _download_deno(temp_dir)
        return _build_target((system, deno_path, force))


def deno_build_targets(targets: list[str], force: bool = False) -> list[str]:
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
