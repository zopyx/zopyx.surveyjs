from __future__ import annotations

import io
import re
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, BooleanObject, DictionaryObject, NameObject


_NAME_RE = re.compile(r"[^a-zA-Z0-9_]+")


def _clean_pdf_token(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.startswith("/"):
        return text[1:]
    return text


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


def _extract_options(raw_options: Any) -> list[str]:
    options: list[str] = []
    if not raw_options:
        return options
    for entry in raw_options:
        if isinstance(entry, (list, tuple)) and entry:
            label = entry[1] if len(entry) > 1 else entry[0]
            options.append(str(label))
        else:
            options.append(str(entry))
    return options


def _extract_on_value(field: dict) -> str:
    ap = field.get("/AP")
    if ap:
        normal = ap.get("/N")
        if hasattr(normal, "keys"):
            for key in normal.keys():
                token = _clean_pdf_token(key)
                if token and token.lower() != "off":
                    return token
    return "Yes"


def _field_kind(field: dict) -> str:
    field_type = _clean_pdf_token(field.get("/FT"))
    if field_type == "Tx":
        flags = int(field.get("/Ff", 0) or 0)
        is_multiline = bool(flags & (1 << 12))
        return "comment" if is_multiline else "text"
    if field_type == "Btn":
        flags = int(field.get("/Ff", 0) or 0)
        is_radio = bool(flags & (1 << 15))
        is_push = bool(flags & (1 << 16))
        if is_push:
            return "pushbutton"
        return "radiogroup" if is_radio else "checkbox"
    if field_type == "Ch":
        return "dropdown"
    if field_type == "Sig":
        return "text"
    return "text"


def extract_pdf_fields(pdf_bytes: bytes) -> list[dict]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    raw_fields = reader.get_fields() or {}
    fields: list[dict] = []
    for name, field in raw_fields.items():
        field_name = str(name)
        title = field.get("/TU") or field.get("/TM") or field_name
        kind = _field_kind(field)
        if kind == "pushbutton":
            continue
        options = _extract_options(field.get("/Opt"))
        on_value = _extract_on_value(field) if kind == "checkbox" else None
        fields.append(
            dict(
                name=field_name,
                title=str(title) if title is not None else field_name,
                kind=kind,
                options=options,
                on_value=on_value,
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
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)

    if "/AcroForm" in reader.trailer["/Root"]:
        writer._root_object.update(
            {NameObject("/AcroForm"): reader.trailer["/Root"]["/AcroForm"]}
        )
    if "/AcroForm" not in writer._root_object:
        writer._root_object.update(
            {
                NameObject("/AcroForm"): DictionaryObject(
                    {
                        NameObject("/Fields"): ArrayObject(),
                        NameObject("/NeedAppearances"): BooleanObject(True),
                    }
                )
            }
        )

    values: dict[str, Any] = {}
    for mapping in field_map:
        pdf_name = mapping["pdf_name"]
        survey_name = mapping["survey_name"]
        if survey_name not in data:
            continue
        value = data.get(survey_name)
        kind = mapping.get("kind")
        if kind == "checkbox":
            on_value = mapping.get("on_value") or "Yes"
            values[pdf_name] = on_value if bool(value) else "Off"
        else:
            values[pdf_name] = "" if value is None else str(value)

    for page in writer.pages:
        writer.update_page_form_field_values(page, values, auto_regenerate=True)

    writer.set_need_appearances_writer()
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
