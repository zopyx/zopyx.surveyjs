# API Compatibility: converters vs converters2

## Overview

The `converters2` package has a redesigned API that is **not backward compatible** with the original `converters` package. This document outlines the differences and provides migration guidance.

---

## Key Differences

### 1. SurveyConverter Class

#### Original (converters)
```python
from zopyx.surveyjs.converters import SurveyConverter
from pathlib import Path

converter = SurveyConverter(
    data_path=Path("data.json"),
    form_path=Path("form.json"),
    output_dir=Path("./output")
)

# Load and convert
entry = converter.load_first_entry()
items, attachments = converter.collect_items(entry, poll_id="123")

# Export
paths = converter.run(formats={"csv", "pdf"}, email_recipient=None)
```

#### New (converters2)
```python
from zopyx.surveyjs.converters2 import SurveyConverter
from pathlib import Path

# Initialize with just form schema
converter = SurveyConverter.from_files(Path("form.json"))

# Or with schema dict
schema = json.loads(Path("form.json").read_text())
converter = SurveyConverter(schema)

# Convert data to Response object
data = json.loads(Path("data.json").read_text())
response = converter.convert(
    data, 
    response_id="123",
    creator="user@example.com",
    created="2024-03-26T10:30:00Z"
)

# Export (Response object passed explicitly)
paths = converter.run(
    response=response,
    formats={"csv", "pdf"},
    output_dir=Path("./output"),
    csv_format="wide"
)
```

### 2. Intermediate Data Format

#### Original: Item
```python
from zopyx.surveyjs.converters import Item, Attachment

item = Item(
    key="Q1",
    label="Question 1",
    values=["Answer"],
    attachments=[],
    field_type="text",
    raw_value=None,
    table=None,
    table_columns=None
)
```

#### New: Response with Cells
```python
from zopyx.surveyjs.converters2 import Response, Cell, CellAddress

response = Response(
    response_id="123",
    cells=[
        Cell(
            address=CellAddress(question_key="Q1"),
            label="Question 1",
            field_type="text",
            value="Answer",
            cell_type=CellType.SCALAR,
            value_type=ValueType.STRING
        )
    ],
    attachments=[]
)

# Access cells
for cell in response.cells:
    print(cell.address.to_path(), cell.value)

# Lookup by path
cell = response.get_cell("Q1")
```

### 3. Export Functions

#### Original
```python
from zopyx.surveyjs.converters import write_markdown, write_csv

# Markdown needs items, poll_id, creator, created
write_markdown(
    items, 
    poll_id="123",
    destination=Path("out.md"),
    creator="User",
    created="2024-03-26"
)

# CSV needs pre-built rows
from zopyx.surveyjs.converters import build_table_rows
rows = build_table_rows(items)
write_csv(rows, Path("out.csv"))
```

#### New
```python
from zopyx.surveyjs.converters2 import write_markdown, write_csv

# All writers take Response object
write_markdown(response, Path("out.md"))
write_csv(response, Path("out.csv"), format="wide")

# No need to pre-build rows - Response contains everything
```

### 4. CSV Export Options

#### Original
- Single format: flat table rows
- Matrix → joined string
- Dynamic → JSON blob

#### New
- Wide format: single row, dynamic columns indexed
- Long format: multiple rows with `_RowIndex`
- Matrix → separate columns
- Dynamic → proper table structure

---

## Migration Guide

### Simple Conversion Script

```python
"""Migrate from converters to converters2."""

# BEFORE (converters)
from zopyx.surveyjs.converters import SurveyConverter

converter = SurveyConverter(data_path, form_path, output_dir)
entry = converter.load_first_entry()
items, attachments = converter.collect_items(entry, "poll-123")
converter.run(formats={"csv", "pdf"})

# AFTER (converters2)
from zopyx.surveyjs.converters2 import SurveyConverter, load_response_data
from pathlib import Path

converter = SurveyConverter.from_files(form_path)
data = load_response_data(data_path)
response = converter.convert(
    data,
    response_id="poll-123",
    creator=data.get("user"),
    created=data.get("created")
)
converter.run(
    response=response,
    formats={"csv", "pdf"},
    output_dir=output_dir,
    csv_format="wide"
)
```

### Custom Processing Migration

```python
# BEFORE: Process items
from zopyx.surveyjs.converters import SurveyConverter

converter = SurveyConverter(data_path, form_path, output_dir)
entry = converter.load_first_entry()
items, attachments = converter.collect_items(entry, "123")

for item in items:
    if item.field_type == "matrix":
        # Parse joined string "Row: Value; Row2: Value2"
        values = item.values[0].split("; ")

# AFTER: Process cells
from zopyx.surveyjs.converters2 import SurveyConverter, load_response_data

converter = SurveyConverter.from_files(form_path)
data = load_response_data(data_path)
response = converter.convert(data, "123")

for cell in response.cells:
    if cell.field_type == "matrix":
        # Direct access to row value
        print(cell.address.sub_key, cell.value)
```

---

## Compatibility Layer (Optional)

To ease migration, you can create a compatibility wrapper:

```python
# compat.py - Compatibility layer
from pathlib import Path
from typing import List, Tuple

from zopyx.surveyjs.converters2 import (
    SurveyConverter as NewSurveyConverter,
    load_response_data,
    Response
)

class SurveyConverter:
    """API-compatible wrapper for converters2."""
    
    def __init__(self, data_path: Path, form_path: Path, output_dir: Path):
        self.data_path = data_path
        self.form_path = form_path
        self.output_dir = output_dir
        self._converter = NewSurveyConverter.from_files(form_path)
        self._data = load_response_data(data_path)
        self._response = None
    
    def load_first_entry(self) -> dict:
        """Return raw data for compatibility."""
        return self._data
    
    def collect_items(self, entry: dict, poll_id: str) -> Tuple[List, List]:
        """Convert to Response and return pseudo-items."""
        self._response = self._converter.convert(
            self._data,
            response_id=poll_id,
            creator=self._data.get("user"),
            created=self._data.get("created")
        )
        # Return cells as pseudo-items for compatibility
        return self._response.cells, self._response.attachments
    
    def run(self, formats: set[str], email_recipient: str = None) -> List[Path]:
        """Run conversion (ignores email_recipient)."""
        if self._response is None:
            raise RuntimeError("Must call collect_items first")
        return self._converter.run(
            self._response,
            formats=formats,
            output_dir=self.output_dir
        )
```

---

## Feature Comparison

| Feature | converters | converters2 | Notes |
|---------|------------|-------------|-------|
| Simple fields | ✓ | ✓ | Both support |
| Matrix | Joined string | Multiple columns | converters2 better for analysis |
| Checkbox | Joined values | One-hot columns | converters2 better for analysis |
| MatrixDynamic | JSON blob | Table rows | converters2 much better |
| PanelDynamic | JSON blob | Table rows | converters2 much better |
| CSV wide format | ✗ | ✓ | Single row per response |
| CSV long format | ✗ | ✓ | Multiple rows for dynamic |
| XLSX multi-response | ✗ | ✓ | Batch export support |
| Type safety | Limited | Rich | CellType, ValueType enums |
| Hierarchical data | ✗ | ✓ | Full path-based addressing |

---

## Recommendation

- **New projects**: Use `converters2` directly
- **Existing projects**: Gradually migrate or use compatibility wrapper
- **CSV analysis**: converters2 provides much better output for nested data
- **Simple exports**: Both work equally well for basic surveys
