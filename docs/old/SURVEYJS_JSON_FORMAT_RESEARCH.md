# SurveyJS JSON Result Format Research

Research findings on how SurveyJS structures JSON results for matrix, checkbox, matrixdynamic, and paneldynamic field types.

---

## 1. Matrix (Single-Select Matrix)

### Schema Definition
```json
{
  "type": "matrix",
  "name": "Quality",
  "title": "Please score each department below.",
  "columns": [
    { "value": 0, "text": "None" },
    { "value": 25, "text": "Isolated" },
    { "value": 50, "text": "Some" },
    { "value": 100, "text": "Widespread" }
  ],
  "rows": [
    { "value": "training", "text": "Training" },
    { "value": "support", "text": "Support" },
    { "value": "safety", "text": "Safety" }
  ]
}
```

### Result JSON Format
```json
{
  "Quality": {
    "training": 25,
    "support": 50,
    "safety": 100
  }
}
```

### Key Characteristics
- **Structure:** Object with row values as keys, column values as values
- **Row identifier:** `row.value` (not `row.text`)
- **Column identifier:** `column.value` (not `column.text`)
- **Value type:** Typically string or number (the column value)
- **Empty answer:** `{}` or property omitted

### CSV Flattening Implications
- Each row becomes a potential column: `Quality_training`, `Quality_support`, `Quality_safety`
- Values are scalar (good for CSV)
- Row labels must be looked up from schema for human-readable headers

---

## 2. Checkbox

### Schema Definition
```json
{
  "type": "checkbox",
  "name": "products",
  "title": "Select products you are interested in:",
  "choices": [
    { "value": "item1", "text": "Item 1" },
    { "value": "item2", "text": "Item 2" },
    { "value": "item3", "text": "Item 3" }
  ]
}
```

### Result JSON Format
```json
{
  "products": ["item1", "item3"]
}
```

### Key Characteristics
- **Structure:** Array of selected choice values
- **Value type:** Array of strings/numbers
- **Empty answer:** `[]` or property omitted
- **Order:** Preserves selection order
- **Single selection:** Still an array with one element

### Alternative: store full objects (custom)
```json
{
  "products": [
    { "value": "item1", "text": "Item 1" },
    { "value": "item3", "text": "Item 3" }
  ]
}
```

### CSV Flattening Implications
- Current: joined string `"item1, item3"`
- One-hot encoding option: `products_item1=1`, `products_item2=0`, `products_item3=1`
- Choice count affects column count in one-hot format
- Choice text requires schema lookup

---

## 3. MatrixDynamic (Dynamic Matrix Table)

### Schema Definition
```json
{
  "type": "matrixdynamic",
  "name": "Orders",
  "title": "Enter your orders:",
  "columns": [
    { "name": "product", "title": "Product", "cellType": "text" },
    { "name": "quantity", "title": "Quantity", "cellType": "text" },
    { "name": "price", "title": "Price", "cellType": "text" }
  ],
  "rowCount": 1,
  "addRowText": "Add Order",
  "removeRowText": "Remove"
}
```

### Result JSON Format
```json
{
  "Orders": [
    { "product": "Widget", "quantity": "5", "price": "10.00" },
    { "product": "Gadget", "quantity": "2", "price": "25.00" },
    { "product": "Tool", "quantity": "1", "price": "50.00" }
  ]
}
```

### Key Characteristics
- **Structure:** Array of objects (one per row)
- **Row object keys:** Column `name` values (not `title`)
- **Row object values:** Cell values (strings by default)
- **Variable row count:** 0 to N rows per response
- **Empty answer:** `[]` or property omitted
- **Cell types:** Can be text, dropdown, checkbox, etc.

### With different cell types
```json
{
  "SurveyItems": [
    {
      "question": "How satisfied are you?",
      "type": "rating",
      "required": true
    },
    {
      "question": "Comments",
      "type": "comment",
      "required": false
    }
  ]
}
```

### CSV Flattening Implications
- **Wide format problematic:** Variable columns if expanded
- **Long format ideal:** One row per matrix row with ResponseID
- **Column naming:** `{Question}_{Column}` with row index: `Orders_0_product`, `Orders_1_product`
- **Schema needed:** Column names come from schema, not data

---

## 4. PanelDynamic (Dynamic Panel)

### Schema Definition
```json
{
  "type": "paneldynamic",
  "name": "FamilyMembers",
  "title": "Family Members",
  "templateElements": [
    { "type": "text", "name": "name", "title": "Name" },
    { "type": "text", "name": "age", "title": "Age" },
    { "type": "dropdown", "name": "relation", "title": "Relation", "choices": ["Father", "Mother", "Child"] }
  ],
  "panelCount": 1,
  "minPanelCount": 1,
  "maxPanelCount": 10
}
```

### Result JSON Format
```json
{
  "FamilyMembers": [
    {
      "name": "John Smith",
      "age": "35",
      "relation": "Father"
    },
    {
      "name": "Jane Smith",
      "age": "33",
      "relation": "Mother"
    },
    {
      "name": "Bob Smith",
      "age": "5",
      "relation": "Child"
    }
  ]
}
```

