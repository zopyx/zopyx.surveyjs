# Proposed Consolidated Intermediate Format for SurveyJS Converters

## Executive Summary

This document proposes a new intermediate data structure that unifies handling of all SurveyJS field types. The format is designed to:
- Support all field types (simple, nested, and dynamic)
- Enable efficient CSV flattening
- Preserve hierarchical relationships for structured exports
- Handle variable-length data (matrixdynamic, paneldynamic)
- Support attachments and metadata

---

## 1. Core Design Principles

### 1.1 Unified Cell-Based Model
All data is normalized into **cells** - atomic units that can be arranged into rows for CSV or hierarchies for JSON/XML.

### 1.2 Path-Based Addressing
Each cell has a unique **path** that encodes its location in the hierarchy, enabling reconstruction of nested structures.

### 1.3 Type-Aware Values
Cells carry type information to drive appropriate formatting per output format.

### 1.4 Separation of Data and Presentation
Schema information (labels, choices) is stored separately from values, allowing flexible rendering.

---

## 2. Data Structures

### 2.1 Core Types

```python
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union
from enum import Enum

class CellType(Enum):
    """Classification of cell value types."""
    SCALAR = "scalar"           # string, number, boolean
    ARRAY = "array"             # list of scalars (checkbox)
    MATRIX = "matrix"           # {row: col} mapping
    TABLE = "table"             # list of row objects (matrixdynamic)
    PANEL = "panel"             # list of panel objects (paneldynamic)
    FILE = "file"               # binary attachment reference
    NULL = "null"               # empty/unanswered

class ValueType(Enum):
    """Semantic type for formatting."""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    CHOICE = "choice"           # single choice value
    MULTICHOICE = "multichoice" # multiple choice values
    JSON = "json"               # raw JSON string

@dataclass
class CellAddress:
    """Hierarchical address for a cell.
    
    Examples:
    - Simple: "Q1"
    - Matrix row: "Q10.Wartezeiten"
    - MatrixDynamic row: "Q12[0].product"
    - PanelDynamic nested: "Q15[2].name"
    """
    question_key: str           # Top-level question name
    row_index: Optional[int] = None    # For dynamic content (matrix/panel)
    sub_key: Optional[str] = None      # For matrix rows or sub-questions
    parent_path: Optional[str] = None  # Full dot-notation path
    
    def to_path(self) -> str:
        """Generate dot-notation path."""
        parts = [self.question_key]
        if self.row_index is not None:
            parts.append(f"[{self.row_index}]")
        if self.sub_key:
            parts.append(f".{self.sub_key}")
        return "".join(parts)

@dataclass
class Cell:
    """Atomic data unit - the fundamental building block.
    
    Every piece of survey data is represented as a Cell, whether
    it's a simple text field or a cell within a matrix row.
    """
    # Identification
    address: CellAddress
    
    # Schema info (from form definition)
    label: str                  # Human-readable label
    field_type: str             # SurveyJS type: "text", "matrix", etc.
    
    # Value and type
    value: Any                  # The actual value
    cell_type: CellType         # Classification for handling
    value_type: ValueType       # Semantic type for formatting
    
    # Metadata for complex types
    schema: Optional[Dict] = None  # Original schema fragment
    choices: Optional[Dict] = None  # For choice-based: {value: text}
    
    # For CSV flattening
    column_name: Optional[str] = None  # Generated: "Q10_Wartezeiten"
    
    # Display formatting
    display_value: Optional[str] = None  # Human-readable formatted value

@dataclass
class Attachment:
    """Binary attachment with metadata."""
    attachment_id: str          # Unique ID: "{response_id}_{field_key}_{index}"
    name: str                   # Filename
    content: bytes              # Binary content
    content_type: Optional[str] = None
    field_key: str              # Source question
    field_label: Optional[str] = None
    row_index: Optional[int] = None  # For attachments in dynamic rows

@dataclass
class QuestionSchema:
    """Schema information for a question (from form JSON)."""
    key: str
    type: str
    title: str
    description: Optional[str] = None
    choices: Optional[List[Dict]] = None      # For checkbox/radiogroup
    rows: Optional[List[Dict]] = None         # For matrix
    columns: Optional[List[Dict]] = None      # For matrix/matrixdynamic
    template_elements: Optional[List] = None  # For paneldynamic
    is_required: bool = False

@dataclass
class Response:
    """Top-level container for a survey response."""
    response_id: str
    created: Optional[str] = None      # ISO timestamp
    modified: Optional[str] = None
    creator: Optional[str] = None      # User ID
    
    # Data storage
    cells: List[Cell]                  # Flat list of all cells
    attachments: List[Attachment]
    
    # Schema reference
    question_schemas: Dict[str, QuestionSchema]  # key -> schema
    
    # Indexes (computed)
    _cell_index: Optional[Dict[str, Cell]] = None  # path -> cell cache
    
    def get_cell(self, path: str) -> Optional[Cell]:
        """Fast lookup by path."""
        if self._cell_index is None:
            self._cell_index = {c.address.to_path(): c for c in self.cells}
        return self._cell_index.get(path)
    
    def get_cells_by_question(self, key: str) -> List[Cell]:
        """Get all cells for a question (handles dynamic arrays)."""
        return [c for c in self.cells if c.address.question_key == key]
    
    def get_simple_value(self, key: str) -> Any:
        """Get scalar value for simple questions."""
        cells = self.get_cells_by_question(key)
        if len(cells) == 1 and cells[0].cell_type == CellType.SCALAR:
            return cells[0].value
        return None

---

## 3. Field Type Mappings

### 3.1 Simple Fields → Single Cell

| SurveyJS Type | CellType | ValueType | Example Value |
|---------------|----------|-----------|---------------|
| `text` | SCALAR | STRING | `"John Doe"` |
| `comment` | SCALAR | STRING | `"Feedback text"` |
| `number` | SCALAR | NUMBER | `42` |
| `boolean` | SCALAR | BOOLEAN | `True` |
| `dropdown` | SCALAR | CHOICE | `"option1"` |
| `radiogroup` | SCALAR | CHOICE | `"yes"` |
| `date` | SCALAR | DATE | `"2024-03-26"` |

**Generated Cells:**
```python
Cell(
    address=CellAddress(question_key="Q1"),
    label="Full Name",
    field_type="text",
    value="John Doe",
    cell_type=CellType.SCALAR,
    value_type=ValueType.STRING,
    column_name="Q1"
)
```

### 3.2 Checkbox/Tagbox → Multiple Cells (One-Hot) OR Array Cell

**Strategy A: One-Hot (for CSV analysis)**
```python
# Schema choices: ["sports", "music", "reading"]
# Selected: ["sports", "reading"]

