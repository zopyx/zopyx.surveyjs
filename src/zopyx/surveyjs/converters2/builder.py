"""Build Response objects from SurveyJS JSON data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .types import (
    Attachment,
    Cell,
    CellAddress,
    CellType,
    QuestionSchema,
    Response,
    ValueType,
)


class ResponseBuilder:
    """Builds Response objects from SurveyJS data and form schema."""
    
    def __init__(self, form_schema: Dict[str, Any]):
        """Initialize with form schema.
        
        Args:
            form_schema: Parsed SurveyJS form JSON
        """
        self.form_schema = form_schema
        self.question_schemas: Dict[str, QuestionSchema] = {}
        self._index_schema()
        
        # Builder state
        self.cells: List[Cell] = []
        self.attachments: List[Attachment] = []
        self.response_id: str = ""
    
    def _index_schema(self):
        """Extract and index question schemas from form."""
        for page in self.form_schema.get("pages", []):
            for element in page.get("elements", []):
                self._process_schema_element(element)
    
    def _process_schema_element(self, element: Dict, parent_key: str = ""):
        """Recursively process schema elements including nested ones."""
        element_type = element.get("type")
        name = element.get("name")
        
        if not name:
            return
        
        # Handle panel containers
        if element_type == "panel":
            for child in element.get("elements", []):
                self._process_schema_element(child, parent_key)
            return
        
        # Create QuestionSchema
        schema = QuestionSchema(
            key=name,
            type=element_type,
            title=element.get("title") or element.get("name") or name,
            description=element.get("description"),
            choices=element.get("choices"),
            rows=element.get("rows"),
            columns=element.get("columns"),
            template_elements=element.get("templateElements"),
            is_required=element.get("isRequired", False)
        )
        self.question_schemas[name] = schema
    
    def build_from_json(self, data: Dict[str, Any], response_id: str,
                       creator: Optional[str] = None,
                       created: Optional[str] = None) -> Response:
        """Build Response from SurveyJS result JSON.
        
        Args:
            data: Survey response data (the 'result' object)
            response_id: Unique identifier for this response
            creator: User who created the response
            created: ISO timestamp of creation
        
        Returns:
            Response object
        """
        self.response_id = response_id
        self.cells = []
        self.attachments = []
        
        # Process each question in the data
        for key, value in data.items():
            if key in self.question_schemas:
                self._add_question(key, value)
            else:
                # Unknown question - add as generic scalar
                self._add_generic(key, value)
        
        return Response(
            response_id=response_id,
            created=created,
            creator=creator,
            cells=self.cells,
            attachments=self.attachments,
            question_schemas=self.question_schemas
        )
    
    def _add_question(self, key: str, value: Any):
        """Add a question based on its schema type."""
        schema = self.question_schemas.get(key)
        if not schema:
            return
        
        handler = getattr(self, f"_add_{schema.type}", self._add_generic)
        handler(key, value, schema)
    
    def _add_text(self, key: str, value: Any, schema: QuestionSchema):
        """Add text question."""
        self._add_scalar(key, value, schema, ValueType.STRING)
    
    def _add_comment(self, key: str, value: Any, schema: QuestionSchema):
        """Add comment question."""
        self._add_scalar(key, value, schema, ValueType.STRING)
    
    def _add_number(self, key: str, value: Any, schema: QuestionSchema):
        """Add number question."""
        self._add_scalar(key, value, schema, ValueType.NUMBER)
    
    def _add_boolean(self, key: str, value: Any, schema: QuestionSchema):
        """Add boolean question."""
        self._add_scalar(key, value, schema, ValueType.BOOLEAN)
    
    def _add_dropdown(self, key: str, value: Any, schema: QuestionSchema):
        """Add dropdown question."""
        self._add_scalar(key, value, schema, ValueType.CHOICE)
    
    def _add_radiogroup(self, key: str, value: Any, schema: QuestionSchema):
        """Add radiogroup question."""
        self._add_scalar(key, value, schema, ValueType.CHOICE)
    
    def _add_date(self, key: str, value: Any, schema: QuestionSchema):
        """Add date question."""
        self._add_scalar(key, value, schema, ValueType.DATE)
    
    def _add_checkbox(self, key: str, value: Any, schema: QuestionSchema):
        """Add checkbox as one-hot encoded cells."""
        if not isinstance(value, list):
            value = [value] if value else []
        
        # Get all possible choices from schema
        all_choices = {}
        if schema.choices:
            for choice in schema.choices:
                val = choice.get("value")
                text = choice.get("text", val)
                all_choices[val] = text
        
        # Create one cell per choice
        for choice_value, choice_text in all_choices.items():
            cell = Cell(
                address=CellAddress(question_key=key, sub_key=str(choice_value)),
                label=f"{schema.title} - {choice_text}",
                field_type="checkbox",
                value=1 if choice_value in value else 0,
                cell_type=CellType.SCALAR,
                value_type=ValueType.BOOLEAN,
                column_name=f"{key}_{choice_value}",
                display_value="Yes" if choice_value in value else "No"
            )
            self.cells.append(cell)
    
    def _add_tagbox(self, key: str, value: Any, schema: QuestionSchema):
        """Add tagbox (same as checkbox)."""
        self._add_checkbox(key, value, schema)
    
    def _add_matrix(self, key: str, value: Dict[str, Any], schema: QuestionSchema):
        """Add matrix question - one cell per row."""
        if not isinstance(value, dict):
            return
        
        # Build choices lookup for columns
        choices = {}
        if schema.columns:
            choices = {str(c.get("value")): c.get("text", c.get("value")) 
                      for c in schema.columns}
        
        for row_value, col_value in value.items():
            row_text = schema.get_row_text(row_value)
            col_text = choices.get(str(col_value), str(col_value))
            
            cell = Cell(
                address=CellAddress(question_key=key, sub_key=str(row_value)),
                label=f"{schema.title} - {row_text}",
                field_type="matrix",
                value=col_value,
                cell_type=CellType.MATRIX,
                value_type=ValueType.CHOICE,
                column_name=f"{key}_{row_value}",
                choices=choices,
                display_value=f"{row_text}: {col_text}"
            )
            self.cells.append(cell)
    
    def _add_multipletext(self, key: str, value: Dict[str, Any], schema: QuestionSchema):
        """Add multiple text question - one cell per item."""
        if not isinstance(value, dict):
            return
        
        for item_key, item_value in value.items():
            cell = Cell(
                address=CellAddress(question_key=key, sub_key=item_key),
                label=f"{schema.title} - {item_key}",
                field_type="multipletext",
                value=item_value,
                cell_type=CellType.MATRIX,
                value_type=ValueType.STRING,
                column_name=f"{key}_{item_key}"
            )
            self.cells.append(cell)
    
    def _add_matrixdynamic(self, key: str, value: List[Dict], schema: QuestionSchema):
        """Add matrixdynamic as table rows."""
        if not isinstance(value, list):
            return
        
        # Build column schema lookup
        col_schemas = {}
        if schema.columns:
            col_schemas = {c.get("name"): c for c in schema.columns}
        
        for row_idx, row_data in enumerate(value):
            if not isinstance(row_data, dict):
                continue
            
            for col_name, cell_value in row_data.items():
                col_schema = col_schemas.get(col_name, {})
                cell_type = col_schema.get("cellType", "text")
                
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
                    value_type=self._infer_value_type(cell_type),
                    column_name=f"{key}_{col_name}"
                )
                self.cells.append(cell)
    
    def _add_paneldynamic(self, key: str, value: List[Dict], schema: QuestionSchema):
        """Add paneldynamic - flattened like matrixdynamic."""
        if not isinstance(value, list):
            return
        
        for panel_idx, panel_data in enumerate(value):
            if not isinstance(panel_data, dict):
                continue
            
            for field_key, field_value in panel_data.items():
                # Check if nested value is itself complex (array/dict)
                if isinstance(field_value, list):
                    # Handle arrays in panel (e.g., checkbox in panel)
                    self._add_panel_array(key, panel_idx, field_key, field_value, schema)
                elif isinstance(field_value, dict):
                    # Handle nested objects
                    for sub_key, sub_value in field_value.items():
                        cell = Cell(
                            address=CellAddress(
                                question_key=key,
                                row_index=panel_idx,
                                sub_key=f"{field_key}_{sub_key}"
                            ),
                            label=f"{schema.title}[{panel_idx}].{field_key}.{sub_key}",
                            field_type="paneldynamic",
                            value=sub_value,
                            cell_type=CellType.PANEL,
                            value_type=ValueType.STRING,
                            column_name=f"{key}_{field_key}_{sub_key}"
                        )
                        self.cells.append(cell)
                else:
                    # Simple scalar
                    cell = Cell(
                        address=CellAddress(
                            question_key=key,
                            row_index=panel_idx,
                            sub_key=field_key
                        ),
                        label=f"{schema.title}[{panel_idx}].{field_key}",
                        field_type="paneldynamic",
                        value=field_value,
                        cell_type=CellType.PANEL,
                        value_type=ValueType.STRING,
                        column_name=f"{key}_{field_key}"
                    )
                    self.cells.append(cell)
    
    def _add_panel_array(self, parent_key: str, panel_idx: int, field_key: str,
                        values: List, schema: QuestionSchema):
        """Handle array values within a paneldynamic."""
        # Create one-hot style cells for array in panel
        for idx, val in enumerate(values):
            cell = Cell(
                address=CellAddress(
                    question_key=parent_key,
                    row_index=panel_idx,
                    sub_key=f"{field_key}_{idx}"
                ),
                label=f"{schema.title}[{panel_idx}].{field_key}[{idx}]",
                field_type="paneldynamic",
                value=val,
                cell_type=CellType.PANEL,
                value_type=ValueType.STRING,
                column_name=f"{parent_key}_{field_key}_{idx}"
            )
            self.cells.append(cell)
    
    def _add_file(self, key: str, value: Any, schema: QuestionSchema):
        """Add file upload - extract attachments."""
        # File values can be single object or array
        files = value if isinstance(value, list) else [value] if value else []
        
        attachment_refs = []
        for idx, file_data in enumerate(files):
            if isinstance(file_data, dict):
                attachment = self._extract_attachment(key, file_data, idx)
                if attachment:
                    self.attachments.append(attachment)
                    attachment_refs.append(attachment.attachment_id)
        
        # Add cell with attachment references
        cell = Cell(
            address=CellAddress(question_key=key),
            label=schema.title,
            field_type="file",
            value=",".join(attachment_refs),
            cell_type=CellType.FILE,
            value_type=ValueType.STRING,
            column_name=key,
            display_value=f"{len(attachment_refs)} attachment(s)"
        )
        self.cells.append(cell)
    
    def _add_imagepicker(self, key: str, value: Any, schema: QuestionSchema):
        """Add imagepicker (multi-select images)."""
        if not isinstance(value, list):
            value = [value] if value else []
        
        # Similar to checkbox - one-hot
        all_choices = {}
        if schema.choices:
            for choice in schema.choices:
                val = choice.get("value")
                text = choice.get("text", val)
                all_choices[val] = text
        
        for choice_value, choice_text in all_choices.items():
            cell = Cell(
                address=CellAddress(question_key=key, sub_key=str(choice_value)),
                label=f"{schema.title} - {choice_text}",
                field_type="imagepicker",
                value=1 if choice_value in value else 0,
                cell_type=CellType.SCALAR,
                value_type=ValueType.BOOLEAN,
                column_name=f"{key}_{choice_value}"
            )
            self.cells.append(cell)
    
    def _add_ranking(self, key: str, value: List, schema: QuestionSchema):
        """Add ranking question (ordered choices)."""
        if not isinstance(value, list):
            value = [value] if value else []
        
        # Store as cells with position
        for idx, choice_value in enumerate(value):
            cell = Cell(
                address=CellAddress(question_key=key, sub_key=f"rank_{idx}"),
                label=f"{schema.title} - Rank {idx + 1}",
                field_type="ranking",
                value=choice_value,
                cell_type=CellType.SCALAR,
                value_type=ValueType.CHOICE,
                column_name=f"{key}_rank{idx}"
            )
            self.cells.append(cell)
    
    def _add_generic(self, key: str, value: Any, schema: Optional[QuestionSchema] = None):
        """Add generic/unknown question type."""
        title = schema.title if schema else key
        
        if isinstance(value, dict):
            # Treat as multipletext-like
            for sub_key, sub_value in value.items():
                cell = Cell(
                    address=CellAddress(question_key=key, sub_key=sub_key),
                    label=f"{title} - {sub_key}",
                    field_type="unknown",
                    value=sub_value,
                    cell_type=CellType.MATRIX,
                    value_type=ValueType.STRING,
                    column_name=f"{key}_{sub_key}"
                )
                self.cells.append(cell)
        elif isinstance(value, list):
            # Treat as checkbox-like
            for idx, item in enumerate(value):
                cell = Cell(
                    address=CellAddress(question_key=key, sub_key=str(idx)),
                    label=f"{title} - Item {idx}",
                    field_type="unknown",
                    value=item,
                    cell_type=CellType.ARRAY,
                    value_type=ValueType.STRING,
                    column_name=f"{key}_{idx}"
                )
                self.cells.append(cell)
        else:
            # Scalar
            cell = Cell(
                address=CellAddress(question_key=key),
                label=title,
                field_type=schema.type if schema else "unknown",
                value=value,
                cell_type=CellType.SCALAR,
                value_type=ValueType.STRING,
                column_name=key
            )
            self.cells.append(cell)
    
    def _add_scalar(self, key: str, value: Any, schema: QuestionSchema, 
                   value_type: ValueType):
        """Add simple scalar cell."""
        cell = Cell(
            address=CellAddress(question_key=key),
            label=schema.title,
            field_type=schema.type,
            value=value,
            cell_type=CellType.SCALAR,
            value_type=value_type,
            column_name=key,
            display_value=str(value) if value is not None else None
        )
        self.cells.append(cell)
    
    def _extract_attachment(self, field_key: str, file_data: Dict, 
                           index: int) -> Optional[Attachment]:
        """Extract attachment from file data."""
        content = file_data.get("content") or file_data.get("base64")
        if not content:
            return None
        
        # Decode base64 content
        import base64
        try:
            if "," in content:
                content = content.split(",", 1)[1]
            decoded = base64.b64decode(content)
        except Exception:
            return None
        
        attachment_id = f"{self.response_id}_{field_key}_{index}"
        
        return Attachment(
            attachment_id=attachment_id,
            name=file_data.get("name", f"{field_key}_{index}"),
            content=decoded,
            content_type=file_data.get("type"),
            field_key=field_key
        )
    
    def _infer_value_type(self, cell_type: str) -> ValueType:
        """Infer ValueType from cell type string."""
        mapping = {
            "text": ValueType.STRING,
            "number": ValueType.NUMBER,
            "boolean": ValueType.BOOLEAN,
            "dropdown": ValueType.CHOICE,
            "checkbox": ValueType.MULTICHOICE,
            "radiogroup": ValueType.CHOICE,
            "comment": ValueType.STRING,
            "date": ValueType.DATE,
        }
        return mapping.get(cell_type, ValueType.STRING)


def load_form_schema(path: Path) -> Dict[str, Any]:
    """Load and parse SurveyJS form schema from JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_response_data(path: Path) -> Dict[str, Any]:
    """Load survey response data from JSON file.
    
    Handles both direct result objects and wrapped formats.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    
    # Handle list of responses - take first
    if isinstance(data, list):
        if not data:
            raise ValueError("Empty response list")
        data = data[0]
    
    # Extract nested result if present
    if isinstance(data, dict) and "result" in data:
        data = data["result"]
    
    return data
