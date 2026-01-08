"""HTML converter."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from markdown2 import markdown

from .common import inline_html_images, wrap_html_output
from .types import Attachment


def build_html(markdown_body: str, attachments: Iterable[Attachment]) -> str:
    html_body = markdown(markdown_body, extras=["tables"])
    html_body = inline_html_images(html_body, attachments)
    return html_body


def write_html(markdown_body: str, attachments: Iterable[Attachment], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    html_body = build_html(markdown_body, attachments)
    destination.write_text(wrap_html_output(html_body), encoding="utf-8")
    return destination
