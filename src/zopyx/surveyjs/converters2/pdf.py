"""PDF converter for Response objects."""

from __future__ import annotations

from pathlib import Path

from weasyprint import HTML

from .common import wrap_pdf_html
from .html import build_html
from .types import Response


def build_pdf_html(response: Response) -> str:
    """Build PDF-optimized HTML."""
    # Get basic HTML
    html_content = build_html(response, inline_images=True)
    
    # Extract body content
    body_start = html_content.find("<body>")
    body_end = html_content.find("</body>")
    if body_start != -1 and body_end != -1:
        body_content = html_content[body_start + 6:body_end]
    else:
        body_content = html_content
    
    # Wrap with PDF styles
    return wrap_pdf_html(body_content, f"Survey Response {response.response_id}")


def write_pdf(response: Response, destination: Path) -> Path:
    """Write a PDF export from response."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf_html = build_pdf_html(response)
    HTML(string=pdf_html).write_pdf(destination)
    return destination
