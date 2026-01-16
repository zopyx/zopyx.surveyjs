# Server-Side Form Data Validation Proposal

## Objectives
- Reject malformed or abusive submissions **before** they reach storage or outbound actions.
- Enforce **strong, explicit constraints** on shape, size, and type of incoming data.
- Use the **SurveyJS form JSON** as the authoritative schema for validation.
- Prevent data poisoning, resource exhaustion, and unexpected data types.

## Principles
- **Fail closed**: any unknown field or unsupported value type is rejected.
- **Deterministic limits**: hard caps on payload size, per-field size, and total attachments.
- **Schema-driven**: each answer validated against its question definition.
- **Defense-in-depth**: validate at input, at conversion, and before export/post.

---

## Validation Pipeline (Strict)

### 1) Transport-Level Limits
- **Max request size**: enforce at web server / app level (e.g. 1–5 MB).
- **Max JSON size**: reject if parsed JSON exceeds cap.
- **Reject compressed bombs**: disable or limit compression on submit endpoints.

### 2) JSON Parsing & Shape Validation
- Require top-level object (not list/string).
- Reject duplicate keys during parse (use strict JSON parser if possible).
- Normalize encoding to UTF‑8; reject invalid sequences.

### 3) Schema Resolution
- Load latest SurveyJS form JSON (the published version).
- Precompute a **flat field index** by question name with:
  - expected type
  - constraints (min/max, choices, regex, length)
  - allow multiple vs single
  - file/media constraints

### 4) Field-by-Field Validation (Hard Reject)
For each key in submission:
- **Unknown field** → reject.
- **Type mismatch** → reject.
- **Value out of bounds** → reject.
- **Length/size exceeded** → reject.

If a required field is missing → reject.

### 5) Attachment and Binary Validation
- Enforce **hard caps** for:
  - total attachment count
  - per-file size
  - total binary size across submission
- Reject unsupported MIME types and extensions.
- Validate base64 payloads strictly:
  - valid base64
  - decoded size matches metadata
  - no embedded data URIs if disabled
- Optionally scan with AV (if available) before storage/forwarding.

### 6) Post-Validation Sanitization
- Normalize numeric formats (int/float).
- Trim whitespace for strings where appropriate.
- Normalize date/time to ISO 8601, reject invalid dates.
- Normalize booleans to true/false.

---

## Strong Validation Rules by Question Type

### Text / Comment
- **Type**: string only.
- **Max length**: e.g., 2,000 chars.
- **Reject**: control chars (except newline/tab), excessive markup.
- Optional: allowlist for HTML (default: disallow HTML).

### Numeric / Rating
- **Type**: number.
- **Range**: must match min/max from schema.
- **Precision**: limit decimal places.

### Boolean
- **Type**: boolean only (reject string "true").

### Date / DateTime
- **Type**: string in ISO format.
- **Range**: optional min/max.
- Reject invalid or ambiguous formats.

### Choice / Dropdown / Radiogroup
- **Type**: string (single) or list (multi).
- **Values**: must be in allowed choices list.
- **Max selections**: enforce if defined.

### Matrix / Panel / Complex
- Validate nested structure recursively.
- Enforce max rows/columns.
- Reject extra keys or unexpected nesting.

### File Upload
- **Structure**: list of file entries.
- **Per-file**: name, size, mime, content (optional).
- Enforce total size caps and MIME allowlist.

---

## Global Limits (Suggested Defaults)
- Max request body: 2 MB
- Max JSON size: 1 MB
- Max text field length: 2,000 chars
- Max choice selections: 50
- Max attachments: 5
- Max attachment size: 2 MB per file
- Max total binary size: 5 MB

All limits should be configurable per form and globally.

---

## Enforcement Outcomes
- **400 Bad Request** for schema or type violations.
- **413 Payload Too Large** for size limits.
- **422 Unprocessable Entity** for semantic mismatch (optional).
- Log minimal rejection reason code + field name.

---

## Audit & Telemetry
- Record:
  - rejection reason code
  - field name
  - size metrics
  - submission ID hash
- Do **not** store full rejected payload by default (privacy).

---

## Implementation Hooks (Plone Add-on)
- Validate in `save_poll` **before** calling `notify`.
- Validation library in `zopyx.surveyjs.validation`:
  - `build_schema_index(form_json)`
  - `validate_submission(schema_index, payload)`
  - `validate_attachments(payload)`
- Optional: reuse SurveyJS schema definitions if available.

---

## Security Considerations
- Fail closed for unknown fields.
- Rate-limit repeated validation failures.
- Ensure any conversion/export also re-checks size and type.

---

## Open Questions
- Should strict validation be **default on** for public forms?
- Do we allow raw HTML answers at all?
- Should binary submission be supported in this add-on or offloaded?

