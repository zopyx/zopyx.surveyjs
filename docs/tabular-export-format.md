# Tabular Export Format

## Goal

SurveyJS responses need two things at the same time:

- a lossless machine-readable representation
- an Excel-friendly representation for analysts and office workflows

A single flat CSV cannot do both once the survey contains nested, repeated, or file-like fields. The export format therefore uses one canonical JSON representation and a related tabular bundle.

## Canonical Representation

The canonical representation is the source of truth. It preserves real types and separates attachments from answers.

```json
{
  "response_id": "18c90d5c-2de4-11f1-8fbb-9d6e50e05304",
  "survey_id": "survey-form-09075e2a",
  "submitted_at": "2026-04-01T16:01:51.681928Z",
  "submitted_by": "admin2",
  "answers": {
    "singleLineText": "Sample text",
    "numberField": 42,
    "checkboxField": ["a", "c", "b"],
    "matrixField": {
      "quality": "poor",
      "price": "good"
    },
    "matrixDropdownField": {
      "service": {"rating": "4", "comment": "Great service"},
      "product": {"rating": "5", "comment": "Excellent product"}
    },
    "dynamicPanelField": [
      {"itemName": "First Item", "itemValue": 100},
      {"itemName": "abc", "itemValue": 5}
    ]
  },
  "attachments": {
    "fileUploadField": [
      {
        "asset_id": "fileUploadField-1",
        "filename": "1004_2026-04-01_UNIV_59.pdf",
        "mime_type": "application/pdf",
        "kind": "file"
      }
    ],
    "signatureField": [
      {
        "asset_id": "signatureField-1",
        "filename": "signatureField.png",
        "mime_type": "image/png",
        "kind": "signature"
      }
    ]
  }
}
```

## Tabular Bundle

The tabular export is a set of related tables. They can be written as separate CSV files or as one `.xlsx` workbook with multiple sheets.

### `responses_wide`

One row per response. Only scalar and fixed-shape values become columns.

Included:

- scalar questions such as `text`, `comment`, `dropdown`, `rating`, `boolean`, `imagepicker`
- fixed `matrix` rows as `question__row`
- fixed `multipletext` items as `question__item`
- fixed `matrixdropdown` cells as `question__row__column`

Excluded from wide columns:

- `checkbox`, `tagbox`, `ranking`
- `paneldynamic`, `matrixdynamic`
- `file`, `signaturepad`
- display-only elements such as `html`

### `answers_long`

One row per atomic answer value.

Columns:

- `response_id`
- `survey_id`
- `submitted_at`
- `submitted_by`
- `question_key`
- `question_title`
- `question_type`
- `path`
- `repeat_index`
- `item_index`
- `row_key`
- `row_label`
- `column_key`
- `column_label`
- `value_type`
- `value_json`
- `display_value`

Examples:

- `checkboxField[1]`
- `matrixField.quality`
- `matrixDropdownField.product.comment`
- `dynamicPanelField[2].itemValue`

### `attachments`

One row per file-like asset.

Columns:

- `response_id`
- `survey_id`
- `submitted_at`
- `submitted_by`
- `question_key`
- `question_title`
- `question_type`
- `item_index`
- `asset_id`
- `filename`
- `mime_type`
- `size_bytes`
- `storage_path`
- `sha256`
- `kind`

### `schema`

A field dictionary for analysts and downstream processors.

Columns:

- `question_key`
- `question_title`
- `question_type`
- `column_name`
- `path_pattern`
- `choice_value`
- `choice_label`
- `row_key`
- `row_label`
- `column_key`
- `column_label`

## Type Rules

| SurveyJS type | Export rule |
| --- | --- |
| `text`, `comment`, `radiogroup`, `dropdown`, `rating`, `boolean`, `imagepicker` | scalar in `responses_wide`, one row in `answers_long` |
| `checkbox`, `tagbox`, `ranking` | one row per selected value in `answers_long`, preserve order in `item_index` |
| `matrix` | one column per row in `responses_wide`, one atomic row per cell in `answers_long` |
| `multipletext` | one column per item in `responses_wide`, one atomic row per item in `answers_long` |
| `matrixdropdown` | one column per fixed row/column pair in `responses_wide`, one atomic row per cell in `answers_long` |
| `paneldynamic`, `matrixdynamic` | long-form only, preserve repeat order in `repeat_index` |
| `file`, `signaturepad` | references in `answers_long`, metadata in `attachments` |
| `html` | kept in `schema`, not exported as answer data |

## Naming Rules

- Use SurveyJS `name` as the stable key.
- Use `__` to build wide column names.
- Use dot and bracket notation for `answers_long.path`.
- Keep dates and datetimes in ISO form.
- Keep raw choice values in answer tables.
- Put human labels in `schema` and `display_value`.

## Legacy `fields[]` Payloads

The repository already contains a legacy result shape with this pattern:

```json
{
  "poll_id": "...",
  "creator": "...",
  "created": "...",
  "fields": [
    {"key": "checkboxField", "values": ["a, c, b"]}
  ]
}
```

That shape is already lossy for some question types. The new exporter accepts it and performs best-effort recovery using the form schema:

- comma-separated legacy values are split for multi-select fields
- matrix prose like `Quality: Poor` is mapped back to row and choice keys
- JSON strings are parsed back into dict or list values when possible
- signature data URLs become attachment rows

This best-effort path is useful for migration and offline analysis, but the canonical representation above is the preferred storage format going forward.

## Output Options

The implementation in this repository supports:

- canonical JSON output
- a CSV bundle with `responses_wide.csv`, `answers_long.csv`, `attachments.csv`, and `schema.csv`
- a standalone Excel workbook with matching sheet names
