"""CSV converter."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Tuple

from .spreadsheet import escape_formula_row


def write_csv(rows: Iterable[Tuple[str, str, str, str]], destination: Path) -> Path:
    """Write a CSV export from flattened response rows.

    Formula-leading values are escaped: a cell starting with ``=``, ``+``,
    ``-`` or ``@`` would otherwise be executed by the spreadsheet application
    an Editor opens the export with.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Key", "Field", "Value", "Attachments"])
        for row in rows:
            writer.writerow(escape_formula_row(row))
    return destination
