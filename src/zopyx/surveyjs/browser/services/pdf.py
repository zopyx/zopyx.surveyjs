"""PDF import helpers for field extraction and SurveyJS conversion."""

from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess

import orjson
from zope.annotation.interfaces import IAnnotations

from ...constants import FORM_VERSIONS_KEY, PDF_FORM_KEY
from ...pdf_forms import build_surveyjs_from_pdf_fields, extract_pdf_fields
from . import forms as forms_service
from .ai import load_ai_settings


def get_pdf_form_state(context):
    """Return PDF form metadata together with the mapped SurveyJS form JSON."""
    annos = IAnnotations(context)
    pdf_form = getattr(context, "pdf_form", None)
    pdf_meta = annos.get(PDF_FORM_KEY) or {}
    field_map = pdf_meta.get("field_map") or []
    version_id = pdf_meta.get("version_id")
    form_json = {}
    if version_id and FORM_VERSIONS_KEY in annos:
        version = annos[FORM_VERSIONS_KEY].get(version_id)
        if version:
            form_json = version.get("form_json") or {}
    if not form_json:
        form_json = forms_service.latest_form_json(annos)
    return dict(
        pdf_form=pdf_form,
        form_json=form_json,
        field_map=field_map,
        version_id=version_id,
        pdf_meta=pdf_meta,
    )


def generate_survey_json_from_pdf_llm(pdf_bytes):
    """Generate SurveyJS JSON from a PDF using the optional LLM pipeline."""
    try:
        from ..ai_generator import generate_survey_json_from_image, strip_markdown_json
    except ImportError as exc:
        raise RuntimeError(f"LLM module not available: {exc}") from exc

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        pdf_path = temp_path / "uploaded.pdf"
        png_path = temp_path / "uploaded.png"

        pdf_path.write_bytes(pdf_bytes)

        command = [
            "convert",
            "-density",
            "300",
            str(pdf_path),
            "-background",
            "white",
            "-alpha",
            "remove",
            "-alpha",
            "off",
            str(png_path),
        ]
        subprocess.run(command, check=True, capture_output=True)

        image_path = png_path
        if not image_path.exists():
            candidates = sorted(temp_path.glob("uploaded*.png"))
            if not candidates:
                raise ValueError("PNG conversion failed: no output created")
            image_path = candidates[0]

        settings = load_ai_settings()

        prompt = (
            "Convert this PDF to SurveyJS JSON. Keep the layout, "
            "keep headers and footer, make JSON as close possible as possible, "
            "return the form JSON only"
        )

        survey_json_str = generate_survey_json_from_image(
            str(image_path),
            prompt,
            model_name=settings.get("model_name"),
            api_key=settings.get("api_key"),
            ollama_url=(
                settings.get("api_url")
                if settings.get("provider") == "ollama"
                else None
            ),
        )

    cleaned_json_str = strip_markdown_json(survey_json_str)
    survey_data = orjson.loads(cleaned_json_str)
    if not isinstance(survey_data, dict):
        raise ValueError("Form JSON must be an object")
    return survey_data


def extract_pdf_form_data(pdf_bytes, extract_mode, survey_title):
    """Extract form data from a PDF using field parsing or the LLM mode."""
    if extract_mode == "llm":
        survey_json = generate_survey_json_from_pdf_llm(pdf_bytes)
        field_map = []
        return survey_json, field_map

    fields = extract_pdf_fields(pdf_bytes)
    if not fields:
        raise ValueError("No fillable fields detected in this PDF.")
    survey_json, field_map = build_surveyjs_from_pdf_fields(fields, title=survey_title)
    return survey_json, field_map
