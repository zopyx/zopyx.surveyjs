# PDF Form Import

This document describes the PDF Form Import feature and is split into two sections: **User Guide** and **Technical Reference**.

## User Guide

### What it does

The PDF Form Import feature lets you upload a PDF form and automatically generate a SurveyJS form from it. It combines visual analysis of the PDF pages with extracted form field metadata to produce a form that matches the layout and structure of the original document.

### Where to find it

Open the **PDF Form Import** view in your survey and you will see:

- An upload panel for the PDF.
- A preview panel for both the PDF and the generated SurveyJS form.
- A small **DOCS** badge linking to the official documentation.

### How to use it

1. **Upload a PDF**
   - Click the file picker and select a PDF.
   - The PDF preview will appear on the right.

2. **(Optional) Add additional instructions**
   - Use the **Additional prompt** text field to provide guidance (e.g. required wording, layout constraints, field naming conventions).

3. **Convert PDF**
   - Click **Convert PDF** to start the conversion.
   - A progress spinner appears while the conversion runs.

4. **Preview and validate**
   - The generated SurveyJS form is rendered in the preview panel.
   - Review it for accuracy.

5. **Store the result**
   - Click **Store converted form as new version** to save it as a new version of the survey.

### Troubleshooting tips

- **No preview or errors:** Make sure the PDF is valid and readable.
- **Conversion errors:** Verify the system has ImageMagick (`convert`) and `pdfcpu` installed.
- **Unexpected layout:** Add clarifying instructions in “Additional prompt” and try again.

## Technical Reference

### Key files

- Template: `src/zopyx/surveyjs/browser/pdf_importer.pt`
- JavaScript: `src/zopyx/surveyjs/browser/static/pdf_importer.js`
- Styles: `src/zopyx/surveyjs/browser/static/pdf_importer.css`
- Backend view: `src/zopyx/surveyjs/browser/views.py` (`import_pdf_form()`)
- PDF form extraction: `src/zopyx/surveyjs/pdf_form_extract.py`
- LLM integration: `src/zopyx/surveyjs/browser/ai_generator.py`

### UI components

**Upload form**

- `pdf_file` (required): PDF upload
- `additional_prompt` (optional): extra instructions appended to the LLM prompt

**Preview area**

- PDF preview in `<iframe>`
- SurveyJS preview rendered from returned JSON

### Conversion workflow (backend)

The `@@import-pdf-form` endpoint performs the following steps:

1) **Read upload**
   - Reads `pdf_file` as bytes.

2) **Temporary workspace**
   - Creates a `TemporaryDirectory()` for all artifacts.

3) **Write PDF to disk**
   - Saves to `uploaded.pdf` in the temp dir.

4) **Convert PDF → PNG (all pages)**
   - Uses ImageMagick `convert`:

     ```
     convert -density 300 uploaded.pdf -background white -alpha remove -alpha off uploaded.png
     ```

   - Produces one PNG per page (e.g. `uploaded-0.png`, `uploaded-1.png`).

5) **Extract form metadata with pdfcpu**
   - `PDFFormExtractor` runs:

     ```
     pdfcpu form export uploaded.pdf <tempfile>.json
     ```

   - Raw JSON is written to `forms.json`.

6) **Build LLM prompt**
   - Base prompt:
     - “Convert this PDF to SurveyJS JSON. Keep the layout, keep headers and footer, make JSON as close possible as possible, return the form JSON only”
   - If `additional_prompt` is present, it is appended as:
     - `Additional instructions: ...`
   - The extracted form JSON is embedded into the prompt in a triple-quoted block.

7) **Send to LLM**
   - `generate_survey_json_from_assets()` is called with:
     - All PNGs as image attachments
     - The prompt containing the embedded `forms.json`

8) **Normalize + parse JSON**
   - Markdown is stripped with `strip_markdown_json()`.
   - JSON is parsed with `orjson` and must be a dict/object.

9) **Return response**

   ```json
   {
     "success": true,
     "json": { /* SurveyJS form */ }
   }
   ```

### Error handling

Typical errors and their causes:

- **400**: Missing `pdf_file`.
- **500**: ImageMagick `convert` missing or failed.
- **500**: `pdfcpu` missing or failed.
- **500**: LLM returned invalid JSON.
- **500**: Unexpected server error.

### Dependencies

- **ImageMagick** (`convert`) must be in `PATH`.
- **pdfcpu** must be in `PATH`.
- **llm** module must be installed and configured.