Cell(address=CellAddress("Q2", sub_key="sports"), value=1, column_name="Q2_sports")
Cell(address=CellAddress("Q2", sub_key="music"), value=0, column_name="Q2_music")
Cell(address=CellAddress("Q2", sub_key="reading"), value=1, column_name="Q2_reading")
```

**Strategy B: Single Cell with Array (for JSON)**
```python
Cell(
    address=CellAddress("Q2"),
    value=["sports", "reading"],
    cell_type=CellType.ARRAY,
    value_type=ValueType.MULTICHOICE
)
```

### 3.3 Matrix → Multiple Cells (One per Row)

**Input:**
```json
{"Q10": {"Wartezeiten": "3", "Support": "4"}}
```

**Generated Cells:**
```python
Cell(
    address=CellAddress("Q10", sub_key="Wartezeiten"),
    label="Q10 - Wartezeiten",
    field_type="matrix",
    value="3",
    cell_type=CellType.MATRIX,
    value_type=ValueType.CHOICE,
    column_name="Q10_Wartezeiten",
    choices={"1": "Poor", "2": "Fair", "3": "Good", "4": "Excellent"}
)
# ... similar for "Support"
```

### 3.4 MatrixDynamic → Table Rows

**Input:**
```json
{
  "Products": [
    {"product": "Widget", "qty": 5, "price": 10.00},
    {"product": "Gadget", "qty": 2, "price": 25.00}
  ]
}
```

**Generated Cells:**
```python
# Row 0
Cell(address=CellAddress("Products", row_index=0, sub_key="product"), 
     value="Widget", column_name="Products_product")
Cell(address=CellAddress("Products", row_index=0, sub_key="qty"), 
     value=5, column_name="Products_qty")
Cell(address=CellAddress("Products", row_index=0, sub_key="price"), 
     value=10.00, column_name="Products_price")

# Row 1
Cell(address=CellAddress("Products", row_index=1, sub_key="product"), 
     value="Gadget", column_name="Products_product")
# ... etc
```

### 3.5 PanelDynamic → Nested Structure

**Input:**
```json
{
  "Family": [
    {"name": "John", "age": 35, "hobbies": ["sports", "reading"]},
    {"name": "Jane", "age": 33, "hobbies": ["music"]}
  ]
}
```

**Generated Cells:**
```python
# Panel 0 - simple fields
Cell(address=CellAddress("Family", row_index=0, sub_key="name"), value="John")
Cell(address=CellAddress("Family", row_index=0, sub_key="age"), value=35)

