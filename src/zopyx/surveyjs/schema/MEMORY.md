Working notes for this task:

- Converter script: `conver_result.py` reads `survey-data-form.json`, uses `survey-form-form.json` for labels, and outputs `output/<poll_id>.{txt,md,html,pdf,csv,xlsx}` plus saved attachments.
- Attachments: extracted to `output/`; images are referenced in Markdown, inlined as data URLs for HTML/PDF (PDF images capped at 75% width), and listed in text/CSV/XLSX.
- Poll ID is derived from outer survey data (`poll_id`/`pollId`/`id`) with fallback to the inner result object; defaults to `sample` slug.
- uv script header includes deps: `markdown2`, `weasyprint`, `openpyxl`; WeasyPrint needs system libs (cairo/pango/etc.).
