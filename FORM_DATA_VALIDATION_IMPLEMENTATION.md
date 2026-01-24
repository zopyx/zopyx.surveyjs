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
Use the SurveyJS external validator via:
- `src/zopyx/surveyjs/data_validation/validate_data.py`

API:
- `validate_data(schema_json, form_json, result_json) -> int`

The output JSON includes:
- `valid: bool`
- `errors: list`

### 2) Validation Flow in `save_poll`
1. Parse JSON payload.
2. Fetch latest form JSON.
3. Write schema + payload to temporary JSON files.
4. Run `validate_data(...)` and parse result JSON.
5. If invalid: return `400` with details.
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

1) **Use SurveyJS validator**
- Run `validate_data(...)` with schema + payload files.
- Parse result JSON and surface error details.

2) **Integrate into save_poll**
- Validate payload before `notify`.
- Return JSON error response with reason code + field name.

3) **Add per-form settings** (optional)
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