### Key Characteristics
- **Structure:** Array of objects (one per panel)
- **Panel object keys:** Question `name` values from templateElements
- **Variable panel count:** 0 to N panels per response
- **Heterogeneous content:** Each panel can have different question types
- **Nesting possible:** Panels can contain other dynamic elements
- **Empty answer:** `[]` or property omitted

### With nested questions
```json
{
  "Employees": [
    {
      "name": "Alice",
      "department": "Engineering",
      "skills": ["Python", "JavaScript"],
      "projects": [
        { "name": "Project A", "status": "active" },
        { "name": "Project B", "status": "completed" }
      ]
    }
  ]
}
```

### CSV Flattening Implications
- **Most complex type:** Can contain nested structures
- **Long format required:** Row per panel with ResponseID
- **Deep flattening:** May need to flatten nested arrays within panels
- **Column explosion risk:** If panel contains matrixdynamic
- **Relational model best:** Separate CSV for panel data with foreign key

---

## 5. Comparison Summary

| Type | Structure | Fixed/Variable | CSV Strategy |
|------|-----------|----------------|--------------|
| **Matrix** | `{"row": "col"}` | Fixed rows | Wide format (columns per row) |
| **Checkbox** | `["val1", "val2"]` | Fixed choices | One-hot encoding or joined |
| **MatrixDynamic** | `[{col: val}]` | Variable rows | Long format (row per entry) |
| **PanelDynamic** | `[{q: val}]` | Variable rows + types | Long format or relational |

---

## 6. SurveyJS `getPlainData()` Alternative Format

SurveyJS provides `getPlainData()` method that returns a normalized structure:

```javascript
survey.getPlainData()
```

### Output Format
```javascript
[
  {
    name: "Quality",
    title: "Please score each department",
    value: { training: 25, support: 50 },
    displayValue: "training: Isolated; support: Some",
    isNode: true,
    data: [
      { name: "training", title: "Training", value: 25, displayValue: "Isolated", isNode: false },
      { name: "support", title: "Support", value: 50, displayValue: "Some", isNode: false }
    ]
  },
  {
    name: "products",
    title: "Select products",
    value: ["item1", "item3"],
    displayValue: "Item 1, Item 3",
    isNode: true,
    data: [
      { name: "item1", title: "Item 1", value: "item1", displayValue: "Item 1", isNode: false },
      { name: "item3", title: "Item 3", value: "item3", displayValue: "Item 3", isNode: false }
    ]
  }
]
```

### Benefits for CSV Conversion
- Normalized structure across question types
- `isNode` flag indicates nested data
- `displayValue` provides human-readable format
- `data` array contains flattened children

---

## 7. Key Findings for CSV Flattening

### 7.1 Schema Dependency
All complex types require the form schema to properly interpret:
- Matrix needs `rows` and `columns` definitions for labels
- Checkbox needs `choices` for text labels
- MatrixDynamic needs `columns` for column names
- PanelDynamic needs `templateElements` for structure

### 7.2 Value Types Vary
- Matrix: Scalar values (string/number)
- Checkbox: Array of scalars
- MatrixDynamic: Array of objects with scalars
- PanelDynamic: Array of objects with mixed types

### 7.3 Empty Value Handling
- All types: Property may be omitted entirely
- Matrix: Empty object `{}`
- Checkbox: Empty array `[]`
- Dynamic: Empty array `[]`

### 7.4 Current Converter Limitations
Based on the code analysis:
- Matrix: Joined into string "Row: Value; Row2: Value2"
- Checkbox: Joined with ", "
- MatrixDynamic: JSON serialized into single cell
- PanelDynamic: JSON serialized into single cell

### 7.5 Recommended CSV Approaches

| Type | Recommended Approach | Column Example |
|------|---------------------|----------------|
| Matrix | Wide | `Q10_training`, `Q10_support` |
| Checkbox | One-hot wide | `Q1_item1`, `Q1_item2` (0/1) |
| MatrixDynamic | Long format | `ResponseID,Question,RowIndex,product,quantity` |
| PanelDynamic | Long format | `ResponseID,Question,PanelIndex,name,age` |

---

## 8. Research Sources

1. SurveyJS Documentation: "Access and Modify Survey Results"
   - https://surveyjs.io/form-library/documentation/access-and-modify-survey-results

2. SurveyJS API Reference: Matrix Table Question
   - https://surveyjs.io/form-library/documentation/api-reference/matrix-table-question-model

3. SurveyJS API Reference: Dynamic Matrix Table
   - https://surveyjs.io/form-library/documentation/api-reference/dynamic-matrix-table-question-model

4. SurveyJS API Reference: Dynamic Panel
   - https://surveyjs.io/form-library/documentation/api-reference/dynamic-panel-model

5. SurveyJS GitHub Issue #1604: Matrix result iteration
   - https://github.com/surveyjs/surveyjs/issues/1604

6. SurveyJS GitHub Issue #7869: Store full choice objects
   - https://github.com/surveyjs/survey-library/issues/7869
