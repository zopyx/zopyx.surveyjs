import argparse
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


def _deno_download_url() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        if machine in ("arm64", "aarch64"):
            return "https://github.com/denoland/deno/releases/latest/download/deno-aarch64-apple-darwin.zip"
        return "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-apple-darwin.zip"
    if system == "linux":
        if machine in ("arm64", "aarch64"):
            return "https://github.com/denoland/deno/releases/latest/download/deno-aarch64-unknown-linux-gnu.zip"
        return "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip"
    raise RuntimeError(
        f"Unsupported platform: {platform.system()} ({platform.machine()})"
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
    with urllib.request.urlopen(url) as response, open(zip_path, "wb") as handle:
        handle.write(response.read())
    with zipfile.ZipFile(zip_path) as zip_file:
        zip_file.extractall(dest_dir)
    deno_path = os.path.join(dest_dir, "deno")
    if not os.path.exists(deno_path):
        raise RuntimeError("Deno binary not found after extraction.")
    os.chmod(deno_path, os.stat(deno_path).st_mode | stat.S_IEXEC)
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
            handle.write('{"imports":{"survey-core":"npm:survey-core"}}')
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
        shutil.copy2(temp_output, target_path)
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
        ctx = multiprocessing.get_context("spawn")
        pool_size = min(len(build_targets), os.cpu_count() or 1)
        with ctx.Pool(processes=pool_size) as pool:
            built_paths = pool.map(
                _build_target, [(system, deno_path, force) for system in build_targets]
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
