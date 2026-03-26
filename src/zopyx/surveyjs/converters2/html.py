"""HTML converter for Response objects."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Dict

from markdown2 import markdown

from .common import format_datetime, inline_html_images, wrap_html_output
from .types import Attachment, CellType, Response


def build_html(response: Response, inline_images: bool = True) -> str:
    """Build HTML content for a survey response."""
    parts = []
    
    # Header
    parts.append(f"<h1>Survey Response ({escape(response.response_id)})</h1>")
    
    # Metadata
    meta_parts = []
    if response.creator:
        meta_parts.append(f"<strong>Created by:</strong> {escape(response.creator)}")
    if response.created:
        meta_parts.append(f"<strong>Created on:</strong> {escape(format_datetime(response.created))}")
    if meta_parts:
        parts.append(f'<div class="meta">{"<br>".join(meta_parts)}</div>')
    
    # Build attachment URL map
    attachment_urls = {}
    if inline_images:
        for att in response.attachments:
            if att.is_image:
                attachment_urls[att.name] = att.data_url()
    
    # Group and render cells
    table_buffer = {}
    current_question = None
    
    for cell in sorted(response.cells, key=lambda c: c.address.to_path()):
        # Check if table row
        if cell.address.row_index is not None:
            key = (cell.address.question_key, cell.address.row_index)
            if key not in table_buffer:
                table_buffer[key] = {}
            table_buffer[key][cell.address.sub_key] = str(cell.value)
            continue
        
        # Flush table
        if table_buffer:
            parts.append(_render_table_html(table_buffer, response))
            table_buffer = {}
        
        # Render cell
        if cell.address.sub_key:
            # Sub-item
            parts.append(f"<h3>{escape(cell.label)}</h3>")
            parts.append(f"<p>{escape(str(cell.value))}</p>")
        else:
            # Simple field
            parts.append(f"<h2>{escape(cell.label)}</h2>")
            if cell.cell_type == CellType.FILE:
                parts.append(f"<p>{escape(cell.display_value or str(cell.value))}</p>")
            else:
                parts.append(f"<p>{escape(str(cell.value))}</p>")
    
    # Flush final table
    if table_buffer:
        parts.append(_render_table_html(table_buffer, response))
    
    html_body = "\n".join(parts)
    
    # Inline images if requested
    if inline_images:
        html_body = inline_html_images(html_body, attachment_urls)
    
    return wrap_html_output(html_body, f"Survey Response {response.response_id}")


def _render_table_html(buffer: dict, response: Response) -> str:
    """Render buffered table as HTML."""
    if not buffer:
        return ""
    
    first_key = list(buffer.keys())[0]
    question_key = first_key[0]
    schema = response.question_schemas.get(question_key)
    
    # Headers
    if schema and schema.columns:
        headers = [c.get("title", c.get("name")) for c in schema.columns]
    else:
        all_keys = set()
        for row_data in buffer.values():
            all_keys.update(row_data.keys())
        headers = sorted(all_keys)
    
    # Build HTML
    title = schema.title if schema else question_key
    parts = [f"<h2>{escape(title)}</h2>", "<table>"]
    
    # Header row
    parts.append("<tr>" + "".join(f"<th>{escape(h)}</th>" for h in headers) + "</tr>")
    
    # Data rows
    for idx in sorted(set(k[1] for k in buffer.keys())):
        row_data = buffer.get((question_key, idx), {})
        cells = [row_data.get(h, "") for h in headers]
        parts.append("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in cells) + "</tr>")
    
    parts.append("</table>")
    return "\n".join(parts)


def write_html(response: Response, destination: Path, inline_images: bool = True) -> Path:
    """Write the HTML export to disk."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    html = build_html(response, inline_images)
    destination.write_text(html, encoding="utf-8")
    return destination
