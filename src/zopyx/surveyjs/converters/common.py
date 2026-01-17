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


def wrap_pdf_html(
    html_body: str, creator: str | None = None, created: str | None = None
) -> str:
    """Wrap HTML with PDF-friendly styles and optional metadata."""
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
        padding: 28px;
        background: var(--bg);
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        font-size: 10.5pt;
        color: var(--text);
        line-height: 1.5;
      }
      .page {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 24px 28px;
        box-shadow: 0 10px 28px rgba(31,45,61,0.08);
      }
      h1 { font-size: 16pt; margin: 0 0 8px 0; }
      h2 { font-size: 13pt; margin: 20px 0 10px 0; }
      h3 { font-size: 11pt; margin: 14px 0 8px 0; }
      p { margin: 8px 0; color: var(--muted); }
      ul, ol { margin: 8px 0; padding-left: 18px; }
      li { margin: 4px 0; }
      table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        margin: 14px 0;
        background: #fff;
        border: 1px solid var(--border);
        border-radius: 8px;
        overflow: hidden;
      }
      th, td {
        padding: 9px 10px;
        border-bottom: 1px solid var(--border);
        text-align: left;
        color: var(--text);
      }
      th {
        background: linear-gradient(90deg, #eef5ff, #e9f1ff);
        font-weight: 600;
        color: #163256;
      }
      tr:last-child td { border-bottom: none; }
      img {
        max-width: 100%;
        height: auto;
        display: block;
        margin: 10px 0;
        border-radius: 8px;
        box-shadow: 0 8px 18px rgba(31,45,61,0.12);
      }
      code, pre {
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
        background: #0f172a;
        color: #e2e8f0;
        border-radius: 6px;
      }
      pre { padding: 10px; overflow-x: auto; }
      a { color: var(--accent); text-decoration: none; }
      a:hover { text-decoration: underline; }
      .metadata { margin: 12px 0 10px 0; color: var(--muted); font-size: 9.5pt; }
      .metadata p { margin: 4px 0; color: var(--text); }
    </style>
    """

    metadata_html = ""
    if creator or created:
        metadata_parts = []
        has_created_by = "Created by:" in html_body
        has_created_on = "Created on:" in html_body
        if creator and not has_created_by:
            metadata_parts.append(f"<p><strong>Created by:</strong> {creator}</p>")
        if created and not has_created_on:
            from datetime import datetime

            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                formatted_date = dt.strftime("%B %d, %Y at %I:%M %p %Z")
            except (ValueError, AttributeError):
                formatted_date = created
            metadata_parts.append(
                f"<p><strong>Created on:</strong> {formatted_date}</p>"
            )
        if metadata_parts:
            metadata_html = f'<div class="metadata">{"".join(metadata_parts)}</div>'

    if metadata_html:
        closing_h1 = html_body.find("</h1>")
        if closing_h1 != -1:
            insert_at = closing_h1 + len("</h1>")
            html_body = f"{html_body[:insert_at]}{metadata_html}{html_body[insert_at:]}"
        else:
            html_body = f"{metadata_html}{html_body}"

    return f'<html><head>{style}</head><body><div class="page">{html_body}</div></body></html>'


def wrap_html_output(html_body: str) -> str:
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
        --shadow: 0 10px 30px rgba(31,45,61,0.08);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        padding: 32px;
        background: radial-gradient(circle at 20% 20%, #f1f6ff, #f7f9fb 35%), radial-gradient(circle at 80% 10%, #e8f8ff, #f7f9fb 30%), var(--bg);
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
        box-shadow: var(--shadow);
        padding: 28px 32px;
      }
      h1, h2, h3 {
        color: var(--text);
        letter-spacing: 0.01em;
        margin-top: 0;
      }
      h1 { font-size: 28px; margin-bottom: 10px; }
      h2 { font-size: 22px; margin-top: 28px; margin-bottom: 12px; }
      h3 { font-size: 18px; margin-top: 22px; margin-bottom: 10px; }
      p { margin: 10px 0; color: var(--muted); }
      .meta { display: grid; grid-template-columns: 1fr; gap: 6px; margin: 12px 0 4px 0; }
      .meta-item { color: var(--muted); }
      .meta-item strong { color: var(--text); }
      ul, ol { padding-left: 24px; margin: 10px 0; }
      li { margin: 6px 0; }
      table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        margin: 16px 0;
        background: #fff;
        border: 1px solid var(--border);
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 6px 12px rgba(31,45,61,0.04);
      }
      th, td {
        padding: 12px 14px;
        border-bottom: 1px solid var(--border);
        text-align: left;
        color: var(--text);
      }
      th {
        background: linear-gradient(90deg, #eef5ff, #e9f1ff);
        font-weight: 600;
        color: #163256;
      }
      tr:last-child td { border-bottom: none; }
      img {
        max-width: 100%;
        height: auto;
        display: block;
        margin: 14px 0;
        border-radius: 10px;
        box-shadow: 0 10px 24px rgba(31,45,61,0.12);
      }
      code, pre {
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
        background: #0f172a;
        color: #e2e8f0;
        border-radius: 8px;
      }
      pre { padding: 14px; overflow-x: auto; }
      a { color: var(--accent); text-decoration: none; }
      a:hover { text-decoration: underline; }
    </style>
    """
    return f'<html><head>{style}</head><body><div class="container">{html_body}</div></body></html>'
