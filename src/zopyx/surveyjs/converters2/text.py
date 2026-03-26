"""Plain text converter for Response objects."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from .common import format_datetime, render_text_table
from .types import Cell, CellType, Response


def build_text(response: Response) -> List[str]:
    """Build a list of text lines for a survey response."""
    lines: List[str] = [f"Survey Response: {response.response_id}", ""]
    
    # Metadata
    if response.creator:
        lines.append(f"Created by: {response.creator}")
    if response.created:
        lines.append(f"Created on: {format_datetime(response.created)}")
    if response.creator or response.created:
        lines.append("")
    
    # Group cells by question
    current_question = None
    table_buffer = {}
    
    for cell in sorted(response.cells, key=lambda c: c.address.to_path()):
        # Check if this is a table row
        if cell.address.row_index is not None:
            # Buffer for table rendering
            key = (cell.address.question_key, cell.address.row_index)
            if key not in table_buffer:
                table_buffer[key] = {}
            table_buffer[key][cell.address.sub_key] = str(cell.value)
            continue
        
        # Flush any pending table
        if table_buffer:
            lines.extend(_render_table_buffer(table_buffer, response))
            table_buffer = {}
        
        # Regular cell
        if cell.address.sub_key:
            # Matrix/multipletext item
            lines.append(f"{cell.label}:")
            lines.append(f"  {cell.value}")
        else:
            # Simple field
            lines.append(f"{cell.label}:")
            if cell.cell_type == CellType.FILE:
                lines.append(f"  {cell.display_value or cell.value}")
            else:
                lines.append(f"  {cell.value}")
        
        lines.append("")
    
    # Flush final table
    if table_buffer:
        lines.extend(_render_table_buffer(table_buffer, response))
    
    return lines


def _render_table_buffer(buffer: dict, response: Response) -> List[str]:
    """Render buffered table rows."""
    if not buffer:
        return []
    
    lines = []
    
    # Get question key from first entry
    first_key = list(buffer.keys())[0]
    question_key = first_key[0]
    
    # Get schema for column headers
    schema = response.question_schemas.get(question_key)
    if schema and schema.columns:
        headers = [c.get("title", c.get("name")) for c in schema.columns]
    else:
        # Use sub_keys from data
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
    lines.append(f"{schema.title if schema else question_key}:")
    lines.append("")
    for line in render_text_table(headers, rows):
        lines.append(f"  {line}")
    lines.append("")
    
    return lines


def write_text(response: Response, destination: Path) -> Path:
    """Write the plain text export to disk."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = build_text(response)
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination
