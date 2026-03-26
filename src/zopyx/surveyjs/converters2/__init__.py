"""SurveyJS Converters v2 - New implementation with cell-based intermediate format.

This package provides a redesigned converter system for SurveyJS that uses
a unified Cell-based intermediate format to handle all field types including
nested and dynamic content.

Example usage:
    from zopyx.surveyjs.converters2 import SurveyConverter, load_response_data
    from pathlib import Path
    
    # Load data
    converter = SurveyConverter.from_files(Path("form.json"))
    data = load_response_data(Path("response.json"))
    
    # Convert
    response = converter.convert(data, "resp-001")
    
    # Export
    from zopyx.surveyjs.converters2 import write_csv, write_pdf
    write_csv(response, Path("output.csv"))
    write_pdf(response, Path("output.pdf"))
"""

from .builder import ResponseBuilder, load_form_schema, load_response_data
from .cli import SurveyConverter, main, parse_formats
from .csv_export import CSVLongAdapter, CSVWideAdapter, write_csv, write_csv_multi
from .docx_export import write_docx
from .html import build_html, write_html
from .json_export import build_json, write_json
from .markdown import build_markdown, write_markdown
from .pdf import build_pdf_html, write_pdf
from .text import build_text, write_text
from .types import (
    Attachment,
    Cell,
    CellAddress,
    CellType,
    QuestionSchema,
    Response,
    ValueType,
)
from .xlsx_export import write_xlsx, write_xlsx_multi
from .xml_export import build_xml, write_xml

__version__ = "2.0.0"

__all__ = [
    # Core types
    "Attachment",
    "Cell",
    "CellAddress",
    "CellType",
    "QuestionSchema",
    "Response",
    "ValueType",
    
    # Builder
    "ResponseBuilder",
    "load_form_schema",
    "load_response_data",
    
    # Main converter
    "SurveyConverter",
    
    # Export functions
    "write_text",
    "write_markdown",
    "write_html",
    "write_pdf",
    "write_csv",
    "write_csv_multi",
    "write_xlsx",
    "write_xlsx_multi",
    "write_xml",
    "write_docx",
    "write_json",
    
    # Builders
    "build_text",
    "build_markdown",
    "build_html",
    "build_pdf_html",
    "build_json",
    "build_xml",
    
    # CSV adapters
    "CSVWideAdapter",
    "CSVLongAdapter",
    
    # CLI
    "parse_formats",
    "main",
]