# Panel 0 - nested array (hobbies)
Cell(address=CellAddress("Family", row_index=0, sub_key="hobbies_sports"), value=1)
Cell(address=CellAddress("Family", row_index=0, sub_key="hobbies_music"), value=0)
Cell(address=CellAddress("Family", row_index=0, sub_key="hobbies_reading"), value=1)

# Panel 1
Cell(address=CellAddress("Family", row_index=1, sub_key="name"), value="Jane")
# ... etc
```

### 3.6 File → Attachment Reference

```python
Cell(
    address=CellAddress("Photo"),
    label="Profile Photo",
    field_type="file",
    value="attachment://resp001_Photo_0",  # Reference, not binary
    cell_type=CellType.FILE,
    value_type=ValueType.STRING
)

# Actual binary stored separately
Attachment(
    attachment_id="resp001_Photo_0",
    name="profile.png",
    content=b"\x89PNG...",
    content_type="image/png",
    field_key="Photo"
)
```

---

## 4. Builder API

```python
class ResponseBuilder:
    """Builds Response objects from SurveyJS data."""
    
    def __init__(self, form_schema: Dict):
        self.schema = self._index_schema(form_schema)
        self.cells: List[Cell] = []
        self.attachments: List[Attachment] = []
    
    def add_simple(self, key: str, value: Any):
        """Add simple scalar field."""
        schema = self.schema[key]
        cell = Cell(
            address=CellAddress(question_key=key),
            label=schema.title,
            field_type=schema.type,
            value=value,
            cell_type=CellType.SCALAR,
            value_type=self._infer_value_type(schema.type, value),
            column_name=key
        )
        self.cells.append(cell)
    
    def add_matrix(self, key: str, value: Dict[str, str]):
        """Add matrix with row->column mapping."""
        schema = self.schema[key]
        for row_value, col_value in value.items():
            # Get row label from schema
            row_label = self._get_row_label(schema, row_value)
            cell = Cell(
                address=CellAddress(question_key=key, sub_key=row_value),
                label=f"{schema.title} - {row_label}",
                field_type="matrix",
                value=col_value,
                cell_type=CellType.MATRIX,
                value_type=ValueType.CHOICE,
                column_name=f"{key}_{row_value}",
                choices={c["value"]: c["text"] for c in schema.columns}
            )
            self.cells.append(cell)
    
    def add_checkbox_onehot(self, key: str, values: List[str]):
        """Add checkbox as one-hot encoded cells."""
        schema = self.schema[key]
        all_choices = {c["value"]: c["text"] for c in schema.choices}
        
        for choice_value, choice_text in all_choices.items():
            cell = Cell(
                address=CellAddress(question_key=key, sub_key=choice_value),
                label=f"{schema.title} - {choice_text}",
                field_type="checkbox",
                value=1 if choice_value in values else 0,
                cell_type=CellType.SCALAR,
                value_type=ValueType.BOOLEAN,
                column_name=f"{key}_{choice_value}"
            )
            self.cells.append(cell)
    
    def add_matrix_dynamic(self, key: str, rows: List[Dict]):
        """Add matrixdynamic as table rows."""
        schema = self.schema[key]
        col_schemas = {c["name"]: c for c in schema.columns}
        
        for row_idx, row_data in enumerate(rows):
            for col_name, cell_value in row_data.items():
                col_schema = col_schemas.get(col_name, {})
                cell = Cell(
                    address=CellAddress(
                        question_key=key, 
                        row_index=row_idx, 
                        sub_key=col_name
                    ),
                    label=f"{schema.title}[{row_idx}].{col_name}",
                    field_type="matrixdynamic",
                    value=cell_value,
                    cell_type=CellType.TABLE,
                    value_type=self._infer_value_type(col_schema.get("cellType"), cell_value),
                    column_name=f"{key}_{col_name}"
                )
                self.cells.append(cell)
    
    def build(self, response_id: str, metadata: Dict = None) -> Response:
        """Assemble final Response object."""
        return Response(
            response_id=response_id,
            cells=self.cells,
            attachments=self.attachments,
            question_schemas=self.schema,
            created=metadata.get("created") if metadata else None,
            creator=metadata.get("creator") if metadata else None
        )
```

---

## 5. Export Adapters

### 5.1 CSV Adapter (Wide Format)

```python
class CSVWideAdapter:
    """Export Response to wide-format CSV (single row per response)."""
    
    def export(self, response: Response) -> List[Dict[str, Any]]:
        """Returns list with single dict representing the row."""
        row = {
            "_ResponseID": response.response_id,
            "_Created": response.created,
            "_Creator": response.creator
        }
        
        for cell in response.cells:
            # Handle dynamic row expansion for limited cases
            if cell.address.row_index is not None:
                # For wide format, we may skip or limit dynamic rows
                if cell.address.row_index >= self.max_dynamic_rows:
                    continue
                col_name = f"{cell.column_name}_{cell.address.row_index}"
            else:
                col_name = cell.column_name
            
            row[col_name] = cell.value
        
        return [row]
