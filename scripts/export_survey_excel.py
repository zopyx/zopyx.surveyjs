#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "openpyxl>=3.1.3",
# ]
# ///
"""Standalone SurveyJS Excel exporter using the tabular export model."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "src" / "zopyx" / "surveyjs" / "converters" / "tabular_export.py"
SPEC = importlib.util.spec_from_file_location("surveyjs_tabular_export", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load exporter module from {MODULE_PATH}")
tabular_export = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tabular_export
SPEC.loader.exec_module(tabular_export)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--form", required=True, help="Path to the SurveyJS form JSON")
    parser.add_argument("--result", required=True, help="Path to the survey result JSON")
    parser.add_argument(
        "--output",
        help="Destination .xlsx path. Defaults to <result-stem>.xlsx next to the result file.",
    )
    parser.add_argument(
        "--survey-id",
        help="Optional stable survey identifier to place into the export metadata.",
    )
    parser.add_argument(
        "--csv-dir",
        help="Optional directory for the CSV bundle with responses_wide, answers_long, attachments, and schema.",
    )
    parser.add_argument(
        "--canonical-json",
        help="Optional path for the canonical typed JSON payload.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    form_path = Path(args.form)
    result_path = Path(args.result)
    output_path = Path(args.output) if args.output else result_path.with_suffix(".xlsx")

    form_payload = tabular_export.load_json_document(form_path)
    result_payload = tabular_export.load_json_document(result_path)
    bundle = tabular_export.build_tabular_export(
        form_payload,
        result_payload,
        survey_id=args.survey_id,
    )

    workbook_path = tabular_export.write_excel_bundle(bundle, output_path)
    print(f"Wrote workbook: {workbook_path}")

    if args.csv_dir:
        csv_dir = tabular_export.write_csv_bundle(bundle, args.csv_dir)
        print(f"Wrote CSV bundle: {csv_dir}")

    if args.canonical_json:
        canonical_path = tabular_export.write_canonical_json(bundle, args.canonical_json)
        print(f"Wrote canonical JSON: {canonical_path}")


if __name__ == "__main__":
    main()
