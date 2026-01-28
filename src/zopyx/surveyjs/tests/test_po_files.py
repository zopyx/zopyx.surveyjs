# -*- coding: utf-8 -*-
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple
import tempfile
import unittest

import polib
import pytest


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists() or (candidate / "setup.py").exists():
            return candidate
    raise RuntimeError("Could not locate repository root from test path")


def _language_for(po_file: Path) -> str:
    parts = po_file.parts
    if "locales" in parts:
        locales_index = parts.index("locales")
        if locales_index + 1 < len(parts):
            return parts[locales_index + 1]
    return po_file.stem


def _po_files_by_language(repo_root: Path) -> Dict[str, List[Path]]:
    grouped: Dict[str, List[Path]] = defaultdict(list)
    search_root = repo_root / "src"
    if not search_root.exists():
        search_root = repo_root
    for po_file in search_root.rglob("*.po"):
        grouped[_language_for(po_file)].append(po_file)
    return {lang: sorted(files) for lang, files in grouped.items()}


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
PO_FILES_BY_LANGUAGE = _po_files_by_language(REPO_ROOT)
PO_LANGUAGE_CASES: List[Tuple[str, List[Path]]] = sorted(PO_FILES_BY_LANGUAGE.items())
PO_LANGUAGE_IDS = [language for language, _ in PO_LANGUAGE_CASES]


def _validate_po_files(language: str, po_files: List[Path], tmp_path: Path) -> None:
    assert po_files, "No .po files found for language {}".format(language)
    for po_file in po_files:
        try:
            po = polib.pofile(str(po_file))
        except Exception as exc:
            raise AssertionError("Failed to parse {}: {}".format(po_file, exc))
        mo_path = tmp_path / "{}.mo".format(po_file.stem)
        try:
            po.save_as_mofile(str(mo_path))
        except Exception as exc:
            raise AssertionError("Failed to compile {} to .mo: {}".format(po_file, exc))


@pytest.mark.parametrize(
    ("language", "po_files"), PO_LANGUAGE_CASES, ids=PO_LANGUAGE_IDS
)
def test_po_files_are_valid(
    language: str, po_files: List[Path], tmp_path: Path
) -> None:
    _validate_po_files(language, po_files, tmp_path)


class POFileTests(unittest.TestCase):
    def test_po_files_are_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for language, po_files in PO_LANGUAGE_CASES:
                with self.subTest(language=language):
                    _validate_po_files(language, po_files, tmp_path)
