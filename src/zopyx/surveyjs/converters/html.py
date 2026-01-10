"""HTML converter."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from markdown2 import markdown

from .common import inline_html_images, wrap_html_output
from .types import Attachment


def build_html(markdown_body: str, attachments: Iterable[Attachment]) -> str:
    """Convert Markdown to HTML and inline image attachments."""
    html_body = markdown(markdown_body, extras=["tables"])
    # Ensure creator/created metadata appear on separate rows if present
    import re

    meta_parts = []
    created_by_match = re.search(r"<p>Created by:\s*(.*?)</p>", html_body)
    if created_by_match:
        meta_parts.append(
            f'<div class="meta-item"><strong>Created by:</strong> {created_by_match.group(1)}</div>'
        )
        html_body = html_body.replace(created_by_match.group(0), "", 1)

    created_on_match = re.search(r"<p>Created on:\s*(.*?)</p>", html_body)
    if created_on_match:
        meta_parts.append(
            f'<div class="meta-item"><strong>Created on:</strong> {created_on_match.group(1)}</div>'
        )
        html_body = html_body.replace(created_on_match.group(0), "", 1)

    if meta_parts:
        meta_html = '<div class="meta">' + "<br>".join(meta_parts) + "</div>"
        html_body = meta_html + html_body

    html_body = inline_html_images(html_body, attachments)
    return html_body


def write_html(
    markdown_body: str, attachments: Iterable[Attachment], destination: Path
) -> Path:
    """Write the HTML export to disk."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    html_body = build_html(markdown_body, attachments)
    destination.write_text(wrap_html_output(html_body), encoding="utf-8")
    return destination
