# PDF Form Import Functionality

This document describes the **PDF Form Import** feature as implemented in the current codebase. It covers the UI flow, the data submitted by the forms, the preview experience, and the backend conversion workflow (PDF → PNG → LLM + pdfcpu metadata) that produces SurveyJS JSON.

## Overview

The PDF Form Import feature lets users upload a PDF form and automatically convert it into a **SurveyJS JSON** definition. The conversion combines:

- **Visual extraction** via rendering PDF pages into PNGs and sending them to an LLM.
- **Structural hints** via `pdfcpu form export` which extracts form field metadata as JSON.

These two signals are fused in a single prompt to improve layout and field mapping accuracy.

## User Interface

The main UI for the importer lives in the **PDF Importer** view (template: `src/zopyx/surveyjs/browser/pdf_importer.pt`, JS: `src/zopyx/surveyjs/browser/static/pdf_importer.js`, CSS: `src/zopyx/surveyjs/browser/static/pdf_importer.css`).

### Upload Form

The upload form consists of:

- **PDF file input** (`name="pdf_file"`, required)
- **Additional prompt** textarea (`name="additional_prompt"`, optional)
- **Convert PDF** submit button

The “Additional prompt” field lets users inject extra instructions into the AI prompt. This is useful for emphasizing layout constraints, field naming rules, or domain-specific expectations.

### Status and Buttons

- A status alert displays success or error messages.
- The “Store converted form as new version” button is hidden/disabled until conversion succeeds.

### Preview Panel

The UI shows two previews side-by-side:

- **PDF Preview**
  - An `<iframe>` displays the uploaded PDF.
  - Placeholder text is shown when no file is selected.

- **SurveyJS Preview**
  - The generated SurveyJS JSON is rendered with SurveyJS runtime.
  - Placeholder text is shown until conversion completes.

## Frontend Flow

The JavaScript in `pdf_importer.js` drives the UI flow:

1. **File selection**
   - When a PDF is selected, the preview iframe loads it using `URL.createObjectURL`.

2. **Submit conversion**
   - The form posts to `@@import-pdf-form` with:
     - `pdf_file` (binary PDF)
     - `additional_prompt` (optional text)
     - `_authenticator` (CSRF token)

3. **Handle response**
   - On success, the JSON is rendered in the SurveyJS preview.
   - The “Store converted form” button becomes active.

## Backend Workflow

The backend endpoint `import_pdf_form()` is implemented in:

- `src/zopyx/surveyjs/browser/views.py`

The method performs the following pipeline:

### 1) Validate Upload

- The request must include `pdf_file`.
- If missing, it returns HTTP **400** with JSON error payload.

### 2) Create Temporary Workspace

- A `TemporaryDirectory()` is created for intermediate artifacts.
- Files are cleaned up automatically when the request finishes.

### 3) Persist Uploaded PDF

- The uploaded binary content is written to:
  - `uploaded.pdf`

### 4) Render PDF → PNG (all pages)

- ImageMagick `convert` renders all pages into PNGs:

  ```
  convert -density 300 uploaded.pdf -background white -alpha remove -alpha off uploaded.png
  ```

- This generates one PNG per page (e.g. `uploaded-0.png`, `uploaded-1.png`, …).
- All generated PNGs are collected via `uploaded*.png`.

### 5) Extract Form Metadata (pdfcpu)

- The PDF is passed to the `PDFFormExtractor` class in:
  - `src/zopyx/surveyjs/pdf_form_extract.py`

- The extractor runs:

  ```
  pdfcpu form export uploaded.pdf <tempfile.json>
  ```

- The exported JSON is read back and written to:
  - `forms.json`

This JSON represents the PDF’s form field structure and values (if present).

### 6) Build the LLM Prompt

A base prompt is used:

- “Convert this PDF to SurveyJS JSON. Keep the layout, keep headers and footer, make JSON as close possible as possible, return the form JSON only”

If the **Additional prompt** field is provided, it is appended as:

- `Additional instructions: …`

Finally, the extracted form JSON is injected into the prompt in a triple-quoted block:

```
... Here is the form represenation of the form as JSON:
"""
```
<forms.json content>
```
"""
```

This gives the LLM explicit structural hints while still relying on the PNG images for layout accuracy.

### 7) Send to LLM with PNG Attachments

The function `generate_survey_json_from_assets()` (in `ai_generator.py`) is called with:

- All PNG page paths as **image attachments**
- The augmented prompt (including `forms.json` text)

The LLM returns a SurveyJS JSON string.

### 8) Normalize and Parse JSON

- Any markdown wrapping is removed with `strip_markdown_json()`.
- The JSON is parsed with `orjson`.
- The result must be an object; otherwise it fails.

### 9) Return Result

On success:

```json
{
  "success": true,
  "json": { /* SurveyJS form */ }
}
```

## Error Handling

Common failure cases:

- Missing file → 400
- ImageMagick `convert` missing or fails → 500
- `pdfcpu` missing → 500
- LLM response is invalid JSON → 500
- Unexpected errors → 500

Errors are returned as JSON with a short message and additional detail when available.

## Summary

The PDF Form Import workflow combines **PDF page rendering** and **structured PDF form metadata** to produce a high-quality SurveyJS JSON conversion. The UI provides a two-panel preview experience, while the backend ensures a controlled, reproducible conversion pipeline that can be tuned via the optional “Additional prompt.”
