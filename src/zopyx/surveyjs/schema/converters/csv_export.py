"""CSV converter."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Tuple


def write_csv(rows: List[Tuple[str, str, str, str]], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Key", "Field", "Value", "Attachments"])
        writer.writerows(rows)
    return destination
