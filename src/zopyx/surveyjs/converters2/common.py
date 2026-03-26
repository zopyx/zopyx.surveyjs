"""Shared helpers for format converters."""

from __future__ import annotations

from typing import Iterable, List, Tuple

from .types import Cell, Response


def render_text_table(headers: List[str], rows: List[List[str]]) -> List[str]:
    """Render a text-aligned table for plain text outputs."""
    if not rows:
        return ["(empty)"]
    
    # Normalize all rows to have same number of columns
    col_count = len(headers)
    normalized = [headers]
    for row in rows:
        padded = list(row) + [""] * (col_count - len(row))
        normalized.append(padded)
    
    # Calculate column widths
    widths = [max(len(str(row[idx])) for row in normalized) for idx in range(col_count)]
    
    def format_row(row: List[str]) -> str:
        padded = [str(cell).ljust(widths[idx]) for idx, cell in enumerate(row)]
        return " | ".join(padded)
    
    lines = [format_row(normalized[0])]
    if len(normalized) > 1:
        separator = "-+-".join("-" * width for width in widths)
        lines.append(separator)
        for row in normalized[1:]:
            lines.append(format_row(row))
    
    return lines


def render_markdown_table(headers: List[str], rows: List[List[str]]) -> List[str]:
    """Render a Markdown table from the provided cell matrix."""
    if not rows:
        return ["(empty)"]
    
    # Ensure headers are strings (not None)
    headers = [str(h) if h is not None else "" for h in headers]
    
    col_count = len(headers)
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in range(col_count)) + " |"
    
    data_rows = []
    for row in rows:
        # Ensure all values are strings
        padded = [str(v) if v is not None else "" for v in row] + [""] * (col_count - len(row))
        data_rows.append("| " + " | ".join(padded) + " |")
    
    return [header, separator] + data_rows


def inline_html_images(html_body: str, attachment_urls: Dict[str, str]) -> str:
    """Replace attachment file references with data URLs for images."""
    updated = html_body
    for filename, data_url in attachment_urls.items():
        updated = updated.replace(f'src="{filename}"', f'src="{data_url}"')
        updated = updated.replace(f"src='{filename}'", f'src="{data_url}"')
    return updated


def wrap_html_output(html_body: str, title: str = "Survey Response") -> str:
    """Wrap HTML with minimal styling for standalone display."""
    style = """
    <style>
      :root {
        --bg: #f7f9fb;
        --panel: #ffffff;
        --border: #e0e6ed;
        --text: #1f2d3d;
        --muted: #5f6b7a;
        --accent: #2b8dd6;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        padding: 32px;
        background: var(--bg);
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        color: var(--text);
        line-height: 1.6;
      }
      .container {
        max-width: 1100px;
        margin: 0 auto;
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 28px 32px;
      }
      h1 { font-size: 28px; margin-bottom: 10px; }
      h2 { font-size: 22px; margin-top: 28px; margin-bottom: 12px; }
      h3 { font-size: 18px; margin-top: 22px; margin-bottom: 10px; }
      table {
        width: 100%;
        border-collapse: collapse;
        margin: 16px 0;
      }
      th, td {
        padding: 12px 14px;
        border: 1px solid var(--border);
        text-align: left;
      }
      th { background: #f5f7fa; }
      img {
        max-width: 100%;
        height: auto;
        display: block;
        margin: 14px 0;
        border-radius: 8px;
      }
    </style>
    """
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    {style}
</head>
<body>
    <div class="container">
        {html_body}
    </div>
</body>
</html>"""


def wrap_pdf_html(html_body: str, title: str = "Survey Response") -> str:
    """Wrap HTML with PDF-friendly styles."""
    style = """
    <style>
      @page { margin: 20mm; }
      body {
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        font-size: 10.5pt;
        line-height: 1.5;
        color: #1f2d3d;
      }
      h1 { font-size: 16pt; margin: 0 0 8px 0; }
      h2 { font-size: 13pt; margin: 20px 0 10px 0; }
      table {
        width: 100%;
        border-collapse: collapse;
        margin: 14px 0;
      }
      th, td {
        padding: 8px 10px;
        border: 1px solid #e0e6ed;
        text-align: left;
      }
      th { background: #f5f7fa; }
      img {
        max-width: 100%;
        height: auto;
        display: block;
        margin: 10px 0;
      }
    </style>
    """
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    {style}
</head>
<body>
    {html_body}
</body>
</html>"""


def format_datetime(iso_string: str) -> str:
    """Format ISO datetime to human-readable string."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y at %I:%M %p %Z")
    except (ValueError, AttributeError):
        return iso_string


def sanitize_filename(name: str) -> str:
    """Create filesystem-safe filename."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
