"""Plain text converter."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from .common import render_text_table
from .types import Item


def build_text(items: Iterable[Item]) -> List[str]:
    lines: List[str] = ["Survey response", ""]
    for item in items:
        lines.append(f"{item.label}:")
        if item.table:
            table_lines = render_text_table(item.table)
            lines.extend(f"  {line}" for line in table_lines)
        else:
            for val in item.values:
                lines.append(f"  - {val}")
        for att in item.attachments:
            desc = att.content_type or "binary"
            lines.append(f"  - Attachment: {att.name} ({desc})")
        lines.append("")
    return lines


def write_text(items: Iterable[Item], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(build_text(items)), encoding="utf-8")
    return destination
