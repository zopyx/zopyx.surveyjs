import json
import os
from pathlib import Path
import tempfile
from typing import Optional

import plone.api
from zopyx.surveyjs.json_extract import NoJSONFound, extract_json_text
from zope.annotation.interfaces import IAnnotations

from .services import ai as ai_service
from .services import forms as forms_service
from .services.http import json_error, json_response
from .views import Views


class AI2View(Views):
    """Dedicated browser view for @@ai2 (beta AI features)."""

    TEMP_FORM_ANNOTATION_KEY = "zopyx.surveyjs.ai2.temp_form_json"
    ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".odt", ".html", ".htm"}
    MIME_TYPES = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".odt": "application/vnd.oasis.opendocument.text",
        ".html": "text/html",
        ".htm": "text/html",
    }
    MIME_TO_EXTENSION = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.oasis.opendocument.text": ".odt",
        "text/html": ".html",
    }

    def _to_jsonable(self, value):
        """Best-effort conversion to JSON-serializable data."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): self._to_jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._to_jsonable(v) for v in value]

        for method_name in ("model_dump", "dict", "to_dict"):
            method = getattr(value, method_name, None)
            if callable(method):
                try:
                    return self._to_jsonable(method())
                except Exception:
                    pass

        for method_name in ("model_dump_json", "json", "to_json"):
            method = getattr(value, method_name, None)
            if callable(method):
                try:
                    raw = method()
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="replace")
                    if isinstance(raw, str):
                        return self._to_jsonable(json.loads(raw))
                except Exception:
                    pass

        if hasattr(value, "__dict__"):
            try:
                return self._to_jsonable(vars(value))
            except Exception:
                pass

        return str(value)

    @property
    def temp_form_data(self):
        return IAnnotations(self.context).get(self.TEMP_FORM_ANNOTATION_KEY)

    @property
    def has_temp_form(self):
        return isinstance(self.temp_form_data, dict)

    @property
    def temp_form_json_pretty(self):
        data = self.temp_form_data
        if not data:
            return ""
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)

    def _extract_pdf_form_data(self, pdf_bytes: bytes):
        """Return (has_form, form_data, error) for a PDF upload."""
        try:
            try:
                from privacyforms.pdf import PDFFormExtractor
            except ImportError:
                from privacyforms_pdf import PDFFormExtractor
        except Exception as exc:
            return None, None, f"privacyforms PDF extractor not available: {exc}"

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                temp_path = tmp.name

            extractor = PDFFormExtractor()
            has_form = bool(extractor.has_form(temp_path))
            form_data = None
            if has_form:
                extracted = extractor.extract(temp_path)
                form_data = self._to_jsonable(extracted)
            return has_form, form_data, None
        except Exception as exc:
            return None, None, str(exc)
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _load_privacyforms_ai(self):
        try:
            from privacyforms.ai import AI  # type: ignore

            return AI
        except Exception:
            pass
        try:
            from privacyforms_ai import AI  # type: ignore

            return AI
        except Exception as exc:
            raise ImportError(
                f"privacyforms.ai integration is not available: {exc}"
            ) from exc

    def _call_ai_conversion(
        self,
        prompt: str,
        file_path: str,
        mime_type: str,
        model_name: Optional[str],
        api_key: Optional[str],
        ollama_url: Optional[str],
    ):
        """Call AI via privacyforms.ai helper methods only."""
        AI = self._load_privacyforms_ai()

        effective_model = model_name
        if ollama_url:
            os.environ["OLLAMA_HOST"] = ollama_url
            if effective_model and not effective_model.startswith("ollama/"):
                effective_model = f"ollama/{effective_model}"

        if api_key and not ollama_url and effective_model:
            key = effective_model.lower()
            if "gpt" in key or "openai" in key:
                os.environ["OPENAI_API_KEY"] = api_key
            elif "claude" in key or "anthropic" in key:
                os.environ["ANTHROPIC_API_KEY"] = api_key

        if not effective_model:
            raise RuntimeError("No AI model configured.")

        model = AI.get_model(effective_model)
        return AI.prompt_with_attachment(model, prompt, file_path, mime_type)

    def _parse_generated_json(self, response_payload):
        if isinstance(response_payload, bytes):
            response_text = response_payload.decode("utf-8", errors="replace").strip()
        elif isinstance(response_payload, str):
            response_text = response_payload.strip()
        elif isinstance(response_payload, (dict, list)):
            return response_payload
        else:
            response_text = str(response_payload).strip()

        if not response_text:
            raise ValueError("AI response is empty.")

        try:
            extracted = extract_json_text(response_text)
            return json.loads(extracted)
        except (NoJSONFound, json.JSONDecodeError):
            return json.loads(response_text)

    def upload_document(self):
        """Upload endpoint for AI2 document conversion to SurveyJS via AI."""
        uploaded_file = self.request.form.get("document_file")
        if not uploaded_file:
            json_error(
                self.request.response,
                400,
                "No file uploaded",
                message="Please upload a file.",
            )
            return

        filename = (getattr(uploaded_file, "filename", None) or "").strip()
        if not filename:
            json_error(
                self.request.response,
                400,
                "Missing filename",
                message="Uploaded file has no filename.",
            )
            return

        extension = Path(filename).suffix.lower()
        content_type = (
            getattr(uploaded_file, "contentType", None)
            or getattr(uploaded_file, "content_type", None)
            or ""
        ).strip().lower()
        base_content_type = content_type.split(";")[0].strip() if content_type else ""

        if extension not in self.ALLOWED_UPLOAD_EXTENSIONS and base_content_type in self.MIME_TO_EXTENSION:
            extension = self.MIME_TO_EXTENSION[base_content_type]

        if extension not in self.ALLOWED_UPLOAD_EXTENSIONS:
            json_error(
                self.request.response,
                400,
                "Unsupported file type",
                message=(
                    "Allowed file types: PDF, DOCX, ODT, HTML"
                ),
                extra={
                    "received_extension": extension,
                    "received_content_type": base_content_type,
                },
            )
            return

        try:
            file_data = uploaded_file.read()
            if isinstance(file_data, str):
                file_data = file_data.encode("utf-8")
        except Exception as exc:
            json_error(
                self.request.response,
                400,
                "Upload failed",
                message=str(exc),
            )
            return

        size_bytes = len(file_data or b"")
        has_form = None
        form_data = None
        has_form_error = None
        if extension == ".pdf":
            has_form, form_data, has_form_error = self._extract_pdf_form_data(file_data)

        model_name, api_key, ollama_url = ai_service.load_ai_settings()
        if not model_name:
            json_error(
                self.request.response,
                400,
                "AI model not configured",
                message="Configure an AI model in Forms settings before using AI2 upload.",
            )
            return

        prompt = """
