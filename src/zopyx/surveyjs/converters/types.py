"""Shared types for SurveyJS converters."""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from typing import Any, List, Tuple


@dataclass
class Attachment:
    """Binary attachment extracted from survey responses."""

    name: str
    content: bytes
    content_type: str | None = None
    field_label: str | None = None

    @property
    def is_image(self) -> bool:
        """Return True when the attachment is an image MIME type."""
        return bool(self.content_type and self.content_type.startswith("image/"))

    def data_url(self) -> str:
        """Return a data URL with base64-encoded attachment content."""
        if not self.content_type:
            mime = mimetypes.guess_type(self.name)[0]
            ctype = mime or "application/octet-stream"
        else:
            ctype = self.content_type
        encoded = base64.b64encode(self.content).decode("ascii")
        return f"data:{ctype};base64,{encoded}"


@dataclass
class Item:
    """Normalized survey item with values, attachments, and tabular data."""

    key: str
    label: str
    values: List[str]
    attachments: List[Attachment]
    field_type: str | None = None
    raw_value: Any | None = None
    table: List[List[str]] | None = None
    table_columns: List[Tuple[str, str]] | None = None
