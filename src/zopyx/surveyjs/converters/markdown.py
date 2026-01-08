"""Markdown converter."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .common import render_markdown_table
from .types import Item


def build_markdown(items: Iterable[Item], poll_id: str) -> str:
    """Build a Markdown document for a survey response."""
    parts = [f"# Survey response ({poll_id})", ""]
    for item in items:
        parts.append(f"## {item.label} ({item.key})")
        if item.table:
            parts.extend(render_markdown_table(item.table))
        else:
            for val in item.values:
                parts.append(f"- {val}")
        for att in item.attachments:
            if att.is_image:
                parts.append(f"![{item.label} - {att.name}]({att.name})")
            else:
                parts.append(f"[{att.name}]({att.name})")
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def write_markdown(items: Iterable[Item], poll_id: str, destination: Path) -> Path:
    """Write the Markdown export to disk."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(build_markdown(items, poll_id), encoding="utf-8")
    return destination
