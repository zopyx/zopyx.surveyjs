"""Shared helpers for format converters."""

from __future__ import annotations

from typing import Iterable, List, Tuple

from .types import Attachment, Item


def render_text_table(table: List[List[str]]) -> List[str]:
    """Render a text-aligned table for plain text outputs."""
    if not table:
        return ["(empty)"]
    col_count = max(len(row) for row in table)
    normalized = [row + [""] * (col_count - len(row)) for row in table]
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


def render_markdown_table(table: List[List[str]]) -> List[str]:
    """Render a Markdown table from the provided cell matrix."""
    if not table:
        return ["(empty)"]
    col_count = max(len(row) for row in table)
    normalized = [row + [""] * (col_count - len(row)) for row in table]
    header = "| " + " | ".join(normalized[0]) + " |"
    separator = "| " + " | ".join("---" for _ in range(col_count)) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in normalized[1:]]
    return [header, separator, *rows]


def build_table_rows(items: Iterable[Item]) -> List[Tuple[str, str, str, str]]:
    """Build flat rows for CSV/XLSX exports."""
    rows: List[Tuple[str, str, str, str]] = []
    for item in items:
        value = "; ".join(item.values)
        att_desc = "; ".join(
            f"{att.name} ({att.content_type or 'binary'})" for att in item.attachments
        )
        rows.append((item.key, item.label, value, att_desc))
    return rows


def inline_html_images(html_body: str, attachments: Iterable[Attachment]) -> str:
    """Replace attachment file references with data URLs for images."""
    updated = html_body
    for att in attachments:
        if not att.is_image:
            continue
        data_url = att.data_url()
        updated = updated.replace(f'src="{att.name}"', f'src="{data_url}"')
        updated = updated.replace(f"src='{att.name}'", f"src='{data_url}'")
    return updated


def wrap_pdf_html(html_body: str, creator: str | None = None, created: str | None = None) -> str:
    """Wrap HTML with PDF-friendly styles and optional metadata."""
    style = """
    <style>
      img { max-width: 75%; height: auto; display: block; margin: 0.3em 0; }
      table { border-collapse: collapse; margin: 0.4em 0; }
      th, td { border: 1px solid #ccc; padding: 0.2em 0.4em; }
      body { font-family: sans-serif; font-size: 10pt; line-height: 1.3; }
      h1 { font-size: 14pt; margin: 0.5em 0 0.3em 0; }
      h2 { font-size: 11pt; margin: 0.4em 0 0.2em 0; font-weight: 600; }
      h3 { font-size: 10pt; margin: 0.3em 0 0.2em 0; }
      p { margin: 0.2em 0; }
      ul, ol { margin: 0.2em 0; padding-left: 1.5em; }
      li { margin: 0.1em 0; }
      .metadata { margin-bottom: 0.8em; color: #666; font-size: 9pt; }
      .metadata p { margin: 0.2em 0; }
    </style>
    """

    metadata_html = ""
    if creator or created:
        metadata_parts = []
        if creator:
            metadata_parts.append(f"<p><strong>Created by:</strong> {creator}</p>")
        if created:
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                formatted_date = dt.strftime("%B %d, %Y at %I:%M %p %Z")
            except (ValueError, AttributeError):
                formatted_date = created
            metadata_parts.append(f"<p><strong>Created on:</strong> {formatted_date}</p>")
        metadata_html = f"<div class=\"metadata\">{''.join(metadata_parts)}</div>"

    return f"<html><head>{style}</head><body>{metadata_html}{html_body}</body></html>"


def wrap_html_output(html_body: str) -> str:
    """Wrap HTML with minimal styling for standalone display."""
    style = """
    <style>
      img { max-width: 1024px; height: auto; display: block; margin: 0.3em 0; }
      table { border-collapse: collapse; margin: 0.4em 0; }
      th, td { border: 1px solid #ccc; padding: 0.2em 0.4em; }
    </style>
    """
    return f"<html><head>{style}</head><body>{html_body}</body></html>"
