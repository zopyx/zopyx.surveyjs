"""PDF converter."""

from __future__ import annotations

from pathlib import Path

from weasyprint import HTML

from .common import wrap_pdf_html


def write_pdf(
    html_body: str,
    destination: Path,
    creator: str | None = None,
    created: str | None = None,
) -> Path:
    """Write a PDF export from HTML content."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf_html = wrap_pdf_html(html_body, creator, created)
    HTML(string=pdf_html).write_pdf(destination)
    return destination
