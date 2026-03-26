"""Core data structures for converters2 intermediate format."""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class CellType(Enum):
    """Classification of cell value types."""
    SCALAR = "scalar"
    ARRAY = "array"
    MATRIX = "matrix"
    TABLE = "table"
    PANEL = "panel"
    FILE = "file"
    NULL = "null"


class ValueType(Enum):
    """Semantic type for formatting."""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    CHOICE = "choice"
    MULTICHOICE = "multichoice"
    JSON = "json"


@dataclass
class CellAddress:
    """Hierarchical address for a cell.
    
    Examples:
    - Simple: "Q1"
    - Matrix row: "Q10.Wartezeiten"
    - MatrixDynamic row: "Q12[0].product"
    """
    question_key: str
    row_index: Optional[int] = None
    sub_key: Optional[str] = None
    
    def to_path(self) -> str:
        """Generate dot-notation path."""
        parts = [self.question_key]
        if self.row_index is not None:
            parts.append(f"[{self.row_index}]")
        if self.sub_key:
            if self.row_index is not None:
                parts.append(f".{self.sub_key}")
            else:
                parts.append(f".{self.sub_key}")
        return "".join(parts)
    
    def to_column_name(self) -> str:
        """Generate CSV-safe column name."""
        parts = [self.question_key]
        if self.sub_key:
            parts.append(self.sub_key)
        return "_".join(parts)


@dataclass
class Cell:
    """Atomic data unit - the fundamental building block."""
    address: CellAddress
    label: str
    field_type: str
    value: Any
    cell_type: CellType
    value_type: ValueType
    schema: Optional[Dict] = None
    choices: Optional[Dict] = None
    column_name: Optional[str] = None
    display_value: Optional[str] = None
    
    def __post_init__(self):
        if self.column_name is None:
            self.column_name = self.address.to_column_name()


@dataclass
class Attachment:
    """Binary attachment with metadata."""
    attachment_id: str
    name: str
    content: bytes
    content_type: Optional[str] = None
    field_key: str = ""
    field_label: Optional[str] = None
    row_index: Optional[int] = None
    
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
class QuestionSchema:
    """Schema information for a question (from form JSON)."""
    key: str
    type: str
    title: str
    description: Optional[str] = None
    choices: Optional[List[Dict]] = None
    rows: Optional[List[Dict]] = None
    columns: Optional[List[Dict]] = None
    template_elements: Optional[List] = None
    is_required: bool = False
    
    def get_choice_text(self, value: str) -> str:
        """Get display text for a choice value."""
        if self.choices:
            for choice in self.choices:
                if choice.get("value") == value:
                    return choice.get("text", value)
        return value
    
    def get_row_text(self, value: str) -> str:
        """Get display text for a matrix row value."""
        if self.rows:
            for row in self.rows:
                if row.get("value") == value:
                    return row.get("text", value)
        return value
    
    def get_column_text(self, value: str) -> str:
        """Get display text for a matrix column value."""
        if self.columns:
            for col in self.columns:
                if str(col.get("value")) == str(value):
                    return col.get("text", value)
        return value


@dataclass
class Response:
    """Top-level container for a survey response."""
    response_id: str
    created: Optional[str] = None
    modified: Optional[str] = None
    creator: Optional[str] = None
    cells: List[Cell] = field(default_factory=list)
    attachments: List[Attachment] = field(default_factory=list)
    question_schemas: Dict[str, QuestionSchema] = field(default_factory=dict)
    
    # Cache for fast lookups
    _cell_index: Optional[Dict[str, Cell]] = field(default=None, repr=False)
    _cells_by_question: Optional[Dict[str, List[Cell]]] = field(default=None, repr=False)
    
    def _build_index(self):
        """Build lookup indexes."""
        self._cell_index = {}
        self._cells_by_question = {}
        for cell in self.cells:
            path = cell.address.to_path()
            self._cell_index[path] = cell
            key = cell.address.question_key
            if key not in self._cells_by_question:
                self._cells_by_question[key] = []
            self._cells_by_question[key].append(cell)
    
    def get_cell(self, path: str) -> Optional[Cell]:
        """Fast lookup by path."""
        if self._cell_index is None:
            self._build_index()
        return self._cell_index.get(path)
    
    def get_cells_by_question(self, key: str) -> List[Cell]:
        """Get all cells for a question (handles dynamic arrays)."""
        if self._cells_by_question is None:
            self._build_index()
        return self._cells_by_question.get(key, [])
    
    def get_simple_value(self, key: str) -> Any:
        """Get scalar value for simple questions."""
        cells = self.get_cells_by_question(key)
        if len(cells) == 1 and cells[0].cell_type == CellType.SCALAR:
            return cells[0].value
        return None
    
    def get_value_by_path(self, path: str) -> Any:
        """Get value by full path."""
        cell = self.get_cell(path)
        return cell.value if cell else None
    
    def has_dynamic_content(self) -> bool:
        """Check if response has table/panel content with row_index."""
        for cell in self.cells:
            if cell.address.row_index is not None:
                return True
        return False
    
    def get_max_row_index(self, question_key: str) -> int:
        """Get maximum row index for a dynamic question."""
        cells = self.get_cells_by_question(question_key)
        indices = [c.address.row_index for c in cells if c.address.row_index is not None]
        return max(indices) if indices else -1
