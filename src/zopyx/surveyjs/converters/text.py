"""Plain text converter."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from .common import render_text_table
from .types import Item


def build_text(
    items: Iterable[Item],
    creator: str | None = None,
    created: str | None = None,
) -> List[str]:
    """Build a list of text lines for a survey response."""
    lines: List[str] = ["Survey response", ""]
    if creator:
        lines.append(f"Created by: {creator}")
    if created:
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            formatted_date = dt.strftime("%B %d, %Y at %I:%M %p %Z")
        except (ValueError, AttributeError):
            formatted_date = created
        lines.append(f"Created on: {formatted_date}")
    if creator or created:
        lines.append("")
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


def write_text(
    items: Iterable[Item],
    destination: Path,
    creator: str | None = None,
    created: str | None = None,
) -> Path:
    """Write the plain text export to disk."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "\n".join(build_text(items, creator, created)), encoding="utf-8"
    )
    return destination
