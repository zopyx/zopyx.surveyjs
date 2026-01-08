"""XML converter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, List, Tuple

from .types import Item


def build_xml(items: Iterable[Item], poll_id: str) -> str:
    root = ET.Element("survey_response")
    root.set("poll_id", poll_id)

    for item in items:
        field = ET.SubElement(root, "field")
        field.set("key", item.key)
        field.set("label", item.label)

        if item.table:
            table_elem = ET.SubElement(field, "table")
            columns: List[Tuple[str, str]] = item.table_columns or []
            if len(columns) < len(item.table[0]):
                padding = len(item.table[0]) - len(columns)
                columns = columns + [("", "")] * padding
            for idx, row in enumerate(item.table):
                row_elem = ET.SubElement(table_elem, "row")
                row_elem.set("header", str(idx == 0).lower())
                for col_idx, cell in enumerate(row):
                    cell_elem = ET.SubElement(row_elem, "cell")
                    if columns:
                        col_key, col_label = columns[col_idx]
                        if col_label:
                            cell_elem.set("label", col_label)
                        if col_key:
                            cell_elem.set("key", col_key.lower())
                    cell_elem.text = cell
        else:
            values_elem = ET.SubElement(field, "values")
            for val in item.values:
                value_elem = ET.SubElement(values_elem, "value")
                value_elem.text = val

        if item.attachments:
            attachments_elem = ET.SubElement(field, "attachments")
            for att in item.attachments:
                att_elem = ET.SubElement(attachments_elem, "attachment")
                att_elem.set("name", att.name)
                if att.content_type:
                    att_elem.set("content_type", att.content_type)
                att_elem.set("is_image", str(att.is_image).lower())

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode", method="xml")


def write_xml(items: Iterable[Item], poll_id: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(build_xml(items, poll_id), encoding="utf-8")
    return destination
