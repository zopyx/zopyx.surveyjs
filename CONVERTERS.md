# SurveyJS Converters Documentation

This document provides an in-depth analysis of the converter logic in `src/zopyx/surveyjs/converters/`, with particular focus on the internal serialization format.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Internal Serialization Format](#internal-serialization-format)
  - [Attachment](#attachment-dataclass)
  - [Item](#item-dataclass)
- [The SurveyConverter Class](#the-surveyconverter-class)
- [Format Converters](#format-converters)
  - [Text, Markdown, HTML, PDF](#text-textpy)
  - [CSV, XLSX](#csv-csv_exportpy)
  - [XML, DOCX, JSON](#xml-xml_exportpy)
- [Common Utilities](#common-utilities)
- [Attachment Handling](#attachment-handling)
- [CLI Interface](#cli-interface)
- [Design Patterns](#design-patterns)
- [Extending the System](#extending-the-system)
- [Summary](#summary)
- [API Reference](#api-reference)
- [CSV Flattening Strategy](#csv-flattening-strategy-for-surveyjs-nesteddynamic-fields)

## Overview

The converters module provides a multi-format export system for SurveyJS survey responses. It transforms raw SurveyJS JSON data into various output formats (Text, Markdown, HTML, PDF, CSV, XLSX, XML, DOCX, JSON) through a normalized intermediate representation.

## Architecture

### Data Flow

```
SurveyJS Data JSON + Form Schema JSON
                ↓
      ┌───────────────────┐
      │  SurveyConverter  │  ← Core orchestrator (cli.py)
      └───────────────────┘
                ↓
      ┌───────────────────┐
      │   collect_items() │  ← Creates internal format
      └───────────────────┘
                ↓
    ┌─────────────────────────────┐
    │   List[Item] + Attachments  │  ← Internal serialization format
    └─────────────────────────────┘
                ↓
    ┌──────────────────────────────────────────┐
    │  Format-specific converters              │
    │  (text, markdown, html, pdf, csv, xlsx,  │
    │   xml, docx, json)                       │
    └──────────────────────────────────────────┘
                ↓
        Output Files
```

## Internal Serialization Format

The internal serialization format is the normalized intermediate representation that decouples SurveyJS-specific data parsing from format-specific rendering. This design allows adding new output formats without understanding SurveyJS data structures.

### Core Types (`types.py`)

#### `Attachment` Dataclass

Represents binary attachments extracted from survey file upload fields.

```python
@dataclass
class Attachment:
    name: str                    # Filename with extension
    content: bytes              # Raw binary content
    content_type: str | None    # MIME type (e.g., "image/png")
    field_label: str | None     # Human-readable field name
```

**Key Methods:**
- `is_image` (property): Returns `True` if `content_type` starts with `"image/"`
- `data_url()`: Returns base64-encoded data URL for embedding in HTML/PDF

**Example:**
```python
attachment = Attachment(
    name="photo.png",
    content=b"\x89PNG...",
    content_type="image/png",
    field_label="Profile Photo"
)

attachment.is_image        # True
attachment.data_url()      # "data:image/png;base64,iVBORw0KGgo..."
```

#### `Item` Dataclass

The central abstraction representing a single survey field/question with its response data.

```python
@dataclass
class Item:
    key: str                              # Field identifier (machine name)
    label: str                            # Human-readable field label
    values: List[str]                     # Display values (formatted strings)
    attachments: List[Attachment]         # Binary attachments for this field
    field_type: str | None = None         # SurveyJS element type
    raw_value: Any | None = None          # Original unprocessed value
    table: List[List[str]] | None = None  # Tabular data (matrixdynamic)
    table_columns: List[Tuple[str, str]]  # (key, label) pairs for columns
```

**Field Semantics:**

| Field | Purpose | Used By |
|-------|---------|---------|
| `key` | Unique identifier from form schema | All formats |
| `label` | Human-readable title | All formats |
| `values` | Formatted string representation | text, markdown, html |
| `attachments` | Binary file uploads | All formats |
| `field_type` | Original SurveyJS type ("file", "matrix", etc.) | JSON export |
| `raw_value` | Original data structure | JSON export (matrixdynamic) |
| `table` | 2D array for matrixdynamic rendering | text, markdown, html, docx, xml |
| `table_columns` | Column metadata (key, label) pairs | xml, structured exports |

**Value Transformation Examples:**

| SurveyJS Type | Input Value | `values` | `table` | `raw_value` |
|---------------|-------------|----------|---------|-------------|
| `text` | `"hello"` | `["hello"]` | `None` | `None` |
| `checkbox` | `["a", "b"]` | `["a, b"]` | `None` | `None` |
| `boolean` | `true` | `["Yes"]` | `None` | `None` |
| `matrix` | `{"row1": "col1"}` | `["Row 1: Column 1"]` | `None` | `None` |
| `matrixdynamic` | `[{"name": "John"}]` | `[JSON string]` | `[["Name"], ["John"]]` | Original array |
| `file` | File upload object | `["stored attachment: filename.png"]` | `None` | `None` |

### Format Value Mapping

The `SurveyConverter.format_value()` method in `cli.py` handles type-specific transformations:

```python
def format_value(self, name, label, value, element, poll_id) -> Tuple[
    List[str],           # Display values
    List[Attachment],    # Attachments
    List[List[str]]|None, # Table data
    List[Tuple[str,str]]|None, # Column metadata
    Any|None             # Raw value
]:
```

**Type Handling Logic:**

1. **`file` type**: Extracts base64 content → `Attachment` objects
2. **`matrix` type**: Maps row/column values to labels via schema
3. **`matrixdynamic` type**: Builds table structure with headers
4. **`boolean` type**: Converts to "Yes"/"No"
5. **`list` type**: Joins with ", " or "(empty)"
6. **`dict` type**: JSON serialization
7. **Primitives**: String conversion

## The `SurveyConverter` Class

Located in `cli.py`, this is the primary orchestrator class.

### Initialization

```python
converter = SurveyConverter(
    data_path=Path("survey-data.json"),   # Response data
    form_path=Path("survey-form.json"),   # Form schema
    output_dir=Path("./output")           # Output directory
)
```

### Schema Loading

The `load_schema()` method indexes form elements by name for O(1) lookup:

```python
schema = {
    "question1": {"type": "text", "title": "Your Name"},
    "question2": {"type": "file", "title": "Upload Document"},
    # ...
}
```

### Data Loading

`load_first_entry()` handles both:
- **List format**: `[{"result": {...}}, ...]` - takes first element
- **Dict format**: `{"result": {...}}` - uses directly

Extracts the nested `result` key if present.

### Item Collection (`collect_items()`)

Transforms raw entry data into the internal `List[Item]` format:

```python
def collect_items(self, entry: Dict[str, Any], poll_id: str) 
    -> Tuple[List[Item], List[Attachment]]:
    # For each field in entry:
    # 1. Look up schema element
    # 2. Call format_value() for type-specific handling
    # 3. Create Item with all metadata
    # 4. Aggregate attachments
```

## Format Converters

### Text (`text.py`)

Simple line-based output with indentation.

**Features:**
- Creator/created metadata at top
- Label followed by indented values
- Table rendering via `render_text_table()` (aligned columns with `|` separators)
- Attachment listings

**Example Output:**
```
Survey response

Created by: John Doe
Created on: March 26, 2026 at 10:30 AM UTC

Your Name:
  - John Doe

Preferences:
  - Option A | Option B
  ---+---
  Yes

Documents:
  - Attachment: document.pdf (application/pdf)
```

### Markdown (`markdown.py`)

Structured Markdown with GitHub-flavored tables.

**Features:**
- H1 heading with poll ID
- Bold labels with key in parentheses
- Bullet lists for values
- GFM tables for matrixdynamic data
- Image embedding syntax for image attachments

**Example Output:**
```markdown
# Survey response (poll-123)

Created by: John Doe
Created on: March 26, 2026 at 10:30 AM UTC

**Your Name** (full_name)
- John Doe

**Products** (products)

| Name | Price | Quantity |
| --- | --- | --- |
| Widget | $10 | 5 |
| Gadget | $25 | 2 |

![Products - photo.png](photo.png)
```

### HTML (`html.py`)

Converts Markdown to HTML with image inlining.

**Process:**
1. Convert Markdown to HTML via `markdown2` library
2. Extract creator/created metadata into `<div class="meta">` block
3. Inline image attachments (replace `src="filename"` with data URLs)
4. Wrap with styled container

**Image Inlining (`inline_html_images()`):**
```python
def inline_html_images(html_body: str, attachments: Iterable[Attachment]) -> str:
    # For each image attachment:
    # Replace src="filename" with src="data:image/png;base64,..."
```

### PDF (`pdf.py`)

Uses WeasyPrint to convert HTML to PDF.

**Features:**
- PDF-optimized CSS styling (`wrap_pdf_html()`)
- Print-friendly typography (10.5pt font)
- Metadata insertion near H1 heading
- Professional table styling with gradient headers

### CSV (`csv_export.py`)

Flat tabular format via `build_table_rows()`.

**Columns:**
- `Key`: Field identifier
- `Field`: Human-readable label
- `Value`: Semicolon-joined values
- `Attachments`: Semicolon-joined attachment descriptions

**Example:**
```csv
Key,Field,Value,Attachments
full_name,Your Name,John Doe,
photo,Profile Photo,stored attachment: photo.png,photo.png (image/png)
```

### XLSX (`xlsx_export.py`)

Excel workbook using openpyxl.

**Features:**
- Single worksheet named "Survey"
- Same flat structure as CSV
- Native Excel formatting

### XML (`xml_export.py`)

Hierarchical XML representation.

**Schema:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<survey_response poll_id="poll-123">
  <field key="full_name" label="Your Name">
    <values>
      <value>John Doe</value>
    </values>
  </field>
  <field key="products" label="Products">
    <table>
      <row header="true">
        <cell label="Product Name" key="name">Name</cell>
        <cell label="Price" key="price">Price</cell>
      </row>
      <row header="false">
        <cell label="Product Name" key="name">Widget</cell>
        <cell label="Price" key="price">$10</cell>
      </row>
    </table>
    <attachments>
      <attachment name="photo.png" content_type="image/png" is_image="true"/>
    </attachments>
  </field>
</survey_response>
```

### DOCX (`docx_export.py`)

Microsoft Word document using python-docx.

**Features:**
- H1 heading with poll ID
- H2 headings for each field (Label + key)
- Styled tables for matrixdynamic data
- Bold table headers
- Paragraph formatting for metadata

### JSON (`json_export.py`)

Structured JSON preserving type information.

**Schema:**
```json
{
  "poll_id": "poll-123",
  "creator": "John Doe",
  "created": "2026-03-26T10:30:00Z",
  "fields": [
    {
      "key": "full_name",
      "label": "Your Name",
      "values": ["John Doe"],
      "attachments": [],
      "table": null,
      "table_columns": null
    },
    {
      "key": "matrix_field",
      "label": "Dynamic Data",
      "values": [{"col1": "value1"}],
      "attachments": [],
      "table": [["Col1"], ["value1"]],
      "table_columns": [{"key": "col1", "label": "Column 1"}]
    }
  ]
}
```

**Special Handling:**
- `matrixdynamic` fields preserve original array in `values` (via `raw_value`)
- Attachment metadata includes `is_image` boolean

## Common Utilities (`common.py`)

### Table Rendering

**`render_text_table(table)`**: ASCII table with column alignment
```
Column A | Column B | Column C
---------+----------+----------
Value 1  | Value 2  | Value 3
```

**`render_markdown_table(table)`**: GFM table format
```markdown
| Column A | Column B | Column C |
| --- | --- | --- |
| Value 1 | Value 2 | Value 3 |
```

**`build_table_rows(items)`**: Flatten Items to CSV/XLSX rows

### HTML Wrappers

**`wrap_html_output(html_body)`**: Standalone HTML with modern styling
- Responsive container (max-width: 1100px)
- CSS custom properties for theming
- Professional typography and shadows

**`wrap_pdf_html(html_body, creator, created)`**: PDF-optimized HTML
- Smaller fonts (10.5pt vs default)
- Print-friendly margins
- Metadata insertion logic

## Attachment Handling

### Extraction Process

1. **Data URL Parsing** (`base64_from_data_url`):
   ```
   data:image/png;base64,iVBORw0KGgo...
   ```
   → Splits into content_type and base64 payload

2. **Validation** (`decode_base64_payload`):
   - Minimum length check (16 chars)
   - Base64 padding validation (mod 4)
   - Safe decoding with exception handling

3. **File Naming**:
   - Uses provided filename from upload metadata
   - Falls back to `{poll_id}_{field_name}_{index}.{ext}`
   - Extension from MIME type via `mimetypes.guess_extension()`

4. **Storage**:
   - Saved to output directory
   - Referenced in exports via filename
   - Inlined as data URLs in HTML/PDF

### Upload Formats Supported

**Single file (object):**
```json
{
  "name": "document.pdf",
  "type": "application/pdf",
  "content": "data:application/pdf;base64,..."
}
```

**Multiple files (array):**
```json
[
  {"name": "file1.png", "content": "data:image/png;base64,..."},
  {"name": "file2.png", "content": "data:image/png;base64,..."}
]
```

**Direct data URL (string):**
```json
"data:image/png;base64,iVBORw0KGgo..."
```

## CLI Interface

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SURVEYJS_DATA_JSON` | Path to response data | `survey-data-form.json` |
| `SURVEYJS_FORM_JSON` | Path to form schema | `survey-form-form.json` |
| `SURVEY_EMAIL_RECIPIENT` | Default email recipient | None |
| `SURVEY_SMTP_HOST` | SMTP server | `localhost` |
| `SURVEY_SMTP_PORT` | SMTP port | `25` |
| `SURVEY_SMTP_USERNAME` | SMTP auth user | None |
| `SURVEY_SMTP_PASSWORD` | SMTP auth password | None |
| `SURVEY_SMTP_STARTTLS` | Enable STARTTLS | `false` |
| `SURVEY_EMAIL_SENDER` | From address | `surveyjs@hostname` |
| `SURVEY_DOTENV_PATH` | Custom .env file path | `.env` |

### Usage

```bash
# Convert to all formats
python -m zopyx.surveyjs.converters --data responses.json --form schema.json --output ./out

# Specific formats
python -m zopyx.surveyjs.converters --formats md,html,pdf

# Email results
python -m zopyx.surveyjs.converters --email user@example.com
```

## Design Patterns

### 1. Two-Phase Transformation

```
Raw Data → Internal Format → Multiple Outputs
```

Benefits:
- Single parsing logic for SurveyJS quirks
- Adding new formats requires no SurveyJS knowledge
- Consistent handling across all outputs

### 2. Type Preservation Strategy

- **Display values** (`values`): Always strings, human-readable
- **Raw values** (`raw_value`): Original structure for JSON fidelity
- **Tabular representation** (`table`): Structured for rendering

### 3. Attachment Abstraction

Binary data flows separately from text content:
- Extracted during parsing
- Saved to disk
- Referenced by filename in text formats
- Inlined as data URLs in markup formats

### 4. Progressive Enhancement

Base formats (text, markdown) are dependencies for richer formats:
- HTML builds on Markdown
- PDF builds on HTML
- This ensures consistency and reduces code duplication

## Testing

The test suite in `tests/test_converters.py` covers:

- **Type behavior**: Attachment data URLs, image detection
- **Table rendering**: Empty tables, column padding, alignment
- **Format round-trips**: All export formats produce valid output
- **Metadata handling**: Creator/created date formatting
- **Edge cases**: Unparseable dates, empty values, missing schema

## Extending the System

### Adding a New Output Format

1. **Create converter module** (e.g., `yaml_export.py`):
```python
def build_yaml(items: Iterable[Item], poll_id: str) -> str:
    """Build YAML representation."""
    # Transform Item list to YAML
    ...

def write_yaml(items: Iterable[Item], poll_id: str, destination: Path) -> Path:
    """Write YAML export to disk."""
    destination.write_text(build_yaml(items, poll_id))
    return destination
```

2. **Add to `__init__.py` exports**

3. **Integrate in `SurveyConverter.run()`**:
```python
if "yaml" in formats:
    yaml_path = self.output_dir / f"{poll_id}.yaml"
    written_paths.append(write_yaml(items, poll_id, yaml_path))
```

4. **Add tests** following existing patterns

### Adding New Field Type Support

1. **Update `format_value()` in `cli.py`**:
```python
if element.get("type") == "newtype":
    return self.format_newtype(value, element), [], None, None, None
```

2. **Add type-specific formatter method**

3. **Update internal format if needed** (rare - existing structure is flexible)

## Summary

The internal serialization format (`List[Item]`) is the key architectural decision that enables multi-format export. By normalizing SurveyJS's heterogeneous data structures into a consistent, type-rich intermediate representation, the system achieves:

- **Separation of concerns**: Parsing vs. rendering
- **Format extensibility**: New outputs without SurveyJS knowledge  
- **Consistent behavior**: All formats handle complex types uniformly
- **Testability**: Internal format is easy to construct and verify

The `Item` dataclass captures all necessary metadata while `Attachment` handles binary content separately, creating a clean abstraction that supports everything from plain text to richly formatted PDFs.

---

# API Reference

Complete API documentation for the `zopyx.surveyjs.converters` module.

Complete API documentation for the `zopyx.surveyjs.converters` module.

## Table of Contents

- [Types](#types)
  - [Attachment](#attachment)
  - [Item](#item)
- [Core Converter](#core-converter)
  - [SurveyConverter](#surveyconverter)
- [Format Writers](#format-writers)
  - [Text](#text)
  - [Markdown](#markdown)
  - [HTML](#html)
  - [PDF](#pdf)
  - [CSV](#csv)
  - [XLSX](#xlsx)
  - [XML](#xml)
  - [DOCX](#docx)
  - [JSON](#json)
- [Common Utilities](#common-utilities)
- [CLI Functions](#cli-functions)

---

## Types

### Attachment

```python
@dataclass
class Attachment:
    name: str
    content: bytes
    content_type: str | None = None
    field_label: str | None = None
```

Binary attachment extracted from survey file upload fields.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Filename with extension |
| `content` | `bytes` | Raw binary content |
| `content_type` | `str \| None` | MIME type (e.g., "image/png") |
| `field_label` | `str \| None` | Human-readable field name |

**Methods:**

#### `is_image` (property)

```python
@property
def is_image(self) -> bool
```

Returns `True` when the attachment is an image MIME type (starts with "image/").

**Example:**
```python
attachment = Attachment("photo.png", b"\x89PNG...", "image/png")
if attachment.is_image:
    print("This is an image")
```

#### `data_url()`

```python
def data_url(self) -> str
```

Returns a data URL with base64-encoded attachment content.

**Format:** `data:{mime_type};base64,{encoded_content}`

**Example:**
```python
url = attachment.data_url()
# "data:image/png;base64,iVBORw0KGgo..."
```

---

### Item

```python
@dataclass
class Item:
    key: str
    label: str
    values: List[str]
    attachments: List[Attachment]
    field_type: str | None = None
    raw_value: Any | None = None
    table: List[List[str]] | None = None
    table_columns: List[Tuple[str, str]] | None = None
```

Normalized survey item with values, attachments, and tabular data.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `key` | `str` | Field identifier (machine name from schema) |
| `label` | `str` | Human-readable field label |
| `values` | `List[str]` | Display values as formatted strings |
| `attachments` | `List[Attachment]` | Binary attachments for this field |
| `field_type` | `str \| None` | SurveyJS element type (e.g., "file", "matrix") |
| `raw_value` | `Any \| None` | Original unprocessed value |
| `table` | `List[List[str]] \| None` | Tabular data for matrixdynamic fields |
| `table_columns` | `List[Tuple[str, str]] \| None` | Column metadata as (key, label) pairs |

**Example:**
```python
item = Item(
    key="full_name",
    label="Full Name",
    values=["John Doe"],
    attachments=[],
    field_type="text"
)
```

---

## Core Converter

### SurveyConverter

Main orchestrator class for converting SurveyJS data to multiple output formats.

```python
class SurveyConverter:
    def __init__(self, data_path: Path, form_path: Path, output_dir: Path) -> None
```

**Constructor Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `data_path` | `Path` | Path to survey response data JSON file |
| `form_path` | `Path` | Path to survey form schema JSON file |
| `output_dir` | `Path` | Directory for output files |

**Example:**
```python
from pathlib import Path
from zopyx.surveyjs.converters import SurveyConverter

converter = SurveyConverter(
    data_path=Path("survey-data.json"),
    form_path=Path("survey-form.json"),
    output_dir=Path("./output")
)
paths = converter.run(formats={"pdf", "csv"})
```

---

#### `load_first_entry()`

```python
def load_first_entry(self) -> Dict[str, Any]
```

Load survey data and return the first entry from a list or a single dict.

**Returns:** Dictionary containing survey response data

**Raises:**
- `ValueError`: If result payload is empty
- `TypeError`: If first entry is not a JSON object

---

#### `load_schema()`

```python
def load_schema(self) -> Dict[str, Dict[str, Any]]
```

Index form elements by name for quick label lookup.

**Returns:** Dictionary mapping field names to element definitions

---

#### `collect_items()`

```python
def collect_items(
    self, 
    entry: Dict[str, Any], 
    poll_id: str
) -> Tuple[List[Item], List[Attachment]]
```

Assemble items with labels, values, and attachments for downstream rendering.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `entry` | `Dict[str, Any]` | Survey response data |
| `poll_id` | `str` | Identifier for the survey/poll |

**Returns:** Tuple of `(items, attachments)`

**Example:**
```python
entry = converter.load_first_entry()
items, attachments = converter.collect_items(entry, "poll-123")
```

---

#### `run()`

```python
def run(
    self, 
    formats: set[str], 
    email_recipient: str | None = None
) -> List[Path]
```

Convert the first survey entry to the requested formats.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `formats` | `set[str]` | Set of format identifiers ("text", "md", "html", "pdf", "csv", "xlsx", "xml", "docx", "json") |
| `email_recipient` | `str \| None` | Optional email address to send outputs |

**Returns:** List of paths to generated files

**Example:**
```python
# Generate PDF and CSV
paths = converter.run(formats={"pdf", "csv"})

# Generate all formats and email
paths = converter.run(
    formats={"text", "md", "html", "pdf", "csv", "xlsx", "xml", "docx", "json"},
    email_recipient="user@example.com"
)
```

---

#### `send_email()`

```python
def send_email(
    self,
    recipient: str | Iterable[str],
    attachments: List[Path],
    poll_id: str,
    creator: str = None,
    created: str = None,
    survey_attachments: List[Path] = None,
    sender: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    cc: Iterable[str] | None = None,
    bcc: Iterable[str] | None = None,
) -> None
```

Send generated files via SMTP.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `recipient` | `str \| Iterable[str]` | Primary recipient(s) |
| `attachments` | `List[Path]` | Files to attach |
| `poll_id` | `str` | Survey identifier for subject line |
| `creator` | `str` | Optional creator name for body |
| `created` | `str` | Optional ISO timestamp for body |
| `survey_attachments` | `List[Path]` | Additional survey file attachments |
| `sender` | `str \| None` | From address (defaults to env var) |
| `subject` | `str \| None` | Custom subject line |
| `body` | `str \| None` | Custom email body |
| `cc` | `Iterable[str] \| None` | CC recipients |
| `bcc` | `Iterable[str] \| None` | BCC recipients |

**Environment Variables:**
- `SURVEY_SMTP_HOST`: SMTP server (default: localhost)
- `SURVEY_SMTP_PORT`: SMTP port (default: 25)
- `SURVEY_SMTP_USERNAME`: SMTP username
- `SURVEY_SMTP_PASSWORD`: SMTP password
- `SURVEY_SMTP_STARTTLS`: Enable STARTTLS ("true"/"false")
- `SURVEY_EMAIL_SENDER`: From address

---

## Format Writers

### Text

#### `build_text()`

```python
def build_text(
    items: Iterable[Item],
    creator: str | None = None,
    created: str | None = None,
) -> List[str]
```

Build a list of text lines for a survey response.

**Returns:** List of text lines

---

#### `write_text()`

```python
def write_text(
    items: Iterable[Item],
    destination: Path,
    creator: str | None = None,
    created: str | None = None,
) -> Path
```

Write the plain text export to disk.

**Returns:** Path to written file

---

### Markdown

#### `build_markdown()`

```python
def build_markdown(
    items: Iterable[Item],
    poll_id: str,
    creator: str | None = None,
    created: str | None = None,
) -> str
```

Build a Markdown document for a survey response.

**Returns:** Markdown string

---

#### `write_markdown()`

```python
def write_markdown(
    items: Iterable[Item],
    poll_id: str,
    destination: Path,
    creator: str | None = None,
    created: str | None = None,
) -> Path
```

Write the Markdown export to disk.

**Returns:** Path to written file

---

### HTML

#### `build_html()`

```python
def build_html(
    markdown_body: str, 
    attachments: Iterable[Attachment]
) -> str
```

Convert Markdown to HTML and inline image attachments.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `markdown_body` | `str` | Markdown content |
| `attachments` | `Iterable[Attachment]` | Attachments to inline as data URLs |

**Returns:** HTML body string (without HTML wrapper)

---

#### `write_html()`

```python
def write_html(
    markdown_body: str, 
    attachments: Iterable[Attachment], 
    destination: Path
) -> Path
```

Write the HTML export to disk.

**Returns:** Path to written file

---

### PDF

#### `write_pdf()`

```python
def write_pdf(
    html_body: str,
    destination: Path,
    creator: str | None = None,
    created: str | None = None,
) -> Path
```

Write a PDF export from HTML content.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `html_body` | `str` | HTML content (will be wrapped with PDF styles) |
| `destination` | `Path` | Output file path |
| `creator` | `str \| None` | Creator name for metadata |
| `created` | `str \| None` | ISO timestamp for metadata |

**Returns:** Path to written file

---

### CSV

#### `write_csv()`

```python
def write_csv(
    rows: List[Tuple[str, str, str, str]], 
    destination: Path
) -> Path
```

Write a CSV export from flattened response rows.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `rows` | `List[Tuple[str, str, str, str]]` | Rows as (key, label, value, attachments) tuples |
| `destination` | `Path` | Output file path |

**Returns:** Path to written file

**Example:**
```python
from zopyx.surveyjs.converters import build_table_rows, write_csv

rows = build_table_rows(items)
write_csv(rows, Path("output.csv"))
```

---

### XLSX

#### `write_xlsx()`

```python
def write_xlsx(
    rows: List[Tuple[str, str, str, str]], 
    destination: Path
) -> Path
```

Write an Excel workbook from flattened response rows.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `rows` | `List[Tuple[str, str, str, str]]` | Rows as (key, label, value, attachments) tuples |
| `destination` | `Path` | Output file path |

**Returns:** Path to written file

---

### XML

#### `build_xml()`

```python
def build_xml(items: Iterable[Item], poll_id: str) -> str
```

Build an XML document for a survey response.

**Returns:** XML string

---

#### `write_xml()`

```python
def write_xml(
    items: Iterable[Item], 
    poll_id: str, 
    destination: Path
) -> Path
```

Write the XML export to disk.

**Returns:** Path to written file

---

### DOCX

#### `write_docx()`

```python
def write_docx(
    items: Iterable[Item],
    destination: Path,
    poll_id: str,
    creator: str | None = None,
    created: str | None = None,
) -> Path
```

Write a DOCX export with headings, tables, and attachments.

**Returns:** Path to written file

---

### JSON

#### `build_json()`

```python
def build_json(
    items: Iterable[Item],
    poll_id: str,
    creator: str | None = None,
    created: str | None = None,
) -> str
```

Build a JSON document for the survey response payload.

**Returns:** JSON string (formatted with indent=2)

---

#### `write_json()`

```python
def write_json(
    items: Iterable[Item],
    poll_id: str,
    destination: Path,
    creator: str | None = None,
    created: str | None = None,
) -> Path
```

Write the JSON export to disk.

**Returns:** Path to written file

---

## Common Utilities

### `build_table_rows()`

```python
def build_table_rows(
    items: Iterable[Item]
) -> List[Tuple[str, str, str, str]]
```

Build flat rows for CSV/XLSX exports.

**Returns:** List of tuples `(key, label, value, attachments)`

**Example:**
```python
from zopyx.surveyjs.converters import build_table_rows

rows = build_table_rows(items)
# [("q1", "Name", "John", ""), ("q2", "Photo", "stored: img.png", "img.png (image/png)")]
```

---

### `render_text_table()`

```python
def render_text_table(table: List[List[str]]) -> List[str]
```

Render a text-aligned table for plain text outputs.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `table` | `List[List[str]]` | 2D array of cells, first row is header |

**Returns:** List of formatted text lines

**Example:**
```python
lines = render_text_table([["Name", "Age"], ["John", "30"]])
# ["Name | Age", "-----+-----", "John | 30  "]
```

---

### `render_markdown_table()`

```python
def render_markdown_table(table: List[List[str]]) -> List[str]
```

Render a Markdown table from the provided cell matrix.

**Returns:** List of Markdown table lines

---

### `inline_html_images()`

```python
def inline_html_images(
    html_body: str, 
    attachments: Iterable[Attachment]
) -> str
```

Replace attachment file references with data URLs for images.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `html_body` | `str` | HTML content with img tags |
| `attachments` | `Iterable[Attachment]` | Image attachments to inline |

**Returns:** HTML with image src attributes replaced by data URLs

---

### `wrap_html_output()`

```python
def wrap_html_output(html_body: str) -> str
```

Wrap HTML with minimal styling for standalone display.

**Returns:** Complete HTML document with CSS

---

### `wrap_pdf_html()`

```python
def wrap_pdf_html(
    html_body: str, 
    creator: str | None = None, 
    created: str | None = None
) -> str
```

Wrap HTML with PDF-friendly styles and optional metadata.

**Returns:** Complete HTML document optimized for PDF generation

---

## CLI Functions

### `parse_args()`

```python
def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace
```

Parse CLI options for selecting input and output settings.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `argv` | `Sequence[str] \| None` | Command line arguments (defaults to sys.argv) |

**Returns:** Parsed arguments namespace

**Arguments:**
- `--data`: Path to survey data JSON
- `--form`: Path to survey form JSON  
- `--output`: Output directory
- `--formats`: Comma-separated format list (default: "all")
- `--email`: Email recipient for output files

---

### `parse_formats()`

```python
def parse_formats(spec: str) -> set[str]
```

Normalize and validate requested formats.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `spec` | `str` | Format specification ("all" or comma-separated) |

**Returns:** Set of valid format strings

**Raises:** `ValueError` if unknown formats specified

**Example:**
```python
from zopyx.surveyjs.converters import parse_formats

formats = parse_formats("pdf,csv,json")
# {"pdf", "csv", "json"}

formats = parse_formats("all")
# {"text", "md", "html", "pdf", "csv", "xlsx", "xml", "docx", "json"}
```

---

### `slugify()`

```python
def slugify(value: Any) -> str
```

Return a filesystem-safe slug for IDs or filenames.

**Example:**
```python
slugify("Hello World!")  # "Hello_World_"
slugify("test@example.com")  # "test_example_com"
```

---

### `load_dotenv()`

```python
def load_dotenv() -> None
```

Populate environment variables from a .env file if present.

Searches for `.env` file in the following locations:
1. Path specified by `SURVEY_DOTENV_PATH` environment variable
2. Default location in converters directory

---

## Usage Examples

### Basic Programmatic Usage

```python
from pathlib import Path
from zopyx.surveyjs.converters import SurveyConverter

# Create converter instance
converter = SurveyConverter(
    data_path=Path("responses.json"),
    form_path=Path("form.json"),
    output_dir=Path("./output")
)

# Generate specific formats
paths = converter.run(formats={"pdf", "csv", "xlsx"})
print(f"Generated files: {paths}")
```

### Custom Item Processing

```python
from zopyx.surveyjs.converters import SurveyConverter, write_csv, build_table_rows

converter = SurveyConverter(data_path, form_path, output_dir)
entry = converter.load_first_entry()

# Get items directly
items, attachments = converter.collect_items(entry, "poll-123")

# Filter or modify items as needed
filtered_items = [item for item in items if item.field_type != "file"]

# Export filtered data
rows = build_table_rows(filtered_items)
write_csv(rows, Path("filtered.csv"))
```

### Building Custom Formats

```python
from zopyx.surveyjs.converters import (
    SurveyConverter, 
    build_markdown, 
    build_html,
    write_pdf
)

converter = SurveyConverter(data_path, form_path, output_dir)
entry = converter.load_first_entry()
items, attachments = converter.collect_items(entry, "poll-123")

# Build custom pipeline
markdown = build_markdown(items, "poll-123")
html_body = build_html(markdown, attachments)

# Add custom processing to HTML
html_body = html_body.replace("Survey response", "Custom Survey Report")

# Generate PDF
write_pdf(html_body, Path("custom.pdf"))
```

### Working with Attachments

```python
from zopyx.surveyjs.converters import SurveyConverter

converter = SurveyConverter(data_path, form_path, output_dir)
entry = converter.load_first_entry()
items, attachments = converter.collect_items(entry, "poll-123")

# Save attachments separately
saved = converter.save_attachments(attachments)
for path in saved:
    print(f"Saved: {path}")

# Filter image attachments
images = [att for att in attachments if att.is_image]
for img in images:
    data_url = img.data_url()
    print(f"Image data URL: {data_url[:50]}...")
```

---

## Error Handling

Common exceptions raised by the API:

| Exception | Cause | Handling |
|-----------|-------|----------|
| `ValueError` | Empty result payload, unknown format | Check input data validity |
| `TypeError` | Unexpected JSON structure | Verify data format |
| `FileNotFoundError` | Missing input files | Check file paths |
| `KeyError` | Missing schema elements | Ensure form schema matches data |

**Example:**
```python
from zopyx.surveyjs.converters import SurveyConverter, parse_formats

try:
    formats = parse_formats("pdf,invalid")
except ValueError as e:
    print(f"Invalid format: {e}")

try:
    converter = SurveyConverter(data_path, form_path, output_dir)
    paths = converter.run(formats={"pdf"})
except (ValueError, TypeError) as e:
    print(f"Conversion error: {e}")
```

---

# CSV Flattening Strategy for SurveyJS Nested/Dynamic Fields

## Executive Summary

The current converter implementation handles several SurveyJS field types that produce nested or dynamic data structures. For CSV export (which requires a flat, tabular format), these nested structures need a coherent flattening strategy. This document analyzes the current handling, identifies gaps, and proposes a comprehensive flattening approach.

---

## 1. Current Field Type Handling Analysis

### 1.1 Simple Fields (Flat)

These fields produce scalar values that are already CSV-compatible:

| Type | Current Output | CSV-Ready |
|------|----------------|-----------|
| `text` | Single string | Yes |
| `comment` | Single string | Yes |
| `boolean` | "Yes"/"No" | Yes |
| `dropdown` | Selected value | Yes |
| `radiogroup` | Selected value | Yes |
| `html` | Ignored | N/A |

### 1.2 Multi-Value Fields (Flattened)

These fields produce multiple values that are currently joined:

| Type | Data Structure | Current Handling | CSV Status |
|------|----------------|------------------|------------|
| `checkbox` | `["value1", "value2"]` | Joined with ", " | Loses granularity |
| `tagbox` | `["value1", "value2"]` | Joined with ", " | Loses granularity |
| `imagepicker` (multi) | Array of selections | Joined with ", " | Loses granularity |

**Problem:** Joining values loses the ability to analyze individual selections in CSV.

### 1.3 Nested Object Fields (Partially Handled)

| Type | Data Structure | Current Handling | CSV Status |
|------|----------------|------------------|------------|
| `matrix` | `{"row1": "col1", "row2": "col2"}` | Formatted as "Row: Col" strings | Human-readable but not analytically useful |
| `multipletext` | `{"item1": "value1", "item2": "value2"}` | JSON serialized | Poor CSV usability |
| `file` | Complex object/array | Extracted to attachments | Handled separately |

### 1.4 Dynamic Table Fields (Table Output)

| Type | Data Structure | Current Handling | CSV Status |
|------|----------------|------------------|------------|
| `matrixdynamic` | Array of row objects | Stored as `table` in Item | Best effort via `build_table_rows` |
| `paneldynamic` | Array of panel objects | JSON serialized | Not handled |

---

## 2. Specific Problems for CSV Export

### 2.1 The Matrix Problem

**Current Behavior:**
```json
{
  "Q11_Erfahrung": {
    "Wartezeiten": "3",
    "Arztbriefe_Information": "4"
  }
}
```

**Current CSV Output:**
```csv
Key,Field,Value
Q11_Erfahrung,"11. Experience",Wartezeiten: 3; Arztbriefe_Information: 4
```

**Issues:**
1. Values are concatenated in a single cell
2. Cannot perform numerical analysis (averages, counts)
3. Cannot filter by specific row values
4. Row labels mixed with values makes parsing difficult

### 2.2 The Checkbox/Tagbox Problem

**Current Behavior:**
```json
{
  "Q1_Fachrichtung": ["Kinder_und_Jugendmedizin", "Neurologie"]
}
```

**Current CSV Output:**
```csv
Key,Field,Value
Q1_Fachrichtung,"1. Specialty",Kinder_und_Jugendmedizin, Neurologie
```

**Issues:**
1. Cannot count occurrences of specific choices
2. Cannot filter rows by specific selections
3. Requires text parsing to analyze

### 2.3 The MatrixDynamic Problem

**Current Behavior:**
```json
{
  "Products": [
    {"name": "Widget", "price": "10", "qty": "5"},
    {"name": "Gadget", "price": "25", "qty": "2"}
  ]
}
```

**Current CSV Output:**
```csv
Key,Field,Value
Products,"Product List","[JSON string]"
```

**Issues:**
1. JSON in CSV cells is not analytically useful
2. Variable number of rows per response
3. Cannot aggregate across responses

---

## 3. Flattening Strategy Options

### 3.1 Strategy A: Wide Format (Column Expansion)

**Concept:** Expand nested structures into additional columns.

**Matrix Example:**
```csv
Q11_Erfahrung_Wartezeiten,Q11_Erfahrung_Arztbriefe_Information
3,4
```

**Pros:**
- Each value in its own cell
- Easy filtering and analysis
- Single row per response

**Cons:**
- Column explosion with many rows
- Variable columns between surveys
- Difficult for dynamic numbers of rows

**Best For:** Matrix questions with fixed, small number of rows

### 3.2 Strategy B: Long Format (Row Duplication)

**Concept:** Create multiple rows per response, duplicating static data.

**MatrixDynamic Example:**
```csv
ResponseID,Question,RowIndex,Column,Value
resp001,Products,1,name,Widget
resp001,Products,1,price,10
resp001,Products,2,name,Gadget
```

**Pros:**
- Handles any number of rows
- Consistent schema
- Easy aggregation with GROUP BY

**Cons:**
- Response data is duplicated
- More rows to process
- Requires ResponseID to reconstruct

**Best For:** Dynamic tables with variable row counts

### 3.3 Strategy C: Hybrid Approach (Type-Dependent)

**Concept:** Choose strategy based on field type characteristics.

| Field Type | Strategy | Rationale |
|------------|----------|-----------|
| `matrix` | Wide | Fixed rows, column-per-row |
| `multipletext` | Wide | Fixed items, column-per-item |
| `checkbox` | Wide (dummy columns) | Fixed choices, boolean columns |
| `matrixdynamic` | Long | Variable rows |
| `paneldynamic` | Long | Variable rows, complex content |

**Pros:**
- Optimized for each field type
- Maintains analytical usefulness
- Flexible

**Cons:**
- More complex implementation
- Different handling per type

### 3.4 Strategy D: Multiple CSV Files (Relational)

**Concept:** Create separate CSV files for main data and nested structures.

**Files:**
- survey_main.csv - Core response data
- survey_matrix.csv - Matrix answers
- survey_dynamic.csv - Matrixdynamic rows
- survey_attachments.csv - File metadata

**Pros:**
- Normalized data structure
- No duplication
- Handles any complexity
- Database-friendly

**Cons:**
- Multiple files to manage
- Requires joins for analysis
- More complex for end users

---

## 4. Recommended Implementation

### 4.1 Primary Recommendation: Hybrid + Optional Relational

**Core Approach (Hybrid):**

1. **Simple fields:** Single column (current behavior)
2. **Matrix/MultipleText:** Wide format (column per row/item)
3. **Checkbox:** Wide format with dummy/one-hot encoding
4. **MatrixDynamic:** Long format with RowIndex column
5. **PanelDynamic:** Long format or separate file

**Secondary Output (Relational):** Offer option to export as multiple normalized CSVs.

### 4.2 Detailed Field Handling

#### Matrix Questions -> Wide Format

**Input:**
```json
{"Q11": {"Wartezeiten": "3", "Arztbriefe_Information": "4"}}
```

**Output:**
```csv
Q11_Wartezeiten,Q11_Arztbriefe_Information
3,4
```

**Column Naming:** `{questionKey}_{rowValue}`

#### Checkbox Questions -> One-Hot Encoding

**Input:**
```json
{"Q1": ["OptionA", "OptionC"]}
```

**Output:**
```csv
Q1_OptionA,Q1_OptionB,Q1_OptionC
1,0,1
```

**Benefits:**
- Easy counting: SUM(Q1_OptionA)
- Easy filtering: WHERE Q1_OptionA = 1

#### MatrixDynamic -> Long Format

**Input:**
```json
{"Products": [{"name": "Widget", "price": "10"}, {"name": "Gadget", "price": "25"}]}
```

**Output:**
```csv
_ResponseID,_Question,_RowIndex,Products_name,Products_price
resp001,Products,0,Widget,10
resp001,Products,1,Gadget,25
```

### 4.3 Configuration Options

Export should be configurable:

```python
csv_options = {
    "format": "hybrid",           # "flat", "wide", "long", "relational"
    "matrix_style": "columns",    # "columns" or "rows"
    "checkbox_style": "onehot",   # "onehot" or "joined"
    "dynamic_style": "long",      # "long" or "json"
    "max_dynamic_rows": 10,       # Limit for wide format
    "include_metadata": True,     # ResponseID, timestamps
}
```

---

## 5. Migration Path

### Phase 1: Add Optional Wide Format for Matrix
- Add build_wide_rows() function
- Support matrix and multipletext types
- Keep default behavior unchanged

### Phase 2: Add Long Format for Dynamic
- Add build_long_rows() function
- Support matrixdynamic and paneldynamic
- Add ResponseID tracking

### Phase 3: Full Hybrid Implementation
- Combine both approaches
- Add configuration options
- Update CLI with format flags

### Phase 4: Relational Export (Optional)
- Add multi-file export option
- Add foreign key relationships
- Provide join documentation

---

## 6. Conclusion

The current CSV export is suitable for simple surveys but struggles with nested and dynamic data. A **hybrid flattening strategy** offers the best balance:

1. **Wide format** for matrix and checkbox (fixed choices)
2. **Long format** for dynamic tables (variable rows)
3. **Optional relational export** for complex analysis

This approach maintains backward compatibility while enabling powerful analytical use cases that are currently impossible with JSON-in-CSV cells.

The implementation should be phased, starting with matrix wide-format as the highest-impact, lowest-risk change.
