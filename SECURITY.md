# Security Policy and Abuse Mitigation

This document describes the security model and built-in measures to reduce abuse of SurveyJS forms in `zopyx.surveyjs`.

## Current implementation status

The submission-validation hardening is implemented on branch
`feature/submission-data-validation`. New `@@save-poll` data is validated and
normalized before `notify()`, persistence, mail actions, or configured external
POST actions.

Verified baseline:

- `bin/test -s zopyx.surveyjs`: 195 tests, 0 failures, 0 errors, 7 skips.
- `make test`: successful; 96 pytest tests passed.
- Ruff and `git diff --check`: successful.

The seven remaining skips are documented publisher-/ZCML-level security cases
that cannot be meaningfully exercised through direct `TestRequest` calls.

## Scope

Threats addressed here focus on form/survey abuse and data integrity risks during submission:
- Oversized payloads that exhaust resources.
- Invalid or malicious submissions that bypass client-side validation.
- Misuse of submission endpoints (spam, automation, or exfiltration via POST actions).

## Built-in Mitigations

### Max payload size (per survey)

Each Survey has a configurable maximum payload size in megabytes (`Max size payload (MB)`). When a submission exceeds this limit, the request is rejected with HTTP 413.

Recommended:
- Keep the default (1 MB) for most forms.
- Increase only when required by the form structure.

The limit is enforced before JSON parsing. The validator also applies separate
file-size and file-count limits.

### Client-side validation (SurveyJS)

SurveyJS runs validation in the browser based on the form schema (required fields, regex, min/max, and other rules). This improves user feedback but must not be relied on for security, because clients can bypass it.

Recommended:
- Define validation rules in the SurveyJS schema.
- Treat client-side validation as usability, not as a security boundary.

### Submission validation and normalization

In addition to optional SurveyJS schema validation, the Python submission
boundary applies these checks to new submission data:

- top-level JSON object shape, required values and schema-dependent fields;
- dangerous markup, event-handler attributes, control characters and unsafe
  URL schemes;
- structured file names, Unicode NFC normalization, MIME allowlist
  membership, valid Base64 data URLs, MIME consistency and magic bytes;
- SVG and `application/octet-stream` rejection by default;
- file count, file size and total payload limits.

Only the normalized copy is passed onward; the original payload is not mutated.
Validation failures use deterministic JSON error codes and warning logging
without recording submission contents or secrets. Rejected submissions do not
reach subscribers or storage. Single-use embed/trusted tokens are consumed
only after validation succeeds.

See `docs/submission-validation.rst` for the contract and
`SUBMISSION_VALIDATION_REQUIREMENTS.md` for the requirement mapping.

### Server-side schema validation (optional)

Two server-side validation paths are available:

- **Enable validation (experimental)**: a Python validator that checks the submission against the form schema. The submission hardening layer above is independent of this option.
- **Force Server Side Validation**: runs a compiled SurveyJS validator binary (Deno) for every submission. This mirrors SurveyJS' own validation engine and is the most reliable option.

Recommended:
- Enable the external validator for forms that require strict validation.
- Ensure the Deno binary is present next to the validation module and kept up-to-date.
- See `docs/installation.rst` for build and usage details.

## Operational Guidance

To reduce abuse and increase reliability:

- **Use HTTPS** for all endpoints, including POST actions.
- **Restrict POST endpoints** to trusted services; validate payloads on the receiver side as well.
- **Add rate limiting** at the reverse proxy or WAF (not implemented in this package).
- **Monitor logs** for repeated failures or unusually large payload sizes.

## Remaining security work

The submission hardening does not resolve unrelated findings. Separate review
items include CSRF enforcement directly inside the public JSON view versus a
publisher-level functional test, SSRF controls for configured
`post_endpoint_url` values, output encoding for stored values rendered by
result views, rate limiting, quotas, bot controls, dependency pinning and key
rotation.

## Reporting

Security issues should be reported directly to the maintainer:

- Andreas Jung | info@zopyx.com
