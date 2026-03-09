"""AI-powered form generation and refinement browser view.

This module provides the AIView class, a Plone browser view that enables
AI-powered conversion of documents (PDF, DOCX, ODT, HTML) into SurveyJS form
definitions. It supports:

- Document upload and AI conversion to SurveyJS JSON
- Fillable PDF form field extraction and mapping
- Interactive form refinement via AI chat
- Version history management with undo capability
- Integration with privacyforms_ai for model abstraction

The view stores temporary form data in Zope annotations, allowing users to
iteratively refine forms before persisting them as formal versions.

Typical workflow:
    1. User uploads a document via upload_document()
    2. AI converts document to SurveyJS JSON
    3. User refines via chat_refine_temp_form() (optional)
    4. User persists via store_temp_as_version()

Dependencies:
    - privacyforms_ai: AI model abstraction layer
    - privacyforms.pdf: PDF form field extraction
    - plone.api: Plone API for portal messages and user info
    - zope.annotation: Persistent object annotations
"""

from datetime import datetime, timezone
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
from .views import Views

from privacyforms_ai import AI


class AIView(Views):
    """Browser view for AI-powered form generation and refinement (@@ai).

    This view provides methods to convert uploaded documents into SurveyJS form
    definitions using AI, with support for iterative refinement and version
    management. Temporary form data is stored in Zope annotations.

    Attributes:
        TEMP_FORM_ANNOTATION_KEY: Annotation key for temporary form JSON storage.
        TEMP_FORM_HISTORY_ANNOTATION_KEY: Annotation key for form edit history.
        TEMP_PDF_FIELD_MAPPING_ANNOTATION_KEY: Annotation key for PDF-to-survey
            field mapping metadata.
        ALLOWED_UPLOAD_EXTENSIONS: Set of supported file extensions for upload.
        MIME_TYPES: Mapping of file extensions to MIME types.
        MIME_TO_EXTENSION: Reverse mapping of MIME types to extensions.
    """

    TEMP_FORM_ANNOTATION_KEY = "zopyx.surveyjs.ai.temp_form_json"
    TEMP_FORM_HISTORY_ANNOTATION_KEY = "zopyx.surveyjs.ai.temp_form_history"
    TEMP_PDF_FIELD_MAPPING_ANNOTATION_KEY = "zopyx.surveyjs.ai.temp_pdf_field_mapping"
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
        """Convert a value to JSON-serializable format.

        Performs best-effort conversion of arbitrary Python objects to
        JSON-serializable primitives (str, int, float, bool, None, dict, list).
        Supports Pydantic models (model_dump/model_dump_json), dataclasses,
        and objects with dict()/to_dict()/json()/to_json() methods.

        Args:
            value: Any Python object to convert.

        Returns:
            JSON-serializable representation of the input value. Falls back
            to str(value) if no conversion method succeeds.
        """
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
        """Get the current temporary form JSON from annotations.

        Returns:
            dict or None: The temporary form JSON data, or None if not set.
        """
        return IAnnotations(self.context).get(self.TEMP_FORM_ANNOTATION_KEY)

    @property
    def has_temp_form(self):
        """Check if temporary form data exists.

        Returns:
            bool: True if temp_form_data is a dict, False otherwise.
        """
        return isinstance(self.temp_form_data, dict)

    @property
    def temp_form_json_pretty(self):
        """Get formatted JSON string of temporary form data.

        Returns:
            str: Pretty-printed JSON (2-space indent) or empty string
                if no temp form data exists.
        """
        data = self.temp_form_data
        if not data:
            return ""
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)

    @property
    def temp_form_history(self):
        """Get the edit history for temporary forms.

        Returns:
            list: List of history entries (dicts with 'prompt' and 'form_json'),
                or empty list if no history exists.
        """
        history = IAnnotations(self.context).get(
            self.TEMP_FORM_HISTORY_ANNOTATION_KEY, []
        )
        return history if isinstance(history, list) else []

    @property
    def has_temp_history(self):
        """Check if temporary form history exists.

        Returns:
            bool: True if history has entries, False otherwise.
        """
        return len(self.temp_form_history) > 0

    @property
    def temp_history_items(self):
        """Get formatted history items for UI display.

        Processes the raw history into a format suitable for template
        rendering, with truncated prompts and step-back indexing.

        Returns:
            list: List of dicts with keys:
                - history_index: Original index in history list
                - step_back: Number of steps back from current (1-indexed)
                - prompt: Truncated prompt text (max 160 chars)
        """
        history = self.temp_form_history
        items = []
        for idx, entry in enumerate(reversed(history)):
            original_index = len(history) - 1 - idx
            prompt = (entry.get("prompt") or "").strip()
            if len(prompt) > 160:
                prompt = prompt[:157] + "..."
            items.append(
                {
                    "history_index": original_index,
                    "step_back": idx + 1,
                    "prompt": prompt or "(no prompt)",
                }
            )
        return items

    def _redirect_ai(self, message, msg_type="info"):
        """Show a portal message and redirect to the AI view.

        Convenience method for handling form action completions with
        user feedback.

        Args:
            message: The message text to display.
            msg_type: Message type - 'info', 'warning', 'error', or 'success'.

        Returns:
            HTTPRedirectResponse: Redirect response to @@ai view.
        """
        plone.api.portal.show_message(
            message,
            request=self.request,
            type=msg_type,
        )
        return self.request.response.redirect(f"{self.context.absolute_url()}/@@ai")

    def _extract_pdf_form_data(self, pdf_bytes: bytes):
        """Extract fillable form field data from PDF bytes.

        Uses privacyforms PDF extraction to detect and extract fillable
        form fields from a PDF document. Writes bytes to a temporary file
        for processing.

        Args:
            pdf_bytes: Raw PDF file content as bytes.

        Returns:
            tuple: (has_form, form_data, error) where:
                - has_form: bool indicating if PDF has fillable fields,
                    or None if extraction failed
                - form_data: dict of extracted field data, or None if no form
                - error: str error message, or None on success
        """
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

    def _normalize_token(self, value):
        """Normalize a string for case-insensitive matching.

        Removes non-alphanumeric characters and converts to lowercase.
        Used for matching PDF field names to survey element names.

        Args:
            value: The string to normalize.

        Returns:
            str: Normalized token string (lowercase, alphanumeric only).
        """
        return "".join(ch.lower() for ch in (value or "") if ch.isalnum())

    def _collect_pdf_fields(self, data):
        """Extract candidate fillable PDF fields from arbitrary JSON-like data.

        Recursively traverses nested data structures to find field definitions,
        looking for common field identifier keys.

        Args:
            data: JSON-like data (dict, list, or primitive) from PDF extraction.

        Returns:
            list: List of field dicts with keys:
                - pdf_field_id: The field identifier/name
                - pdf_field_label: Human-readable field label
                - pdf_field_type: Field type/kind
                - geometry: Dict of geometric info (bbox, position, etc.)
        """
        fields = []
        if isinstance(data, list):
            for item in data:
                fields.extend(self._collect_pdf_fields(item))
            return fields

        if not isinstance(data, dict):
            return fields

        id_keys = (
            "name",
            "id",
            "field_name",
            "fieldName",
            "full_name",
            "qualified_name",
            "technical_name",
            "key",
        )
        label_keys = ("label", "caption", "title", "display_name", "displayName")
        type_keys = ("type", "field_type", "fieldType", "kind", "widget_type")
        geo_keys = ("bbox", "rect", "geometry", "position", "x", "y", "width", "height")

        field_id = next((data.get(k) for k in id_keys if data.get(k)), None)
        field_label = next((data.get(k) for k in label_keys if data.get(k)), None)
        field_type = next((data.get(k) for k in type_keys if data.get(k)), None)

        if field_id or field_label:
            geometry = {k: data.get(k) for k in geo_keys if k in data}
            fields.append(
                {
                    "pdf_field_id": str(field_id or ""),
                    "pdf_field_label": str(field_label or ""),
                    "pdf_field_type": str(field_type or ""),
                    "geometry": self._to_jsonable(geometry),
                }
            )

        for value in data.values():
            fields.extend(self._collect_pdf_fields(value))
        return fields

    def _collect_survey_elements(self, survey_json):
        """Flatten SurveyJS elements for mapping lookup.

        Recursively walks through SurveyJS JSON structure (pages, elements,
        rows, columns, etc.) to collect all form field definitions.

        Args:
            survey_json: SurveyJS form definition as dict.

        Returns:
            list: List of element dicts with keys:
                - survey_name: Element name attribute
                - survey_title: Element title/label
                - survey_type: Element type (text, checkbox, etc.)
        """
        elements = []

        def walk_items(items):
            if not isinstance(items, list):
                return
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "")
                title = item.get("title")
                title_text = str(title) if isinstance(title, str) else ""
                if name or title_text:
                    elements.append(
                        {
                            "survey_name": name,
                            "survey_title": title_text,
                            "survey_type": str(item.get("type") or ""),
                        }
                    )
                walk_items(item.get("elements"))
                walk_items(item.get("rows"))
                walk_items(item.get("columns"))
                walk_items(item.get("templates"))
                for cell in (
                    item.get("cells", []) if isinstance(item.get("cells"), list) else []
                ):
                    walk_items(cell)

        if isinstance(survey_json, dict):
            pages = survey_json.get("pages")
            if isinstance(pages, list):
                for page in pages:
                    if isinstance(page, dict):
                        walk_items(page.get("elements"))
            walk_items(survey_json.get("elements"))
        return elements

    def _build_pdf_to_survey_mapping(self, pdf_form_data, survey_json):
        """Create a best-effort internal map between PDF and SurveyJS fields.

        Attempts to correlate fillable PDF form fields with SurveyJS elements
        using name/label matching with normalized tokens. Confidence levels:
        - high: Direct match on ID->name or label->title
        - medium: Cross match (label->name or ID->title)
        - unmatched: No match found

        Args:
            pdf_form_data: Extracted PDF form field data (dict or list).
            survey_json: SurveyJS form definition as dict.

        Returns:
            dict: Mapping metadata with keys:
                - created: ISO timestamp of mapping creation
                - source: Always "fillable-pdf"
                - mapped_count: Number of successfully matched fields
                - pdf_field_count: Total PDF fields found
                - survey_field_count: Total survey elements found
                - mappings: List of field mapping dicts
        """
        pdf_fields = self._collect_pdf_fields(pdf_form_data)
        survey_fields = self._collect_survey_elements(survey_json)

        by_name = {}
        by_title = {}
        for field in survey_fields:
            name_key = self._normalize_token(field.get("survey_name"))
            title_key = self._normalize_token(field.get("survey_title"))
            if name_key and name_key not in by_name:
                by_name[name_key] = field
            if title_key and title_key not in by_title:
                by_title[title_key] = field

        mapped = []
        for pdf_field in pdf_fields:
            token_id = self._normalize_token(pdf_field.get("pdf_field_id"))
            token_label = self._normalize_token(pdf_field.get("pdf_field_label"))

            chosen = None
            matched_by = None
            confidence = "low"

            if token_id and token_id in by_name:
                chosen = by_name[token_id]
                matched_by = "pdf_id->survey_name"
                confidence = "high"
            elif token_label and token_label in by_title:
                chosen = by_title[token_label]
                matched_by = "pdf_label->survey_title"
                confidence = "high"
            elif token_label and token_label in by_name:
                chosen = by_name[token_label]
                matched_by = "pdf_label->survey_name"
                confidence = "medium"
            elif token_id and token_id in by_title:
                chosen = by_title[token_id]
                matched_by = "pdf_id->survey_title"
                confidence = "medium"

            mapped.append(
                {
                    "pdf_field_id": pdf_field.get("pdf_field_id"),
                    "pdf_field_label": pdf_field.get("pdf_field_label"),
                    "pdf_field_type": pdf_field.get("pdf_field_type"),
                    "pdf_geometry": pdf_field.get("geometry"),
                    "survey_name": chosen.get("survey_name") if chosen else None,
                    "survey_title": chosen.get("survey_title") if chosen else None,
                    "survey_type": chosen.get("survey_type") if chosen else None,
                    "matched_by": matched_by,
                    "confidence": confidence if chosen else "unmatched",
                }
            )

        return {
            "created": datetime.now(timezone.utc).isoformat(),
            "source": "fillable-pdf",
            "mapped_count": len([m for m in mapped if m.get("survey_name")]),
            "pdf_field_count": len(pdf_fields),
            "survey_field_count": len(survey_fields),
            "mappings": mapped,
        }

    def _clear_pdf_field_mapping(self, annos):
        """Remove PDF field mapping from annotations.

        Args:
            annos: IAnnotations object for the context.
        """
        annos.pop(self.TEMP_PDF_FIELD_MAPPING_ANNOTATION_KEY, None)

    def _prepare_ai_model(self, model_name, api_key, ollama_url):
        """Prepare and return an AI model from privacyforms_ai.

        Configures environment variables for Ollama, OpenAI, or Anthropic
        based on the model name and provided credentials, then returns
        a configured model instance.

        Args:
            model_name: Name of the AI model (e.g., 'gpt-4', 'ollama/llama2').
            api_key: API key for cloud providers (OpenAI, Anthropic).
            ollama_url: URL for Ollama server (if using Ollama).

        Returns:
            A configured AI model instance from privacyforms_ai.

        Raises:
            RuntimeError: If privacyforms_ai is not available or no model
                is configured.
        """
        if AI is None:
            raise RuntimeError("privacyforms_ai package not found")

        effective_model = model_name
        if ollama_url:
            os.environ["OLLAMA_HOST"] = ollama_url
            if effective_model and not effective_model.startswith("ollama/"):
                effective_model = f"ollama/{effective_model}"

        if api_key and not ollama_url and effective_model:
            key = (effective_model or "").lower()
            if "gpt" in key or "openai" in key:
                os.environ["OPENAI_API_KEY"] = api_key
            elif "claude" in key or "anthropic" in key:
                os.environ["ANTHROPIC_API_KEY"] = api_key

        if not effective_model:
            raise RuntimeError("No AI model configured.")

        return AI.get_model(effective_model)

    def _call_ai_conversion(
        self,
        prompt: str,
        file_path: str,
        mime_type: str,
        model_name: Optional[str],
        api_key: Optional[str],
        ollama_url: Optional[str],
    ):
        """Call AI to convert an uploaded document to SurveyJS JSON.

        Sends the document file along with a conversion prompt to the AI
        model using privacyforms_ai's attachment prompting.

        Args:
            prompt: The conversion prompt text.
            file_path: Path to the uploaded document file.
            mime_type: MIME type of the document.
            model_name: Name of the AI model to use.
            api_key: API key for authentication.
            ollama_url: Ollama server URL (optional).

        Returns:
            The AI response payload (typically JSON text).
        """
        model = self._prepare_ai_model(model_name, api_key, ollama_url)
        return AI.prompt_with_attachment(
            model=model,
            prompt=prompt,
            file_path=file_path,
            mime_type=mime_type,
        )

    def _call_ai_text_refinement(self, prompt, model_name, api_key, ollama_url):
        """Call AI for text-based form refinement.

        Sends a text-only prompt for refining existing form JSON.

        Args:
            prompt: The refinement prompt (includes current JSON + instructions).
            model_name: Name of the AI model to use.
            api_key: API key for authentication.
            ollama_url: Ollama server URL (optional).

        Returns:
            str: The AI response text containing refined JSON.
        """
        model = self._prepare_ai_model(model_name, api_key, ollama_url)
        response = model.prompt(prompt)
        return response.text() if callable(response.text) else response.text

    def _parse_generated_json(self, response_payload):
        """Parse AI response payload into a Python dict/list.

        Handles various response formats (bytes, str, dict, list) and
        attempts to extract JSON from text responses using extract_json_text.

        Args:
            response_payload: Raw AI response (bytes, str, dict, or list).

        Returns:
            dict or list: Parsed JSON data.

        Raises:
            ValueError: If the AI response is empty.
            json.JSONDecodeError: If JSON parsing fails.
        """
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
        """Handle document upload and AI conversion to SurveyJS form.

        Browser view action that processes uploaded documents (PDF, DOCX,
        ODT, HTML), optionally extracts fillable PDF form data, calls AI
        for conversion, and stores the result in temporary annotations.

        Returns:
            HTTPRedirectResponse: Redirects to @@ai view with status message.

        Raises (handled internally):
            Various exceptions during upload/AI processing are caught and
            converted to error messages.
        """
        uploaded_file = self.request.form.get("document_file")
        if not uploaded_file:
            return self._redirect_ai(
                "No file uploaded. Please upload a file.", "error"
            )

        filename = (getattr(uploaded_file, "filename", None) or "").strip()
        if not filename:
            return self._redirect_ai("Uploaded file has no filename.", "error")

        extension = Path(filename).suffix.lower()
        content_type = (
            (
                getattr(uploaded_file, "contentType", None)
                or getattr(uploaded_file, "content_type", None)
                or ""
            )
            .strip()
            .lower()
        )
        base_content_type = content_type.split(";")[0].strip() if content_type else ""

        if (
            extension not in self.ALLOWED_UPLOAD_EXTENSIONS
            and base_content_type in self.MIME_TO_EXTENSION
        ):
            extension = self.MIME_TO_EXTENSION[base_content_type]

        if extension not in self.ALLOWED_UPLOAD_EXTENSIONS:
            return self._redirect_ai(
                (
                    "Unsupported file type. Allowed file types: PDF, DOCX, ODT, HTML. "
                    f"(received extension={extension}, content-type={base_content_type or 'n/a'})"
                ),
                "error",
            )

        try:
            file_data = uploaded_file.read()
            if isinstance(file_data, str):
                file_data = file_data.encode("utf-8")
        except Exception as exc:
            return self._redirect_ai(f"Upload failed: {exc}", "error")

        size_bytes = len(file_data or b"")
        has_form = None
        form_data = None
        has_form_error = None
        if extension == ".pdf":
            has_form, form_data, has_form_error = self._extract_pdf_form_data(file_data)
        annos = IAnnotations(self.context)
        if extension != ".pdf" or has_form is not True:
            self._clear_pdf_field_mapping(annos)

        model_name, api_key, ollama_url = ai_service.load_ai_settings()
        if not model_name:
            return self._redirect_ai(
                "AI model not configured. Configure an AI model in Forms settings before using AI upload.",
                "error",
            )

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
            return self._redirect_ai(
                f"AI conversion failed: {ai_error or 'Unknown AI conversion error.'}",
                "error",
            )

        annos[self.TEMP_FORM_ANNOTATION_KEY] = generated_form
        annos[self.TEMP_FORM_HISTORY_ANNOTATION_KEY] = []
        if extension == ".pdf" and has_form is True and form_data is not None:
            annos[self.TEMP_PDF_FIELD_MAPPING_ANNOTATION_KEY] = (
                self._build_pdf_to_survey_mapping(
                    form_data,
                    generated_form,
                )
            )
        else:
            self._clear_pdf_field_mapping(annos)

        Path("form.json").write_text(
            json.dumps(generated_form, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        detail = f"AI upload succeeded for {filename} ({size_bytes} bytes)."
        if extension == ".pdf":
            if has_form is True:
                detail += " Fillable PDF form detected."
            elif has_form is False:
                detail += " No fillable PDF form detected."
            if has_form_error:
                detail += f" Form extraction note: {has_form_error}"
        return self._redirect_ai(
            detail,
            "info",
        )

    def store_temp_as_version(self):
        """Persist temporary AI form as a regular form version.

        Browser view action that converts the current temporary form
        (from AI upload/refinement) into a persisted version using the
        forms service. Clears temporary storage on success.

        Returns:
            HTTPRedirectResponse: Redirects to @@ai view with status message.
        """
        annos = IAnnotations(self.context)
        temp_form = annos.get(self.TEMP_FORM_ANNOTATION_KEY)
        if not isinstance(temp_form, dict):
            plone.api.portal.show_message(
                "No temporary AI form is available to store.",
                request=self.request,
                type="warning",
            )
            return self.request.response.redirect(
                f"{self.context.absolute_url()}/@@ai"
            )

        try:
            version_data = forms_service.save_form_version(
                annos,
                temp_form,
                plone.api.user.get_current().getId(),
                locked=False,
            )
            del annos[self.TEMP_FORM_ANNOTATION_KEY]
            annos[self.TEMP_FORM_HISTORY_ANNOTATION_KEY] = []
        except Exception as exc:
            plone.api.portal.show_message(
                f"Failed to store form version: {exc}",
                request=self.request,
                type="error",
            )
            return self.request.response.redirect(
                f"{self.context.absolute_url()}/@@ai"
            )

        plone.api.portal.show_message(
            f"Stored as new version {version_data.get('id')}.",
            request=self.request,
            type="info",
        )
        return self.request.response.redirect(f"{self.context.absolute_url()}/@@ai")

    def copy_latest_version_to_temp(self):
        """Copy latest persisted form version to temporary AI storage.

        Browser view action that loads the most recent persisted form
        version and copies it into the temporary annotation storage,
        allowing users to refine existing forms via AI.

        Returns:
            HTTPRedirectResponse: Redirects to @@ai view with status message.
        """
        annos = IAnnotations(self.context)
        versions = forms_service.sorted_form_versions(annos)
        if not versions:
            return self._redirect_ai(
                "No persisted form versions found to copy.",
                "warning",
            )

        latest = versions[-1]
        form_json = latest.get("form_json")
        if not isinstance(form_json, dict):
            return self._redirect_ai(
                "Latest version has no valid JSON object to copy.",
                "error",
            )

        annos[self.TEMP_FORM_ANNOTATION_KEY] = form_json
        annos[self.TEMP_FORM_HISTORY_ANNOTATION_KEY] = []
        return self._redirect_ai(
            f"Copied latest version {latest.get('id')} into temporary AI storage.",
            "info",
        )

    def clear_temp_storage(self):
        """Clear all temporary AI form storage.

        Browser view action that removes the temporary form JSON and
        edit history from annotations.

        Returns:
            HTTPRedirectResponse: Redirects to @@ai view with status message.
        """
        annos = IAnnotations(self.context)
        if self.TEMP_FORM_ANNOTATION_KEY in annos:
            del annos[self.TEMP_FORM_ANNOTATION_KEY]
        annos[self.TEMP_FORM_HISTORY_ANNOTATION_KEY] = []
        return self._redirect_ai("Temporary AI storage cleared.", "info")

    def chat_refine_temp_form(self):
        """Refine temporary form via AI chat interaction.

        Browser view action that takes a user prompt, sends the current
        temporary form JSON plus the prompt to AI, and stores the refined
        result. Maintains a history of up to 5 previous versions for undo.

        Returns:
            HTTPRedirectResponse: Redirects to @@ai view with status message.
        """
        prompt = (self.request.form.get("chat_prompt") or "").strip()
        if not prompt:
            return self._redirect_ai(
                "Please enter a prompt for AI refinement.", "warning"
            )

        annos = IAnnotations(self.context)
        current_form = annos.get(self.TEMP_FORM_ANNOTATION_KEY)
        if not isinstance(current_form, dict):
            return self._redirect_ai(
                "No temporary form available. Upload a document or copy latest version first.",
                "warning",
            )

        model_name, api_key, ollama_url = ai_service.load_ai_settings()
        if not model_name:
            return self._redirect_ai(
                "AI model not configured. Configure an AI model in Forms settings.",
                "error",
            )

        chat_prompt = (
            "You are a SurveyJS expert improving an existing SurveyJS JSON form.\n"
            "You receive the current form JSON and a user request.\n"
            "Apply the user request while preserving valid latest SurveyJS v2+ schema.\n"
            "Return ONLY the full updated SurveyJS JSON object.\n\n"
            "Current form JSON:\n"
            f"{json.dumps(current_form, ensure_ascii=False, default=str)}\n\n"
            "User request:\n"
            f"{prompt}\n"
        )

        try:
            ai_result_text = self._call_ai_text_refinement(
                chat_prompt,
                model_name=model_name,
                api_key=api_key,
                ollama_url=ollama_url,
            )
            refined_form = self._parse_generated_json(ai_result_text)
        except Exception as exc:
            return self._redirect_ai(f"AI refinement failed: {exc}", "error")

        history = annos.get(self.TEMP_FORM_HISTORY_ANNOTATION_KEY, [])
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "prompt": prompt,
                "form_json": current_form,
            }
        )
        if len(history) > 5:
            history = history[-5:]

        annos[self.TEMP_FORM_HISTORY_ANNOTATION_KEY] = history
        annos[self.TEMP_FORM_ANNOTATION_KEY] = refined_form
        Path("form.json").write_text(
            json.dumps(refined_form, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return self._redirect_ai("AI refinement applied to temporary form.", "info")

    def restore_temp_history_step(self):
        """Restore temporary form from history (undo functionality).

        Browser view action that restores the temporary form to a previous
        state from the edit history, discarding all changes made after
        the selected history point.

        Returns:
            HTTPRedirectResponse: Redirects to @@ai view with status message.
        """
        raw_index = self.request.form.get("history_index", "").strip()
        try:
            history_index = int(raw_index)
        except Exception:
            return self._redirect_ai("Invalid history step.", "error")

        annos = IAnnotations(self.context)
        history = annos.get(self.TEMP_FORM_HISTORY_ANNOTATION_KEY, [])
        if not isinstance(history, list) or not history:
            return self._redirect_ai("No temporary history available.", "warning")

        if history_index < 0 or history_index >= len(history):
            return self._redirect_ai("Selected history step is out of range.", "error")

        entry = history[history_index]
        previous_form = entry.get("form_json")
        if not isinstance(previous_form, dict):
            return self._redirect_ai(
                "Selected history step has no valid form JSON.", "error"
            )

        annos[self.TEMP_FORM_ANNOTATION_KEY] = previous_form
        annos[self.TEMP_FORM_HISTORY_ANNOTATION_KEY] = history[:history_index]
        return self._redirect_ai(
            f"Restored temporary form to {len(history) - history_index} step(s) back.",
            "info",
        )
