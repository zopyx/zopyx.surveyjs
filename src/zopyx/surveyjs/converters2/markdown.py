"""Markdown converter for Response objects."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from .common import format_datetime, render_markdown_table
from .types import Cell, CellType, Response


def build_markdown(response: Response) -> str:
    """Build a Markdown document for a survey response."""
    parts = [f"# Survey Response ({response.response_id})", ""]
    
    # Metadata
    if response.creator:
        parts.append(f"Created by: {response.creator}")
    if response.created:
        parts.append(f"Created on: {format_datetime(response.created)}")
    if response.creator or response.created:
        parts.append("")
    
    # Group cells by question
    table_buffer = {}
    
    for cell in sorted(response.cells, key=lambda c: c.address.to_path()):
        # Check if this is a table row
        if cell.address.row_index is not None:
            key = (cell.address.question_key, cell.address.row_index)
            if key not in table_buffer:
                table_buffer[key] = {}
            table_buffer[key][cell.address.sub_key] = str(cell.value)
            continue
        
        # Flush any pending table
        if table_buffer:
            parts.extend(_render_table_buffer(table_buffer, response))
            table_buffer = {}
        
        # Regular cell
        if cell.address.sub_key:
            # Matrix/multipletext item
            parts.append(f"**{cell.label}** ({cell.address.sub_key})")
            parts.append(f"- {cell.value}")
        else:
            # Simple field
            parts.append(f"**{cell.label}**")
            if cell.cell_type == CellType.FILE:
                parts.append(f"- {cell.display_value or cell.value}")
            else:
                parts.append(f"- {cell.value}")
        
        parts.append("")
    
    # Flush final table
    if table_buffer:
        parts.extend(_render_table_buffer(table_buffer, response))
    
    return "\n".join(parts).strip() + "\n"


def _render_table_buffer(buffer: dict, response: Response) -> List[str]:
    """Render buffered table rows as Markdown."""
    if not buffer:
        return []
    
    parts = []
    
    # Get question key
    first_key = list(buffer.keys())[0]
    question_key = first_key[0]
    
    # Get schema
    schema = response.question_schemas.get(question_key)
    
    # Get headers
    if schema and schema.columns:
        headers = [c.get("title") or c.get("name") or "" for c in schema.columns]
    else:
        all_keys = set()
        for row_data in buffer.values():
            all_keys.update(row_data.keys())
        headers = sorted(all_keys)
    
    # Build rows
    rows = []
    for idx in sorted(set(k[1] for k in buffer.keys())):
        row_data = buffer.get((question_key, idx), {})
        row = [row_data.get(h, "") for h in headers]
        rows.append(row)
    
    # Render
    title = schema.title if schema else question_key
    parts.append(f"**{title}**")
    parts.append("")
    parts.extend(render_markdown_table(headers, rows))
    parts.append("")
    
    return parts


def write_markdown(response: Response, destination: Path) -> Path:
    """Write the Markdown export to disk."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(build_markdown(response), encoding="utf-8")
    return destination
