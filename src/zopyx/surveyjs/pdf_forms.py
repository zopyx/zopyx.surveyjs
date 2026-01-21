from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

_NAME_RE = re.compile(r"[^a-zA-Z0-9_]+")


_PDFCPU_KIND_MAP = {
    "textfield": "text",
    "datefield": "text",
    "checkbox": "checkbox",
    "radiobuttongroup": "radiogroup",
    "combobox": "dropdown",
    "listbox": "dropdown",
}


def _sanitize_name(name: str, used: set[str]) -> str:
    base = _NAME_RE.sub("_", name.strip()) if name else "field"
    base = base.strip("_") or "field"
    candidate = base
    counter = 2
    while candidate in used:
        candidate = f"{base}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def _run_pdfcpu(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("pdfcpu binary not found in PATH") from exc


def _export_pdfcpu_form_json(pdf_bytes: bytes) -> dict:
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        pdf_path = tmpdir_path / "input.pdf"
        json_path = tmpdir_path / "form.json"
        pdf_path.write_bytes(pdf_bytes)

        _run_pdfcpu(["pdfcpu", "form", "export", str(pdf_path), str(json_path)])

        if not json_path.exists():
            raise RuntimeError("pdfcpu export did not generate JSON output")
        return json.loads(json_path.read_text(encoding="utf-8"))


def _iter_pdfcpu_fields(payload: dict):
    forms = payload.get("forms") or []
    if isinstance(forms, dict):
        forms_iter = [forms]
    elif isinstance(forms, list):
        forms_iter = forms
    else:
        forms_iter = []

    for form_entry in forms_iter:
        if not isinstance(form_entry, dict):
            continue
        for field_type, entries in form_entry.items():
            if isinstance(entries, dict):
                entries_iter = [entries]
            elif isinstance(entries, list):
                entries_iter = entries
            else:
                continue
            for entry in entries_iter:
                if isinstance(entry, dict):
                    yield field_type, entry


def _extract_options(raw_options: Any) -> list[str]:
    if not raw_options:
        return []
    if isinstance(raw_options, list):
        return [str(option) for option in raw_options]
    if isinstance(raw_options, tuple):
        return [str(option) for option in raw_options]
    if isinstance(raw_options, str):
        return [part.strip() for part in raw_options.split(",") if part.strip()]
    return [str(raw_options)]


def extract_pdf_fields(pdf_bytes: bytes) -> list[dict]:
    payload = _export_pdfcpu_form_json(pdf_bytes)
    fields: list[dict] = []
    for field_type, entry in _iter_pdfcpu_fields(payload):
        name = entry.get("name") or entry.get("id")
        if not name:
            continue
        title = entry.get("label") or entry.get("altName") or name
        kind = _PDFCPU_KIND_MAP.get(field_type, "text")
        if entry.get("multiline") or entry.get("multiLine"):
            kind = "comment"
        options = _extract_options(entry.get("options"))
        fields.append(
            dict(
                name=str(name),
                title=str(title),
                kind=kind,
                options=options,
                on_value=None,
            )
        )
    return fields


def build_surveyjs_from_pdf_fields(
    fields: list[dict], title: str | None = None
) -> tuple[dict, list[dict]]:
    used_names: set[str] = set()
    elements: list[dict] = []
    field_map: list[dict] = []

    for field in fields:
        pdf_name = field["name"]
        survey_name = _sanitize_name(pdf_name, used_names)
        kind = field["kind"]
        question: dict[str, Any] = {
            "name": survey_name,
            "title": field.get("title") or pdf_name,
            "pdfFieldName": pdf_name,
        }

        if kind == "checkbox":
            question.update(
                type="boolean",
                labelTrue="Yes",
                labelFalse="No",
            )
        elif kind == "radiogroup":
            choices = field.get("options") or ["Yes", "No"]
            question.update(type="radiogroup", choices=choices)
        elif kind == "dropdown":
            choices = field.get("options") or []
            question.update(type="dropdown", choices=choices)
        elif kind == "comment":
            question.update(type="comment")
        else:
            question.update(type="text")

        elements.append(question)
        field_map.append(
            dict(
                pdf_name=pdf_name,
                survey_name=survey_name,
                kind=kind,
                on_value=field.get("on_value"),
            )
        )

    survey_json = dict(
        title=title or "PDF Form",
        pages=[dict(name="page1", elements=elements)],
    )
    return survey_json, field_map


def fill_pdf_form(pdf_bytes: bytes, data: dict, field_map: list[dict]) -> bytes:
    values: dict[str, Any] = {}
    for mapping in field_map:
        pdf_name = mapping["pdf_name"]
        survey_name = mapping["survey_name"]
        if survey_name not in data:
            continue
        value = data.get(survey_name)
        kind = mapping.get("kind")
        if kind == "checkbox":
            values[pdf_name] = "Yes" if bool(value) else "Off"
        else:
            values[pdf_name] = value

    payload = _export_pdfcpu_form_json(pdf_bytes)
    forms = payload.get("forms") or []
    if isinstance(forms, dict):
        forms_iter = [forms]
    elif isinstance(forms, list):
        forms_iter = forms
    else:
        forms_iter = []

    updated_forms: list[dict] = []
    for form_entry in forms_iter:
        if not isinstance(form_entry, dict):
            continue
        updated_entry: dict[str, Any] = {}
        for field_type, entries in form_entry.items():
            if isinstance(entries, dict):
                entries_iter = [entries]
            elif isinstance(entries, list):
                entries_iter = entries
            else:
                continue
            filtered_entries: list[dict] = []
            for entry in entries_iter:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name") or entry.get("id")
                if not name or name not in values:
                    continue
                value = values[name]
                if field_type == "checkbox":
                    entry["value"] = "Yes" if bool(value) else "Off"
                elif field_type == "listbox" and isinstance(value, list):
                    entry["values"] = [str(v) for v in value]
                else:
                    entry["value"] = "" if value is None else str(value)
                filtered_entries.append(entry)
            if filtered_entries:
                updated_entry[field_type] = filtered_entries
        if updated_entry:
            updated_forms.append(updated_entry)

    payload["forms"] = updated_forms

    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        pdf_path = tmpdir_path / "input.pdf"
        json_path = tmpdir_path / "fill.json"
        output_path = tmpdir_path / "output.pdf"
        pdf_path.write_bytes(pdf_bytes)
        json_path.write_text(json.dumps(payload), encoding="utf-8")

        _run_pdfcpu(
            ["pdfcpu", "form", "fill", str(pdf_path), str(json_path), str(output_path)]
        )

        if not output_path.exists():
            raise RuntimeError("pdfcpu did not create filled PDF output")
        return output_path.read_bytes()
