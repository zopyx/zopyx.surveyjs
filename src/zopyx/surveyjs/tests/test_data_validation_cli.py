import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
DATA_VALIDATION_DIR = ROOT / "data-validation"
VALIDATE_SCRIPT = DATA_VALIDATION_DIR / "validate.mjs"
SURVEY_CORE_DIR = DATA_VALIDATION_DIR / "node_modules" / "survey-core"


def _pick_runner():
    node = shutil.which("node")
    if node:
        return [node, str(VALIDATE_SCRIPT)]
    bun = shutil.which("bun")
    if bun:
        return [bun, str(VALIDATE_SCRIPT)]
    return None


def _run_validation(tmp_path, form_json, schema_json="survey.json"):
    runner = _pick_runner()
    if runner is None:
        pytest.skip("No JS runtime available (node or bun required).")
    if not SURVEY_CORE_DIR.exists():
        pytest.skip("survey-core is not installed in data-validation/node_modules.")

    output_path = tmp_path / "output.json"
    cmd = runner + [
        "--schema-json",
        schema_json,
        "--form-json",
        form_json,
        "--result-json",
        str(output_path),
    ]
    completed = subprocess.run(
        cmd,
        cwd=DATA_VALIDATION_DIR,
        capture_output=True,
        text=True,
    )
    return completed, output_path


def test_validate_cli_valid(tmp_path):
    completed, output_path = _run_validation(tmp_path, "data-valid.json")

    assert completed.returncode == 0
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["valid"] is True
    assert payload["errors"] == []


def test_validate_cli_invalid(tmp_path):
    completed, output_path = _run_validation(tmp_path, "data-invalid.json")

    assert completed.returncode == 1
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["valid"] is False
    assert payload["valid"] is False


def test_validate_cli_required_field_missing(tmp_path):
    schema = {
        "title": "Required text",
        "pages": [
            {
                "name": "page1",
                "elements": [
                    {
                        "type": "text",
                        "name": "fullName",
                        "title": "Full name",
                        "isRequired": True,
                    }
                ],
            }
        ],
    }
    data = {}
    schema_path = tmp_path / "schema.json"
    data_path = tmp_path / "data.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    data_path.write_text(json.dumps(data), encoding="utf-8")

    completed, output_path = _run_validation(
        tmp_path,
        str(data_path),
        schema_json=str(schema_path),
    )

    assert completed.returncode == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["valid"] is False
    assert payload["valid"] is False


def test_validate_cli_regex_and_min_max(tmp_path):
    schema = {
        "title": "Regex and range",
        "pages": [
            {
                "name": "page1",
                "elements": [
                    {
                        "type": "text",
                        "name": "code",
                        "title": "Code",
                        "validators": [
                            {
                                "type": "regex",
                                "text": "Code must be AAA-999",
                                "regex": "^[A-Z]{3}-[0-9]{3}$",
                            }
                        ],
                    },
                    {
                        "type": "rating",
                        "name": "score",
                        "title": "Score",
                        "rateMin": 1,
                        "rateMax": 5,
                    },
                ],
            }
        ],
    }
    data = {"code": "bad", "score": 10}
    schema_path = tmp_path / "schema.json"
    data_path = tmp_path / "data.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    data_path.write_text(json.dumps(data), encoding="utf-8")

    completed, output_path = _run_validation(
        tmp_path,
        str(data_path),
        schema_json=str(schema_path),
    )

    assert completed.returncode == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["valid"] is False


def test_validate_cli_matrix_dropdown(tmp_path):
    schema = {
        "title": "Matrix dropdown",
        "pages": [
            {
                "name": "page1",
                "elements": [
                    {
                        "type": "matrixdropdown",
                        "name": "matrix",
                        "title": "Matrix",
                        "columns": [
                            {
                                "name": "quality",
                                "title": "Quality",
                                "cellType": "radiogroup",
                                "choices": ["good", "bad"],
                                "isRequired": True,
                            },
                            {
                                "name": "count",
                                "title": "Count",
                                "cellType": "text",
                                "inputType": "number",
                                "isRequired": True,
                            },
                        ],
                        "rows": ["row1", "row2"],
                    }
                ],
            }
        ],
    }
    data = {"matrix": {"row1": {"quality": "unknown", "count": 2}, "row2": {}}}
    schema_path = tmp_path / "schema.json"
    data_path = tmp_path / "data.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    data_path.write_text(json.dumps(data), encoding="utf-8")

    completed, output_path = _run_validation(
        tmp_path,
        str(data_path),
        schema_json=str(schema_path),
    )

    assert completed.returncode == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["valid"] is False


def test_validate_cli_panel_dynamic_required(tmp_path):
    schema = {
        "title": "Panel dynamic",
        "pages": [
            {
                "name": "page1",
                "elements": [
                    {
                        "type": "paneldynamic",
                        "name": "employees",
                        "title": "Employees",
                        "templateElements": [
                            {
                                "type": "text",
                                "name": "email",
                                "title": "Email",
                                "isRequired": True,
                                "inputType": "email",
                                "validators": [
                                    {
                                        "type": "email",
                                        "text": "Invalid email",
                                    }
                                ],
                            }
                        ],
                        "minPanelCount": 1,
                    }
                ],
            }
        ],
    }
    data = {"employees": [{"email": "not-an-email"}]}
    schema_path = tmp_path / "schema.json"
    data_path = tmp_path / "data.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    data_path.write_text(json.dumps(data), encoding="utf-8")

    completed, output_path = _run_validation(
        tmp_path,
        str(data_path),
        schema_json=str(schema_path),
    )

    assert completed.returncode == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["valid"] is False
