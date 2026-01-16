# Form Data Validation — Implementation Proposal

## Scope
Implement **strict server-side validation** for SurveyJS submissions in this add-on. Validation is schema-driven, rejects unknown or malformed data, enforces tight size/type limits, and runs **before** any storage or downstream actions.

---

## Where to Validate
- **Primary enforcement**: `Views.save_poll` in `src/zopyx/surveyjs/browser/views.py`.
- **Secondary enforcement** (defense-in-depth): before export, email, or POST actions in subscribers (optional if primary is strict).

---

## Architecture

### 1) Validation Module
Create a new module, e.g.:
- `src/zopyx/surveyjs/validation.py`

Exported functions:
- `build_schema_index(form_json) -> SchemaIndex`
- `validate_submission(schema_index, payload) -> ValidationResult`
- `validate_attachments(payload, limits) -> ValidationResult`

`ValidationResult`:
- `ok: bool`
- `status: int`
- `reason: str`
- `field: str | None`
- `details: dict`

### 2) Schema Index
Precompute a flat map of questions by `name`:
- type (text, checkbox, file, matrix, panel, etc.)
- choices / allowed values
- required flag
- min/max / length constraints
- max selections
- file constraints

Handle nested structures (panel, matrix) by flattening into field paths or by recursive validators.

### 3) Validation Flow in `save_poll`
1. Parse JSON payload.
2. Fetch latest form JSON.
3. Build schema index.
4. Validate submission.
5. If invalid: return `400` / `413` with reason code.
6. If valid: proceed with normal flow.

---

## Limits and Defaults
Set global defaults in a single place (config or registry), with optional per-form overrides:

```
MAX_REQUEST_BYTES = 2_000_000
MAX_JSON_BYTES = 1_000_000
MAX_TEXT_LENGTH = 2_000
MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_BYTES = 2_000_000
MAX_TOTAL_ATTACHMENT_BYTES = 5_000_000
MAX_CHOICES = 50
```

Enforce in order: **request size → JSON size → schema validation**.

---

## Enforcement Strategy
- **Unknown field** → reject (strict mode).
- **Missing required field** → reject.
- **Type mismatch** → reject.
- **Out-of-range / invalid choice** → reject.
- **Attachment limits exceeded** → reject.
- **Invalid base64** → reject.

HTTP responses:
- `400 Bad Request` for structural/type violations.
- `413 Payload Too Large` for size violations.
- `422 Unprocessable Entity` for semantic mismatch (optional).

---

## Suggested Implementation Steps

1) **Add validation module**
- Implement strict validators for: text, comment, number, rating, boolean, date, choice, checkbox, matrix, panel, file.
- Add helper: `normalize_value` for date/number conversions.

2) **Integrate into save_poll**
- Validate payload before `notify`.
- Return JSON error response with reason code + field name.

3) **Add per-form settings** (optional)
- `validation_enabled` (default true for public forms).
- Override limits for large enterprise forms.

4) **Add tests**
- Valid submission passes.
- Unknown field rejected.
- Oversized attachment rejected.
- Wrong type rejected.

---

## Logging & Privacy
- Log only: reason code, field name, size metrics, submission ID hash.
- Do **not** store full rejected payloads by default.

---

## Compatibility & Rollout
- Start with **strict mode** for public forms only; allow fallback for authenticated workflows if needed.
- Document limits in admin UI.

---

## Open Questions
- Do we accept submissions with missing optional fields? (likely yes)
- Should HTML content be entirely disallowed in text fields? (default: yes)
- Are file uploads expected in public forms? If not, disable by default.

