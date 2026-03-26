"""CLI and SurveyConverter for converters2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from .builder import ResponseBuilder, load_form_schema, load_response_data
from .common import sanitize_filename
from .csv_export import write_csv
from .docx_export import write_docx
from .html import write_html
from .json_export import write_json
from .markdown import write_markdown
from .pdf import write_pdf
from .text import write_text
from .types import Response
from .xlsx_export import write_xlsx
from .xml_export import write_xml


class SurveyConverter:
    """Core converter for SurveyJS data to multiple export formats (converters2)."""
    
    def __init__(self, form_schema: Dict[str, Any]):
        """Initialize with form schema.
        
        Args:
            form_schema: Parsed SurveyJS form JSON
        """
        self.builder = ResponseBuilder(form_schema)
    
    @classmethod
    def from_files(cls, form_path: Path) -> "SurveyConverter":
        """Create converter from form schema file."""
        schema = load_form_schema(form_path)
        return cls(schema)
    
    def convert(self, data: Dict[str, Any], response_id: str,
                creator: Optional[str] = None,
                created: Optional[str] = None) -> Response:
        """Convert SurveyJS data to Response object."""
        return self.builder.build_from_json(data, response_id, creator, created)
    
    def run(self, response: Response, formats: Set[str], output_dir: Path,
            csv_format: str = "wide") -> List[Path]:
        """Export Response to requested formats.
        
        Args:
            response: Response object to export
            formats: Set of format identifiers
            output_dir: Directory for output files
            csv_format: "wide" or "long" for CSV/XLSX
        
        Returns:
            List of written file paths
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_id = sanitize_filename(response.response_id)
        written: List[Path] = []
        
        if "text" in formats:
            written.append(write_text(response, output_dir / f"{safe_id}.txt"))
        
        if "md" in formats or "markdown" in formats:
            written.append(write_markdown(response, output_dir / f"{safe_id}.md"))
        
        if "html" in formats:
            written.append(write_html(response, output_dir / f"{safe_id}.html"))
        
        if "pdf" in formats:
            written.append(write_pdf(response, output_dir / f"{safe_id}.pdf"))
        
        if "csv" in formats:
            written.append(write_csv(
                response, output_dir / f"{safe_id}.csv", format=csv_format
            ))
        
        if "xlsx" in formats:
            written.append(write_xlsx(
                response, output_dir / f"{safe_id}.xlsx", format=csv_format
            ))
        
        if "xml" in formats:
            written.append(write_xml(response, output_dir / f"{safe_id}.xml"))
        
        if "docx" in formats:
            written.append(write_docx(response, output_dir / f"{safe_id}.docx"))
        
        if "json" in formats:
            written.append(write_json(response, output_dir / f"{safe_id}.json"))
        
        return written


def parse_formats(spec: str) -> Set[str]:
    """Normalize and validate requested formats."""
    allowed = {"text", "md", "markdown", "html", "pdf", "csv", "xlsx", "xml", "docx", "json"}
    
    if spec.lower() == "all":
        return {"text", "md", "html", "pdf", "csv", "xlsx", "xml", "docx", "json"}
    
    requested = {part.strip().lower() for part in spec.split(",") if part.strip()}
    
    # Normalize markdown aliases
    if "markdown" in requested:
        requested.discard("markdown")
        requested.add("md")
    
    invalid = requested - allowed
    if invalid:
        raise ValueError(f"Unknown formats: {', '.join(sorted(invalid))}")
    
    return requested or allowed


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Convert SurveyJS responses to multiple formats (converters2)"
    )
    parser.add_argument(
        "--data", required=True,
        help="Path to survey response JSON file"
    )
    parser.add_argument(
        "--form", required=True,
        help="Path to survey form schema JSON file"
    )
    parser.add_argument(
        "--output", default="./output",
        help="Output directory (default: ./output)"
    )
    parser.add_argument(
        "--formats", default="all",
        help="Comma-separated formats: text,md,html,pdf,csv,xlsx,xml,docx,json (default: all)"
    )
    parser.add_argument(
        "--csv-format", default="wide", choices=["wide", "long"],
        help="CSV/XLSX format style (default: wide)"
    )
    parser.add_argument(
        "--response-id",
        help="Response ID (default: auto-generated from data)"
    )
    
    args = parser.parse_args(argv)
    
    try:
        formats = parse_formats(args.formats)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    
    data_path = Path(args.data)
    form_path = Path(args.form_path)
    output_dir = Path(args.output)
    
    if not data_path.exists():
        print(f"Error: Data file not found: {data_path}")
        return 1
    
    if not form_path.exists():
        print(f"Error: Form file not found: {form_path}")
        return 1
    
    # Load data
    try:
        raw_data = json.loads(data_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in data file: {e}")
        return 1
    
    # Handle wrapped format
    if isinstance(raw_data, list):
        raw_data = raw_data[0] if raw_data else {}
    
    response_data = raw_data.get("result", raw_data)
    response_id = args.response_id or raw_data.get("id") or raw_data.get("poll_id") or "response"
    creator = raw_data.get("user")
    created = raw_data.get("created")
    
    # Create converter and run
    try:
        converter = SurveyConverter.from_files(form_path)
        response = converter.convert(response_data, response_id, creator, created)
        paths = converter.run(response, formats, output_dir, args.csv_format)
        
        print(f"Response ID: {response_id}")
        print("Generated files:")
        for path in paths:
            print(f"  - {path}")
        
        return 0
    except Exception as e:
        print(f"Error during conversion: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