```

### 5.2 CSV Adapter (Long Format)

```python
class CSVLongAdapter:
    """Export Response to long-format CSV (multiple rows per response)."""
    
    def export(self, response: Response) -> List[Dict[str, Any]]:
        """Returns multiple rows for dynamic content."""
        
        # Group cells by row_index
        main_cells = []  # No row_index
        dynamic_groups = {}  # row_index -> cells
        
        for cell in response.cells:
            if cell.address.row_index is None:
                main_cells.append(cell)
            else:
                idx = cell.address.row_index
                if idx not in dynamic_groups:
                    dynamic_groups[idx] = []
                dynamic_groups[idx].append(cell)
        
        # If no dynamic content, return single row
        if not dynamic_groups:
            row = self._cells_to_dict(main_cells)
            row["_ResponseID"] = response.response_id
            return [row]
        
        # Create row for each dynamic index
        rows = []
        base_row = self._cells_to_dict(main_cells)
        base_row["_ResponseID"] = response.response_id
        
        for idx in sorted(dynamic_groups.keys()):
            row = base_row.copy()
            row["_RowIndex"] = idx
            row["_RowType"] = dynamic_groups[idx][0].field_type
            
            for cell in dynamic_groups[idx]:
                row[cell.column_name] = cell.value
            
            rows.append(row)
        
        return rows
```

### 5.3 JSON Adapter

```python
class JSONAdapter:
    """Export Response to structured JSON preserving hierarchy."""
    
    def export(self, response: Response) -> Dict:
        """Reconstruct nested structure from flat cells."""
        result = {
            "_metadata": {
                "response_id": response.response_id,
                "created": response.created,
                "creator": response.creator
            },
            "data": {}
        }
        
        # Group by question key
        by_question = {}
        for cell in response.cells:
            key = cell.address.question_key
            if key not in by_question:
                by_question[key] = []
            by_question[key].append(cell)
        
        # Reconstruct each question
        for key, cells in by_question.items():
            result["data"][key] = self._reconstruct_value(cells)
        
        return result
    
    def _reconstruct_value(self, cells: List[Cell]) -> Any:
        """Reconstruct original value from cells."""
        if len(cells) == 1 and cells[0].address.sub_key is None:
            # Simple scalar
            return cells[0].value
        
        # Check if matrix (sub_keys but no row_index)
        if all(c.address.row_index is None for c in cells):
            return {c.address.sub_key: c.value for c in cells}
        
        # Check if table (has row_index)
        rows = {}
        for c in cells:
            idx = c.address.row_index or 0
            if idx not in rows:
                rows[idx] = {}
            rows[idx][c.address.sub_key] = c.value
        
        return [rows[i] for i in sorted(rows.keys())]
```

---

## 6. Comparison with Current Implementation

| Aspect | Current | Proposed |
|--------|---------|----------|
| **Core unit** | `Item` (question-level) | `Cell` (atomic) |
| **Hierarchy** | Flat list with `table` attr | Path-based addressing |
| **Matrix** | Joined string in `values` | Multiple cells with sub_key |
| **Checkbox** | Joined string | One-hot cells OR array cell |
| **MatrixDynamic** | JSON string | Table cells with row_index |
| **CSV export** | Single format | Multiple adapters |
| **Extensibility** | Hard-coded types | Type-driven handlers |
| **Metadata** | Limited | Rich schema attachment |

---

## 7. Benefits

1. **Complete Coverage:** Handles all field types including deeply nested paneldynamic
2. **Flexible Export:** Same data drives CSV (flat), JSON (hierarchical), XML (structured)
3. **Analytical Ready:** One-hot encoding enables direct statistical analysis
4. **Type Safety:** Rich typing prevents formatting errors
5. **Extensible:** New field types just need new CellType/ValueType handlers
6. **Testable:** Pure data structures easy to unit test
7. **Performance:** Flat cell list with index enables O(1) lookups

---

## 8. Migration Strategy

### Phase 1: Implement Core Types
- Define Cell, CellAddress, Attachment dataclasses
- Build ResponseBuilder with simple field types

### Phase 2: Add Complex Types
- Implement matrix, checkbox one-hot
- Add matrixdynamic table support

### Phase 3: Dynamic Content
- Implement paneldynamic with nesting
- Handle variable-length arrays

### Phase 4: Export Adapters
- CSV wide format
- CSV long format
- JSON/XML hierarchical

### Phase 5: Integration
- Replace current Item-based pipeline
- Maintain backward compatibility
- Performance optimization
