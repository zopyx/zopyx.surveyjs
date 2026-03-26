# SurveyJS Converters v2

A redesigned converter system for SurveyJS with a unified cell-based intermediate format that handles all field types including nested and dynamic content.

## Key Features

- **Cell-based architecture**: All data normalized to atomic cells with hierarchical addressing
- **Universal field support**: Handles simple fields, matrix, checkbox, matrixdynamic, paneldynamic
- **Multiple export formats**: Text, Markdown, HTML, PDF, CSV (wide/long), XLSX, XML, DOCX, JSON
- **Type-aware**: Rich type system drives appropriate formatting per output format
- **CSV-friendly**: One-hot encoding for checkboxes, wide/long format options for dynamic data

## Quick Start

```python
from pathlib import Path
from zopyx.surveyjs.converters2 import SurveyConverter, load_response_data

# Load converter with form schema
converter = SurveyConverter.from_files(Path("survey-form.json"))

# Load response data
data = load_response_data(Path("survey-response.json"))

# Convert to intermediate format
response = converter.convert(data, response_id="resp-001")

# Export to multiple formats
from zopyx.surveyjs.converters2 import write_csv, write_pdf, write_json

write_csv(response, Path("output.csv"), format="wide")
write_pdf(response, Path("output.pdf"))
write_json(response, Path("output.json"))
```

## CLI Usage

```bash
# Export to all formats
python -m zopyx.surveyjs.converters2 --data response.json --form form.json --output ./out

# Specific formats
python -m zopyx.surveyjs.converters2 --data response.json --form form.json --formats csv,json --csv-format wide

# Long format CSV for dynamic content
python -m zopyx.surveyjs.converters2 --data response.json --form form.json --formats csv --csv-format long
```

## Architecture

### Core Types

```python
from zopyx.surveyjs.converters2.types import Cell, CellAddress, Response

# Each piece of data is a Cell with hierarchical address
Cell(
    address=CellAddress(
        question_key="Orders",      # Top-level question
        row_index=0,                # For dynamic arrays
        sub_key="product"           # Column/field name
    ),
    label="Orders[0].product",
    value="Widget",
    cell_type=CellType.TABLE,
    column_name="Orders_product"
)
```

### Field Type Handling

| SurveyJS Type | Cell Generation | CSV Strategy |
|---------------|-----------------|--------------|
| `text`, `comment`, `number` | Single cell | Single column |
| `checkbox`, `tagbox` | One cell per choice (one-hot) | Boolean columns |
| `matrix` | One cell per row | Wide format columns |
| `matrixdynamic` | Cells with row_index | Long format or wide with suffix |
| `paneldynamic` | Cells with row_index | Long format |
| `file` | Cell + Attachment | Reference + separate files |

## CSV Export Formats

### Wide Format (Default)
Single row per response, dynamic content gets indexed columns:

```csv
_ResponseID,Q1_Name,Q2_sports,Q2_music,Q3_quality,Q3_price,Q4_product_0,Q4_product_1
resp-001,John,1,0,5,4,Widget,Gadget
```

### Long Format
Multiple rows for dynamic content:

```csv
_ResponseID,_RowIndex,_QuestionType,Q1_Name,Q4_product,Q4_qty,Q4_price
resp-001,,,John,,,
resp-001,0,matrixdynamic,,Widget,5,10.00
resp-001,1,matrixdynamic,,Gadget,2,25.00
```

## Comparison with Original Converters

| Aspect | Original (converters) | New (converters2) |
|--------|----------------------|-------------------|
| Intermediate | `Item` (question-level) | `Cell` (atomic) |
| Matrix | Joined string | Multiple cells |
| Checkbox | Joined values | One-hot cells |
| Dynamic tables | JSON string | Indexed cells |
| CSV handling | Single format | Wide/long options |
| Type system | Limited | Rich (CellType, ValueType) |

## Testing

```bash
cd /path/to/zopyx.surveyjs
python -m pytest src/zopyx/surveyjs/converters2/tests/ -v
```

## Migration Guide

The API is similar to the original converters with some key differences:

```python
# Old
from zopyx.surveyjs.converters import SurveyConverter
converter = SurveyConverter(data_path, form_path, output_dir)
items, attachments = converter.collect_items(entry, poll_id)

# New
from zopyx.surveyjs.converters2 import SurveyConverter
converter = SurveyConverter.from_files(form_path)
response = converter.convert(data, response_id)
# response.cells instead of items
# response.attachments same as before
```

## License

Same as the parent zopyx.surveyjs package.
