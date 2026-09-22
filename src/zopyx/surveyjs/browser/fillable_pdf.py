# -*- coding: utf-8 -*-
"""Fillable PDF generation view for surveys."""

import io
import logging
import tempfile
from pathlib import Path

import plone.api
from pypdf import PdfReader
from plone.namedfile.file import NamedBlobFile
from privacyforms_pdf.extractor import PDFFormService
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.annotation.interfaces import IAnnotations

from .views import Views
from .services import forms as forms_service

logger = logging.getLogger(__name__)

# PyMuPDF is used for PDF form filling. Import the modern ``pymupdf`` module
# name; the module stays bound as ``fitz`` for the call sites below.
try:
    import pymupdf as fitz

    PYMUPDF_AVAILABLE = True
except ImportError:  # pragma: no cover - the ``pdf`` extra is not installed
    PYMUPDF_AVAILABLE = False
    logger.debug("PyMuPDF not available, PDF filling will not work")


class FillablePDFView(Views):
    """Browser view for generating fillable PDFs from survey forms.

    This view allows users to upload a fillable PDF template and map
    form fields to PDF fields for automated PDF generation.
    """

    index = ViewPageTemplateFile("fillable_pdf.pt")

    def __call__(self):
        """Check if the feature is enabled before rendering."""
        if not self.require_feature("fillable-pdf"):
            return
        return self.index()

    def _get_latest_form_json(self) -> dict:
        """Get the latest published form JSON from versions.

        Returns:
            Form JSON dict from the latest version, or empty dict if none.
        """
        annos = IAnnotations(self.context)
        forms_service.ensure_form_versions(annos)
        return forms_service.latest_form_json(annos)

    @property
    def has_fillable_pdf(self):
        """Return True if a fillable PDF template has been uploaded."""
        pdf = getattr(self.context, "fillable_pdf", None)
        return pdf is not None and getattr(pdf, "data", None)

    @property
    def pdf_filename(self):
        """Return the filename of the uploaded PDF template."""
        pdf = getattr(self.context, "fillable_pdf", None)
        if pdf is not None:
            return getattr(pdf, "filename", None)
        return None

    @property
    def pdf_content_type(self):
        """Return the content type of the uploaded PDF template."""
        pdf = getattr(self.context, "fillable_pdf", None)
        if pdf is not None:
            return getattr(pdf, "contentType", "application/pdf")
        return "application/pdf"

    @property
    def pdf_size(self):
        """Return the size of the uploaded PDF template in bytes."""
        pdf = getattr(self.context, "fillable_pdf", None)
        if pdf is not None:
            data = getattr(pdf, "data", None)
            if data:
                return len(data)
        return 0

    @property
    def pdf_fields(self):
        """Return list of form fields from the uploaded PDF.

        Uses ``privacyforms_pdf.PDFFormService``.
        """
        pdf = getattr(self.context, "fillable_pdf", None)
        if not pdf or not getattr(pdf, "data", None):
            return []

        try:
            fields = self._extract_fields_with_privacyforms_pdf(pdf.data)

            # Add existence info for each field
            json_field_names = self._get_json_form_field_names()
            for field in fields:
                field["exists_in_json_form"] = field["name"] in json_field_names

            return fields
        except Exception as e:
            logger.warning("Failed to extract PDF fields: %s", str(e))
            return []

    def _extract_field_names_from_json(
        self, element: dict | list, names: set = None
    ) -> set:
        """Recursively extract all field names from SurveyJS JSON.

        Args:
            element: JSON element (dict or list) to traverse.
            names: Set to collect field names into.

        Returns:
            Set of field names found in the JSON.
        """
        if names is None:
            names = set()

        if isinstance(element, dict):
            # Check for 'name' key at this level
            name = element.get("name")
            if name and isinstance(name, str):
                names.add(name)

            # Recurse into elements, pages, panels
            for key in ["elements", "pages", "panels"]:
                if key in element:
                    self._extract_field_names_from_json(element[key], names)

        elif isinstance(element, list):
            for item in element:
                self._extract_field_names_from_json(item, names)

        return names

    def _get_json_form_field_names(self) -> set:
        """Get all field names from the latest published JSON form.

        Returns:
            Set of field names from the latest form version.
        """
        form_json = self._get_latest_form_json()
        if not form_json:
            return set()
        return self._extract_field_names_from_json(form_json)

    def _extract_form_properties_from_json(
        self, element: dict | list, properties: list = None
    ) -> list:
        """Recursively extract field properties from SurveyJS JSON.

        Args:
            element: JSON element (dict or list) to traverse.
            properties: List to collect field properties into.

        Returns:
            List of dicts with name, type, and inputType for each field.
        """
        if properties is None:
            properties = []

        if isinstance(element, dict):
            # Check if this is a field element with a name
            name = element.get("name")
            if name and isinstance(name, str) and element.get("type"):
                # Skip panel and page containers
                element_type = element.get("type", "")
                if element_type not in ["panel", "paneldynamic", "page"]:
                    prop = {
                        "name": name,
                        "type": element_type,
                        "inputType": element.get("inputType", "—"),
                    }
                    properties.append(prop)

            # Recurse into elements, pages, panels
            for key in ["elements", "pages", "panels"]:
                if key in element:
                    self._extract_form_properties_from_json(element[key], properties)

        elif isinstance(element, list):
            for item in element:
                self._extract_form_properties_from_json(item, properties)

        return properties

    @property
    def json_form_properties(self) -> list[dict]:
        """Return list of field properties from the latest published JSON form.

        Returns:
            List of dicts with name, type, and inputType for each form field.
        """
        form_json = self._get_latest_form_json()
        if not form_json:
            return []

        properties = self._extract_form_properties_from_json(form_json)
        # Sort by name for consistent display
        properties.sort(key=lambda p: p["name"].lower())
        return properties

    def _extract_fields_with_privacyforms_pdf(self, data: bytes) -> list[dict]:
        """Extract fields using ``privacyforms_pdf.PDFFormService``.

        The service expects a file path, so the upload is written to a
        temporary file for the duration of the extraction.
        """
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file.write(data)
            tmp_path = Path(tmp_file.name)

        try:
            form_data = PDFFormService().extract(tmp_path)

            fields = []
            for field in form_data.fields:
                layout = field.layout
                flags = field.field_flags
                page = getattr(layout, "page", None) or 1
                geometry = (
                    {
                        "page": page,
                        "x": layout.x,
                        "y": layout.y,
                        "width": layout.width,
                        "height": layout.height,
                    }
                    if layout is not None
                    else None
                )
                fields.append(
                    {
                        "name": field.name,
                        "id": field.id,
                        "type": field.type,
                        "value": field.value,
                        "pages": [page],
                        "page_num": page,
                        "locked": bool(flags.read_only) if flags else False,
                        "options": [
                            choice.text or choice.value
                            for choice in (field.choices or [])
                        ],
                        "readonly": bool(flags.read_only) if flags else False,
                        "required": bool(flags.required) if flags else False,
                        "geometry": geometry,
                    }
                )

            return fields
        finally:
            # Clean up temporary file
            try:
                tmp_path.unlink()
            except Exception:
                pass

    def _validate_fillable_pdf(self, data: bytes) -> tuple[bool, str]:
        """Validate that the PDF contains fillable form fields.

        Uses pypdf.
        """
        try:
            pdf_stream = io.BytesIO(data)
            reader = PdfReader(pdf_stream)

            if not reader.pages:
                return False, "The PDF file is empty (no pages found)."

            fields = reader.get_fields()
            if not fields:
                return False, (
                    "This PDF does not contain any fillable form fields. "
                    "Please upload a PDF with interactive form fields (AcroForm)."
                )

            field_count = len(fields)
            logger.info(
                "Fillable PDF validation passed: %d form fields found", field_count
            )
            return True, f"PDF contains {field_count} form field(s)."

        except Exception as e:
            logger.warning("PDF validation error: %s", str(e))
            return False, f"Could not parse PDF file: {str(e)}"

    def upload_pdf(self):
        """Handle PDF template upload."""
        self._check_post_authenticator()
        request = self.request

        pdf_file = request.form.get("pdf_file")
        if not pdf_file:
            plone.api.portal.show_message(
                "No file was uploaded.",
                request=request,
                type="error",
            )
            return request.response.redirect(
                f"{self.context.absolute_url()}/@@fillable-pdf"
            )

        filename = getattr(pdf_file, "filename", "")
        if not filename.lower().endswith(".pdf"):
            plone.api.portal.show_message(
                "Only PDF files are allowed.",
                request=request,
                type="error",
            )
            return request.response.redirect(
                f"{self.context.absolute_url()}/@@fillable-pdf"
            )

        try:
            if hasattr(pdf_file, "read"):
                data = pdf_file.read()
            else:
                data = pdf_file

            is_valid, message = self._validate_fillable_pdf(data)
            if not is_valid:
                plone.api.portal.show_message(
                    message,
                    request=request,
                    type="error",
                )
                return request.response.redirect(
                    f"{self.context.absolute_url()}/@@fillable-pdf"
                )

            named_file = NamedBlobFile(
                data=data,
                contentType="application/pdf",
                filename=filename,
            )
            self.context.fillable_pdf = named_file
            self.context.reindexObject()

            plone.api.portal.show_message(
                f"PDF template '{filename}' uploaded successfully.",
                request=request,
                type="info",
            )
            logger.info(
                "Fillable PDF uploaded for %s: %s (%s bytes)",
                self.context.absolute_url(),
                filename,
                len(data),
            )
        except Exception as e:
            logger.exception("Failed to upload fillable PDF")
            plone.api.portal.show_message(
                f"Failed to upload PDF: {str(e)}",
                request=request,
                type="error",
            )

        return request.response.redirect(
            f"{self.context.absolute_url()}/@@fillable-pdf"
        )

    def download_pdf(self):
        """Download the uploaded PDF template."""
        pdf = getattr(self.context, "fillable_pdf", None)
        if not pdf or not getattr(pdf, "data", None):
            self.request.response.setStatus(404)
            return "No PDF template available."

        filename = getattr(pdf, "filename", "template.pdf")
        self.request.response.setHeader("Content-Type", "application/pdf")
        self.request.response.setHeader(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        self.request.response.write(pdf.data)

    def delete_pdf(self):
        """Delete the uploaded PDF template."""
        self._check_post_authenticator()
        try:
            if hasattr(self.context, "fillable_pdf"):
                delattr(self.context, "fillable_pdf")
                self.context.reindexObject()

            plone.api.portal.show_message(
                "PDF template deleted successfully.",
                request=self.request,
                type="info",
            )
            logger.info(
                "Fillable PDF deleted for %s",
                self.context.absolute_url(),
            )
        except Exception as e:
            logger.exception("Failed to delete fillable PDF")
            plone.api.portal.show_message(
                f"Failed to delete PDF: {str(e)}",
                request=self.request,
                type="error",
            )

        return self.request.response.redirect(
            f"{self.context.absolute_url()}/@@fillable-pdf"
        )

    def _get_input_type_for_field(self, field: dict) -> str:
        """Determine the appropriate HTML input type for a PDF field.

        Args:
            field: Field dictionary with type and other properties.

        Returns:
            HTML input type ('text', 'checkbox', 'select', 'textarea', etc.)
        """
        field_type = field.get("type", "").lower()

        if field_type in ["checkbox", "radiobuttongroup"]:
            return "checkbox"
        elif field_type in ["listbox", "combobox"]:
            return "select"
        elif field_type == "signature":
            return "signature"  # Special handling
        else:
            # Default to text input
            return "text"

    @property
    def pdf_fields_with_input_types(self) -> list[dict]:
        """Return PDF fields with HTML input types for form rendering."""
        fields = self.pdf_fields
        for field in fields:
            field["input_type"] = self._get_input_type_for_field(field)
        return fields

    def fill_pdf(self):
        """Fill the PDF template with form data and return as download."""
        self._check_post_authenticator()
        request = self.request

        # Check if PyMuPDF is available
        if not PYMUPDF_AVAILABLE:
            plone.api.portal.show_message(
                "PDF filling is not available. PyMuPDF is required.",
                request=request,
                type="error",
            )
            return request.response.redirect(
                f"{self.context.absolute_url()}/@@fillable-pdf"
            )

        # Get the PDF template
        pdf = getattr(self.context, "fillable_pdf", None)
        if not pdf or not getattr(pdf, "data", None):
            plone.api.portal.show_message(
                "No PDF template available to fill.",
                request=request,
                type="error",
            )
            return request.response.redirect(
                f"{self.context.absolute_url()}/@@fillable-pdf"
            )

        try:
            # Load PDF from bytes
            pdf_bytes = pdf.data
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            # Get form data from request
            form_data = request.form

            # Log the submitted form data
            # Track filled fields
            filled_count = 0

            # Iterate through all pages and fill widgets
            for page in doc:
                for widget in page.widgets():
                    field_name = widget.field_name
                    if not field_name:
                        continue

                    # Check if we have a value for this field
                    if field_name in form_data:
                        value = form_data[field_name]

                        # Handle different field types
                        if widget.field_type_string == "Text":
                            widget.field_value = str(value) if value else ""
                            widget.update()
                            filled_count += 1

                        elif widget.field_type_string == "Checkbox":
                            # Handle checkbox values
                            if isinstance(value, str):
                                is_checked = value.lower() in ("on", "true", "yes", "1")
                            else:
                                is_checked = bool(value)

                            # For checkboxes, we need to set the on_state
                            if is_checked:
                                # Get the "On" state name (usually "Yes" or "On")
                                states = widget.button_states()
                                if states and "On" in states:
                                    widget.field_value = True
                                else:
                                    # Try to find any "on" state
                                    on_state = None
                                    for state in states or []:
                                        if state.lower() in ("yes", "on", "1"):
                                            on_state = state
                                            break
                                    if on_state:
                                        widget.field_value = True
                                    else:
                                        widget.field_value = True  # Default to True
                            else:
                                widget.field_value = False
                            widget.update()
                            filled_count += 1

                        elif widget.field_type_string in ("ComboBox", "ListBox"):
                            # Handle choice fields
                            if value:
                                widget.field_value = str(value)
                                widget.update()
                                filled_count += 1

                        else:
                            # Default handling for other types
                            if value:
                                widget.field_value = str(value)
                                widget.update()
                                filled_count += 1

            # Save to bytes
            output_bytes = doc.tobytes()
            doc.close()

            # Generate filename for download
            original_filename = getattr(pdf, "filename", "template.pdf")
            base_name = (
                original_filename.rsplit(".", 1)[0]
                if "." in original_filename
                else original_filename
            )
            download_filename = f"{base_name}_filled.pdf"

            logger.info(
                "Filled PDF for %s: %d fields filled",
                self.context.absolute_url(),
                filled_count,
            )

            # Return as download
            request.response.setHeader("Content-Type", "application/pdf")
            request.response.setHeader(
                "Content-Disposition", f'attachment; filename="{download_filename}"'
            )
            request.response.write(output_bytes)

        except Exception as e:
            logger.exception("Failed to fill PDF")
            plone.api.portal.show_message(
                f"Failed to fill PDF: {str(e)}",
                request=request,
                type="error",
            )
            return request.response.redirect(
                f"{self.context.absolute_url()}/@@fillable-pdf"
            )
