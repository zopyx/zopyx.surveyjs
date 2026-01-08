"""JSON converter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .types import Item


def build_json(
    items: Iterable[Item],
    poll_id: str,
    creator: str | None = None,
    created: str | None = None,
) -> str:
    """Build a JSON document for the survey response payload."""
    payload = {
        "poll_id": poll_id,
        "creator": creator,
        "created": created,
        "fields": [],
    }
    for item in items:
        values = item.values
        if item.field_type == "matrixdynamic" and item.raw_value is not None:
            values = item.raw_value
        field = {
            "key": item.key,
            "label": item.label,
            "values": values,
            "attachments": [
                {
                    "name": att.name,
                    "content_type": att.content_type,
                    "is_image": att.is_image,
                }
                for att in item.attachments
            ],
        }
        if item.table:
            field["table"] = item.table
        if item.table_columns:
            field["table_columns"] = [
                {"key": key, "label": label} for key, label in item.table_columns
            ]
        payload["fields"].append(field)
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_json(
    items: Iterable[Item],
    poll_id: str,
    destination: Path,
    creator: str | None = None,
    created: str | None = None,
) -> Path:
    """Write the JSON export to disk."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        build_json(items, poll_id, creator, created), encoding="utf-8"
    )
    return destination
