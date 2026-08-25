# Security Policy and Abuse Mitigation

This document describes the security model and built-in measures to reduce abuse of SurveyJS forms in `zopyx.surveyjs`.

## Current implementation status

New `@@save-poll` data is validated and normalized before `notify()`,
persistence, mail actions, or configured external POST actions. This is the
pre-validation boundary for new submissions.

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

The pre-validation pipeline runs after request/access checks and before any
event or side effect. Its order is deliberate:

1. **Transport limits.** The request `Content-Length` and the actual request
   body are checked against the survey's maximum payload size. Oversized input
   is rejected with HTTP 413 before JSON parsing. This prevents large bodies
   from reaching parsing, validation or downstream actions.
2. **JSON and top-level shape.** The `pollResult` value must be valid JSON and
   its top-level value must be an object. Arrays, strings, numbers and `null`
   are rejected; nested values are copied recursively and restricted to JSON
   scalar, list and object types.
3. **Schema field boundary.** Field names are collected from the active form
   schema. Unknown top-level fields and orphaned comment fields are rejected.
   SurveyJS comment suffixes remain supported through the configured
   `commentPrefix`. The optional `missing_required` check remains implemented
   but is disabled by default for compatibility; callers can explicitly enable
   it with `enforce_required_fields=True`.
4. **Text safety.** Strings are checked recursively for control characters,
   dangerous `javascript:` and `vbscript:` URL schemes, whitespace/control
   character obfuscation, and dangerous markup. Script, SVG, iframe, object
   and embed elements plus `on*=` event-handler attributes are rejected.
   Safe ordinary text containing comparison characters such as `<` is retained.
5. **Data-URL safety.** Text-field data URLs are restricted to Base64 PNG or
   JPEG images. The Base64 encoding is syntactically decoded with strict
   validation; unsupported MIME types and malformed data URLs are rejected.
6. **File structure.** File values must use the expected list/object shape and
   string-valued filename, MIME type and content members. Unknown file members
   are ignored in the normalized result rather than persisted.
7. **Filename safety.** Filenames are normalized to Unicode NFC before length
   and character checks. Path separators, traversal patterns, control
   characters, quotes and markup-oriented characters are rejected, while
   legitimate international filenames remain supported.
8. **MIME and content validation.** A restrictive MIME allowlist is enforced.
   SVG and `application/octet-stream` are rejected by default. The declared
   MIME type must match the data URL MIME type, and decoded content must match
   the expected magic bytes for PNG, JPEG, GIF, WebP, PDF, RTF, ZIP and Office
   formats. MIME declarations alone are never trusted.
9. **Resource limits.** File count, decoded file size and overall payload
   limits are enforced independently. This prevents an attacker from evading
   the request limit through many individually small files.
10. **Canonical hand-off.** A normalized deep copy is returned. The original
    caller-owned payload is not mutated. Only this normalized copy is passed to
    optional external SurveyJS validation and, if successful, to notification,
    storage and post-submit actions.

Every failed step raises a deterministic validation error with a stable error
code and optional field name. The request returns a client-safe JSON error,
logs a warning and stops immediately. Submission contents, tokens, secrets and
credentials are not written to the validation log. Because validation occurs
before `notify()`, rejected data cannot trigger subscribers, mail delivery,
external POSTs or persistence. Single-use embed/trusted tokens are consumed
only after validation succeeds, so malformed input does not burn a valid
token.

See `docs/validation.rst` for the complete validation contract and
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
