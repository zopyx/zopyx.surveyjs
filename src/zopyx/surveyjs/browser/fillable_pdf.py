# -*- coding: utf-8 -*-
"""Fillable PDF generation view for surveys."""

import io
import logging
import tempfile
from pathlib import Path

import plone.api
from pypdf import PdfReader
from plone.namedfile.file import NamedBlobFile
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from .views import Views

logger = logging.getLogger(__name__)

# Try to import privacyforms_pdf, fallback to inline implementation
try:
    from privacyforms_pdf.extractor import PDFFormExtractor, PDFFormNotFoundError

    PRIVACYFORMS_PDF_AVAILABLE = True
except ImportError:
    PRIVACYFORMS_PDF_AVAILABLE = False
    logger.debug("privacyforms_pdf not available, using inline implementation")


class PDFValidationError(Exception):
    """Raised when PDF validation fails."""

    pass


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

        Uses privacyforms_pdf.PDFFormExtractor if available,
        otherwise falls back to inline implementation.
        """
        pdf = getattr(self.context, "fillable_pdf", None)
        if not pdf or not getattr(pdf, "data", None):
            return []

        try:
            if PRIVACYFORMS_PDF_AVAILABLE:
                return self._extract_fields_with_privacyforms_pdf(pdf.data)
            else:
                return self._extract_pdf_fields_inline(pdf.data)
        except Exception as e:
            logger.warning("Failed to extract PDF fields: %s", str(e))
            return []

    def _extract_fields_with_privacyforms_pdf(self, data: bytes) -> list[dict]:
        """Extract fields using privacyforms_pdf library."""
        # Write to temporary file since PDFFormExtractor expects a file path
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file.write(data)
            tmp_path = Path(tmp_file.name)

        try:
            extractor = PDFFormExtractor()
            form_data = extractor.extract(tmp_path)

            # Convert PDFField objects to simple dicts for template
            fields = []
            for field in form_data.fields:
                # Strip leading "/" from value and options
                value = field.value
                if isinstance(value, str) and value.startswith("/"):
                    value = value[1:]

                options = [
                    opt[1:] if opt.startswith("/") else opt
                    for opt in (field.options or [])
                ]

                field_dict = {
                    "name": field.name,
                    "id": field.id,
                    "type": field.field_type,
                    "value": value,
                    "pages": field.pages,
                    "page_num": field.pages[0] if field.pages else 1,
                    "locked": field.locked,
                    "options": options,
                    "readonly": False,  # Not exposed by PDFField
                    "required": False,  # Not exposed by PDFField
                }
                # Add geometry if available
                if field.geometry:
                    field_dict["geometry"] = {
                        "page": field.geometry.page,
                        "rect": field.geometry.rect,
                        "x": field.geometry.x,
                        "y": field.geometry.y,
                        "width": field.geometry.width,
                        "height": field.geometry.height,
                    }
                else:
                    field_dict["geometry"] = None

                fields.append(field_dict)

            return fields
        finally:
            # Clean up temporary file
            try:
                tmp_path.unlink()
            except Exception:
                pass

    def _extract_pdf_fields_inline(self, data: bytes) -> list[dict]:
        """Extract form field information using inline implementation.

        Fallback when privacyforms_pdf is not available.
        Based on privacyforms_pdf/extractor.py logic.
        """

        fields = []
        pdf_stream = io.BytesIO(data)
        reader = PdfReader(pdf_stream)

        # Check if PDF has a form
        pdf_fields = reader.get_fields()
        if not pdf_fields:
            return []

        # Extract widget info (pages and geometry) in one pass
        widget_info = self._extract_widgets_info_inline(reader)

        for field_counter, (field_name, field_data) in enumerate(
            pdf_fields.items(), start=1
        ):
            # Get field type
            field_type = self._get_field_type_inline(field_data)

            # Get field value
            value = self._get_field_value_inline(field_data)

            # Get info from widget scan
            info = widget_info.get(field_name, ([], None))
            pages = info[0] if info[0] else [1]
            geometry = info[1]

            # Get options for choice fields
            options = self._get_field_options_inline(field_data)

            # Build field dict
            field_info = {
                "name": field_name,
                "id": str(field_counter),
                "type": field_type,
                "value": value,
                "pages": pages,
                "page_num": pages[0] if pages else 1,
                "locked": False,
                "geometry": geometry,
                "options": options,
                "readonly": False,
                "required": False,
            }

            # Check field flags
            ff = field_data.get("/Ff", 0)
            if isinstance(ff, int):
                field_info["readonly"] = bool(ff & 1)
                field_info["required"] = bool(ff & 2)

            fields.append(field_info)

        # Sort by page number, then by name
        fields.sort(key=lambda f: (f["page_num"], f["name"]))

        return fields

    def _get_field_type_inline(self, field: dict) -> str:
        """Determine field type from pypdf field data (inline fallback)."""
        ft = field.get("/FT")
        if ft is None:
            ft = field.get("/Type")

        if ft == "/Tx":
            return "textfield"
        elif ft == "/Btn":
            if "/Opt" in field:
                return "radiobuttongroup"
            ff = field.get("/Ff", 0)
            if isinstance(ff, int) and ff & 0x8000:
                return "pushbutton"
            return "checkbox"
        elif ft == "/Ch":
            ff = field.get("/Ff", 0)
            if isinstance(ff, int) and ff & 0x40000:
                return "combobox"
            return "listbox"
        elif ft == "/Sig":
            return "signature"
        return "textfield"

    def _get_field_value_inline(self, field: dict) -> str | bool:
        """Extract value from pypdf field data (inline fallback)."""
        value = field.get("/V")
        if value is None:
            return ""
        if isinstance(value, str):
            if value.lower() in ("/yes", "yes", "/on", "on", "1"):
                return True
            elif value.lower() in ("/off", "off", "no", "0"):
                return False
            # Strip leading "/" from PDF name objects
            return value[1:] if value.startswith("/") else value
        if hasattr(value, "name"):
            name = value.name
            if name.lower() in ("/yes", "yes", "/on", "on", "1"):
                return True
            elif name.lower() in ("/off", "off", "no", "0"):
                return False
            # Strip leading "/" from PDF name objects
            return name[1:] if name.startswith("/") else name
        return str(value)

    def _strip_slash(self, value: str) -> str:
        """Strip leading "/" from PDF name objects."""
        return value[1:] if value.startswith("/") else value

    def _get_field_options_inline(self, field: dict) -> list[str]:
        """Extract options for choice/radio fields (inline fallback)."""
        options = field.get("/Opt", [])
        if options:
            result = []
            for opt in options:
                if isinstance(opt, list) and len(opt) >= 2:
                    result.append(self._strip_slash(str(opt[1])))
                elif isinstance(opt, list) and len(opt) == 1:
                    result.append(self._strip_slash(str(opt[0])))
                else:
                    result.append(self._strip_slash(str(opt)))
            return result

        kids = field.get("/Kids", [])
        if kids:
            opt_list = []
            for kid in kids:
                kid_obj = kid.get_object() if hasattr(kid, "get_object") else kid
                if kid_obj and "/AP" in kid_obj:
                    ap = kid_obj["/AP"]
                    if "/N" in ap:
                        names = list(ap["/N"].keys())
                        opt_list.extend(
                            [
                                self._strip_slash(str(n))
                                for n in names
                                if str(n).lower() != "/off"
                            ]
                        )
            return list(dict.fromkeys(opt_list))
        return []

    def _extract_widgets_info_inline(self, reader: PdfReader) -> dict:
        """Scan all pages once to find widget pages and geometry (inline fallback)."""
        info = {}

        for page_num, page in enumerate(reader.pages, start=1):
            if "/Annots" not in page:
                continue

            annots = page["/Annots"]
            for annot_ref in annots:
                try:
                    annot = (
                        annot_ref.get_object()
                        if hasattr(annot_ref, "get_object")
                        else annot_ref
                    )

                    if annot.get("/Subtype") != "/Widget":
                        continue

                    t_value = annot.get("/T")
                    if not t_value:
                        continue

                    field_name = (
                        str(t_value)
                        if isinstance(t_value, str)
                        else str(getattr(t_value, "name", t_value))
                    )

                    geometry = None
                    rect = annot.get("/Rect")
                    if rect:
                        x0, y0, x1, y1 = [float(coord) for coord in rect]
                        geometry = {
                            "page": page_num,
                            "rect": (x0, y0, x1, y1),
                            "x": x0,
                            "y": y0,
                            "width": x1 - x0,
                            "height": y1 - y0,
                        }

                    if field_name not in info:
                        info[field_name] = ([page_num], geometry)
                    else:
                        pages, existing_geom = info[field_name]
                        if page_num not in pages:
                            pages.append(page_num)
                        if existing_geom is None:
                            info[field_name] = (pages, geometry)

                except Exception:
                    pass

        return info

    def _validate_fillable_pdf(self, data: bytes) -> tuple[bool, str]:
        """Validate that the PDF contains fillable form fields.

        Uses PDFFormExtractor if available, otherwise uses inline implementation.
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
