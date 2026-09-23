"""PDF converter."""

from __future__ import annotations

from pathlib import Path

from weasyprint import HTML

from .common import wrap_pdf_html
from .sanitize import sanitize_html


def write_pdf(
    html_body: str,
    destination: Path,
    creator: str | None = None,
    created: str | None = None,
) -> Path:
    """Write a PDF export, allowing only inline images from the document body."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf_body = sanitize_html(html_body, data_images_only=True)
    pdf_html = wrap_pdf_html(pdf_body, creator, created)
    HTML(string=pdf_html).write_pdf(destination)
    return destination
