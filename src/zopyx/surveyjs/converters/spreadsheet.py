"""Formula-injection hardening for the spreadsheet exports.

Answer values are attacker-controlled.  Excel, LibreOffice and Google Sheets
treat a cell starting with ``=``, ``+``, ``-``, ``@``, a tab or a carriage
return as a formula (or as a DDE/command payload), so a public respondent can
plant a value that executes — or builds risky links — when an Editor opens a
CSV/XLSX export.

Two mechanisms, one rule:

* :func:`escape_formula_value` for CSV, which has no cell types: the value is
  prefixed with an apostrophe, the spreadsheet "this is text" marker.
* :func:`write_text_row` for XLSX: the value is kept verbatim but written as
  an explicit string cell.  openpyxl would otherwise persist a leading ``=``
  as a real formula (``<f>`` element) inside the workbook.
"""

from __future__ import annotations

from typing import Any, Iterable

#: Characters a spreadsheet application interprets as the start of a formula.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def is_formula_like(value: Any) -> bool:
    """Return whether ``value`` would be treated as a formula by a spreadsheet."""
    return isinstance(value, str) and value[:1] in FORMULA_PREFIXES


def escape_formula_value(value: Any) -> Any:
    """Return ``value`` neutralised for a CSV export.

    Non-strings and strings that cannot start a formula are returned
    unchanged.
    """
    if is_formula_like(value):
        return "'" + value
    return value


def escape_formula_row(row: Iterable[Any]) -> list[Any]:
    """Return ``row`` with every formula-leading value escaped for CSV."""
    return [escape_formula_value(value) for value in row]


def write_text_row(worksheet, row_index: int, values: Iterable[Any]) -> None:
    """Write ``values`` as one XLSX row, forcing formula-leading strings to text."""
    for column_index, value in enumerate(values, start=1):
        cell = worksheet.cell(row=row_index, column=column_index)
        cell.value = value
        if is_formula_like(value):
            # openpyxl stores "=..." as a formula; an explicit string cell
            # keeps the value inert (and visible) in every spreadsheet app.
            cell.data_type = "s"
