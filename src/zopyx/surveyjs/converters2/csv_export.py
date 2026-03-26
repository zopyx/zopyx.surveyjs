"""CSV converter for Response objects with wide and long format support."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import Cell, Response


class CSVWideAdapter:
    """Export Response to wide-format CSV (single row per response)."""
    
    def __init__(self, max_dynamic_rows: int = 10):
        self.max_dynamic_rows = max_dynamic_rows
    
    def export(self, response: Response) -> List[Dict[str, Any]]:
        """Returns list with single dict representing the row."""
        row: Dict[str, Any] = {
            "_ResponseID": response.response_id,
            "_Created": response.created or "",
            "_Creator": response.creator or ""
        }
        
        for cell in response.cells:
            # Handle dynamic rows with index suffix
            if cell.address.row_index is not None:
                if cell.address.row_index >= self.max_dynamic_rows:
                    continue
                col_name = f"{cell.column_name}_{cell.address.row_index}"
            else:
                col_name = cell.column_name
            
            # Ensure unique column name
            base_name = col_name
            counter = 1
            while col_name in row:
                col_name = f"{base_name}_{counter}"
                counter += 1
            
            row[col_name] = cell.value
        
        return [row]
    
    def get_headers(self, responses: List[Response]) -> List[str]:
        """Get union of all column headers from multiple responses."""
        all_keys = set()
        for resp in responses:
            row = self.export(resp)[0]
            all_keys.update(row.keys())
        
        # Order: metadata first, then alphabetically
        metadata = ["_ResponseID", "_Created", "_Creator"]
        others = sorted(k for k in all_keys if k not in metadata)
        return metadata + others


class CSVLongAdapter:
    """Export Response to long-format CSV (multiple rows for dynamic content)."""
    
    def export(self, response: Response) -> List[Dict[str, Any]]:
        """Returns multiple rows for dynamic content."""
        # Separate main cells from dynamic cells
        main_cells: List[Cell] = []
        dynamic_groups: Dict[int, List[Cell]] = {}
        
        for cell in response.cells:
            if cell.address.row_index is None:
                main_cells.append(cell)
            else:
                idx = cell.address.row_index
                if idx not in dynamic_groups:
                    dynamic_groups[idx] = []
                dynamic_groups[idx].append(cell)
        
        # Build base row from main cells
        base_row: Dict[str, Any] = {
            "_ResponseID": response.response_id,
            "_Created": response.created or "",
            "_Creator": response.creator or ""
        }
        for cell in main_cells:
            base_row[cell.column_name] = cell.value
        
        # If no dynamic content, return single row
        if not dynamic_groups:
            return [base_row]
        
        # Create row for each dynamic index
        rows = []
        for idx in sorted(dynamic_groups.keys()):
            row = base_row.copy()
            row["_RowIndex"] = idx
            
            # Get question type from first cell
            first_cell = dynamic_groups[idx][0]
            row["_QuestionType"] = first_cell.field_type
            
            for cell in dynamic_groups[idx]:
                row[cell.column_name] = cell.value
            
            rows.append(row)
        
        return rows
    
    def get_headers(self, responses: List[Response]) -> List[str]:
        """Get union of all column headers from multiple responses."""
        all_keys = set()
        for resp in responses:
            rows = self.export(resp)
            for row in rows:
                all_keys.update(row.keys())
        
        # Order: metadata, row index, then alphabetically
        metadata = ["_ResponseID", "_Created", "_Creator", "_RowIndex", "_QuestionType"]
        others = sorted(k for k in all_keys if k not in metadata)
        return metadata + others


def write_csv(response: Response, destination: Path, 
              format: str = "wide", max_dynamic_rows: int = 10) -> Path:
    """Write CSV export for a single response.
    
    Args:
        response: Response to export
        destination: Output file path
        format: "wide" or "long"
        max_dynamic_rows: Maximum dynamic rows for wide format
    
    Returns:
        Path to written file
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    
    if format == "wide":
        adapter = CSVWideAdapter(max_dynamic_rows)
    else:
        adapter = CSVLongAdapter()
    
    rows = adapter.export(response)
    headers = adapter.get_headers([response])
    
    with destination.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    
    return destination


def write_csv_multi(responses: List[Response], destination: Path,
                   format: str = "wide", max_dynamic_rows: int = 10) -> Path:
    """Write CSV export for multiple responses.
    
    Args:
        responses: List of responses to export
        destination: Output file path
        format: "wide" or "long"
        max_dynamic_rows: Maximum dynamic rows for wide format
    
    Returns:
        Path to written file
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    
    if format == "wide":
        adapter = CSVWideAdapter(max_dynamic_rows)
    else:
        adapter = CSVLongAdapter()
    
    headers = adapter.get_headers(responses)
    
    with destination.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        
        for response in responses:
            rows = adapter.export(response)
            writer.writerows(rows)
    
    return destination
