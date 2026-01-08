"""Excel converter."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from openpyxl import Workbook


def write_xlsx(rows: List[Tuple[str, str, str, str]], destination: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Survey"
    ws.append(["Key", "Field", "Value", "Attachments"])
    for row in rows:
        ws.append(list(row))
    destination.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destination)
    return destination