You are a SurveyJS expert specialized in converting business documents and fillable PDFs into high-quality SurveyJS form definitions.

Task:
- Convert the uploaded document into a valid SurveyJS form JSON object.
- Return ONLY JSON (no markdown, no explanations, no code fences).

Requirements:
0) Version compatibility
- The output MUST follow the latest SurveyJS v2+ JSON schema conventions.
- Do not use deprecated or invalid question types/properties for current SurveyJS.
- Ensure the JSON can be loaded by modern SurveyJS Creator/Form Library without schema errors.

1) SurveyJS quality
- Use proper SurveyJS structure (`title`, `description`, `pages`, `elements`).
- Use suitable element types (`text`, `comment`, `radiogroup`, `checkbox`, `dropdown`, `boolean`, `number`, `matrix`, `panel`, `multipletext`).
- For date input, use current SurveyJS-compatible representation (for example `type: "text"` with date-oriented settings such as `inputType`), not obsolete types.
- Use clear field names and readable titles.
- Add required validation where obvious from labels/context.

2) Layout fidelity
- Preserve or imitate the original layout as far as possible.
- Keep grouping/sections/order from the source document.
- If source has rows/columns, mimic this with `panel`, `paneldynamic`, `multipletext`, or matrix-like structures where appropriate.
- Goal: produce a visually and structurally familiar, nice form.

