"""XML converter for Response objects."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

from .types import Cell, CellType, Response


def build_xml(response: Response) -> str:
    """Build an XML document for a survey response."""
    root = ET.Element("survey_response")
    root.set("id", response.response_id)
    
    if response.created:
        root.set("created", response.created)
    if response.creator:
        root.set("creator", response.creator)
    
    # Group cells by question
    by_question = {}
    for cell in response.cells:
        key = cell.address.question_key
        if key not in by_question:
            by_question[key] = []
        by_question[key].append(cell)
    
    # Build XML structure
    for question_key, cells in by_question.items():
        schema = response.question_schemas.get(question_key)
        question_elem = ET.SubElement(root, "question")
        question_elem.set("key", question_key)
        if schema:
            question_elem.set("type", schema.type)
            question_elem.set("label", schema.title)
        
        # Check if has dynamic content
        has_dynamic = any(c.address.row_index is not None for c in cells)
        
        if has_dynamic:
            # Group by row index
            by_row = {}
            for cell in cells:
                idx = cell.address.row_index or 0
                if idx not in by_row:
                    by_row[idx] = []
                by_row[idx].append(cell)
            
            for idx in sorted(by_row.keys()):
                row_elem = ET.SubElement(question_elem, "row")
                row_elem.set("index", str(idx))
                for cell in by_row[idx]:
                    _add_cell_to_xml(cell, row_elem)
        else:
            for cell in cells:
                _add_cell_to_xml(cell, question_elem)
    
    # Add attachments metadata
    if response.attachments:
        attachments_elem = ET.SubElement(root, "attachments")
        for att in response.attachments:
            att_elem = ET.SubElement(attachments_elem, "attachment")
            att_elem.set("id", att.attachment_id)
            att_elem.set("name", att.name)
            att_elem.set("field", att.field_key)
            if att.content_type:
                att_elem.set("content_type", att.content_type)
            att_elem.set("is_image", str(att.is_image).lower())
    
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode", method="xml"
    )


def _add_cell_to_xml(cell: Cell, parent: ET.Element):
    """Add a cell as XML element."""
    if cell.address.sub_key:
        elem = ET.SubElement(parent, "field")
        elem.set("key", cell.address.sub_key)
        elem.set("label", cell.label)
    else:
        elem = ET.SubElement(parent, "value")
    
    elem.text = str(cell.value) if cell.value is not None else ""
    
    if cell.display_value:
        elem.set("display", cell.display_value)
    
    if cell.cell_type == CellType.FILE:
        elem.set("type", "file")


def write_xml(response: Response, destination: Path) -> Path:
    """Write the XML export to disk."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(build_xml(response), encoding="utf-8")
    return destination
