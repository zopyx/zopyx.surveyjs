"""JSON converter for Response objects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .types import Cell, CellType, Response


def build_json(response: Response, include_metadata: bool = True) -> str:
    """Build a JSON document for the survey response.
    
    Reconstructs the original nested structure from flat cells.
    """
    result: Dict[str, Any] = {
        "response_id": response.response_id
    }
    
    if include_metadata:
        result["_metadata"] = {
            "created": response.created,
            "modified": response.modified,
            "creator": response.creator
        }
    
    # Group cells by question
    by_question = {}
    for cell in response.cells:
        key = cell.address.question_key
        if key not in by_question:
            by_question[key] = []
        by_question[key].append(cell)
    
    # Reconstruct each question's value
    data = {}
    for question_key, cells in by_question.items():
        schema = response.question_schemas.get(question_key)
        data[question_key] = _reconstruct_value(cells, schema)
    
    result["data"] = data
    
    # Add attachments metadata
    if response.attachments:
        result["attachments"] = [
            {
                "id": att.attachment_id,
                "name": att.name,
                "field": att.field_key,
                "content_type": att.content_type,
                "is_image": att.is_image
            }
            for att in response.attachments
        ]
    
    return json.dumps(result, ensure_ascii=False, indent=2) + "\n"


def _reconstruct_value(cells: List[Cell], schema) -> Any:
    """Reconstruct original value from cells."""
    if not cells:
        return None
    
    # Check if all cells are scalar (simple value)
    if len(cells) == 1 and cells[0].address.sub_key is None and cells[0].address.row_index is None:
        return cells[0].value
    
    # Check if matrix (sub_keys but no row_index)
    if all(c.address.row_index is None for c in cells):
        result = {}
        for c in cells:
            if c.address.sub_key:
                result[c.address.sub_key] = c.value
            else:
                return c.value
        return result
    
    # Table/panel with row_index
    by_row = {}
    for c in cells:
        idx = c.address.row_index or 0
        if idx not in by_row:
            by_row[idx] = {}
        by_row[idx][c.address.sub_key or "value"] = c.value
    
    return [by_row[i] for i in sorted(by_row.keys())]


def write_json(response: Response, destination: Path, 
               include_metadata: bool = True) -> Path:
    """Write the JSON export to disk."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        build_json(response, include_metadata), encoding="utf-8"
    )
    return destination