3) Extracted PDF form metadata (when provided)
- You may receive extracted fillable-PDF metadata as JSON.
- This metadata can contain field-level details such as:
  - technical id/name
  - field type/kind
  - label/caption
  - value/default
  - required flags/options
  - geometry/bounding box/position (x, y, width, height)
  - page number and ordering hints
- Use these metadata attributes to map source fields to SurveyJS elements as accurately as possible.
- Use geometry/page/order hints to maintain relative placement and section flow.

4) Output constraints
- Output must be a single valid JSON object parseable by standard JSON parsers.
- Do not include comments or trailing commas.
- Do not include text outside the JSON object.
""".strip()
        if form_data is not None:
            prompt += (
                "\n\nHere is optional extracted form metadata JSON from the source PDF:\n"
                + json.dumps(form_data, ensure_ascii=False, default=str)
            )
        print(prompt)

        generated_form = None
        ai_error = None
        try:
            with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as tmp:
                tmp.write(file_data)
                tmp_path = tmp.name
            try:
                ai_result = self._call_ai_conversion(
                    prompt=prompt,
                    file_path=tmp_path,
                    mime_type=self.MIME_TYPES.get(
                        extension, "application/octet-stream"
                    ),
                    model_name=model_name,
                    api_key=api_key,
                    ollama_url=ollama_url,
                )
                generated_form = self._parse_generated_json(ai_result)
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except Exception as exc:
            ai_error = str(exc)

        if generated_form is None:
            json_error(
                self.request.response,
                500,
                "AI conversion failed",
                message=ai_error or "Unknown AI conversion error.",
            )
            return

        annos = IAnnotations(self.context)
        annos[self.TEMP_FORM_ANNOTATION_KEY] = generated_form

        Path("form.json").write_text(
            json.dumps(generated_form, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(json.dumps(generated_form, indent=2, ensure_ascii=False, default=str))

        json_response(
            self.request.response,
            {
                "success": True,
                "message": "Document processed and converted by configured AI provider.",
                "filename": filename,
                "extension": extension,
                "size_bytes": size_bytes,
                "has_form": has_form,
                "form_data_extracted": bool(form_data) if has_form else False,
                "has_form_error": has_form_error,
                "temp_form_stored": True,
                "temp_form_annotation_key": self.TEMP_FORM_ANNOTATION_KEY,
                "generated_form": generated_form,
            },
        )

    def store_temp_as_version(self):
        """Persist temporary AI2 form JSON as a regular form version."""
        annos = IAnnotations(self.context)
        temp_form = annos.get(self.TEMP_FORM_ANNOTATION_KEY)
        if not isinstance(temp_form, dict):
            plone.api.portal.show_message(
                "No temporary AI2 form is available to store.",
                request=self.request,
                type="warning",
            )
            return self.request.response.redirect(f"{self.context.absolute_url()}/@@ai2")

        try:
            version_data = forms_service.save_form_version(
                annos,
                temp_form,
                plone.api.user.get_current().getId(),
                locked=False,
            )
            del annos[self.TEMP_FORM_ANNOTATION_KEY]
        except Exception as exc:
            plone.api.portal.show_message(
                f"Failed to store form version: {exc}",
                request=self.request,
                type="error",
            )
            return self.request.response.redirect(f"{self.context.absolute_url()}/@@ai2")

        plone.api.portal.show_message(
            f"Stored as new version {version_data.get('id')}.",
            request=self.request,
            type="info",
        )
        return self.request.response.redirect(f"{self.context.absolute_url()}/@@ai2")
