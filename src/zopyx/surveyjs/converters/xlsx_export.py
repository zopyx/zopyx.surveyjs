"""Excel converter."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

from openpyxl import Workbook

from .spreadsheet import write_text_row


def write_xlsx(rows: Iterable[Tuple[str, str, str, str]], destination: Path) -> Path:
    """Write an Excel workbook from flattened response rows.

    Formula-leading values are stored as explicit string cells, so a value
    submitted as ``=1+1`` is rendered as text instead of being persisted as a
    formula that Excel would evaluate when the export is opened.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Survey"
    write_text_row(ws, 1, ["Key", "Field", "Value", "Attachments"])
    row_index = 1
    for row in rows:
        row_index += 1
        write_text_row(ws, row_index, list(row))
    destination.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destination)
    return destination
