# Security Policy and Abuse Mitigation

This document describes the security model and built-in measures to reduce abuse of SurveyJS forms in `zopyx.surveyjs`.

## Current implementation status

New `@@save-poll` data is validated and normalized before `notify()`,
persistence, mail actions, or configured external POST actions. This is the
pre-validation boundary for new submissions.

Verified baseline:

- `bin/test -s zopyx.surveyjs`: 472 tests, 0 failures, 0 errors, 75 skips
  (66 database-container tests that require `RUN_DB_CONTAINER_TESTS=1` plus
  Docker, 2 subprocess-race tests, 7 documented publisher-/ZCML-level
  security cases that cannot be meaningfully exercised through direct
  `TestRequest` calls).
- `make test`: successful; the Plone-free subset (converters, schema,
  validator wrapper) adds 115 passing pytest tests with 100 % coverage of
  `converters/`.
- Ruff and `git diff --check`: successful (13 pre-existing Ruff findings in
  untouched files are known and not release blockers).

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

### Submission rate limiting

`@@save-poll` meters every attempt per survey and client address before any
parsing (fixed one-minute and one-hour windows in the configured KV store). A
request over the limit is answered with `429 rate_limited` and a `Retry-After`
header and is not stored; a request that cannot be metered (KV store
unavailable) is refused with `503 rate_limit_unavailable` instead of being
admitted. Buckets key on `REMOTE_ADDR`, or on the right-most
`X-Forwarded-For` entry when `submission_rate_limit_trust_proxy` is enabled
behind a trusted reverse proxy. Configure via the `submission_rate_limit_*`
records in the "Security" fieldset (see `docs/security.rst`).

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
- **Add rate limiting** in front of the built-in limiter (reverse proxy or WAF): the package enforces per-survey, per-client limits itself (`submission_rate_limit_*` in the Security fieldset), an edge limit still helps against traffic that never reaches Plone.
- **Monitor logs** for repeated failures or unusually large payload sizes.

## Remaining security work

The submission hardening does **not** resolve unrelated findings. The
following items were verified against the current source and are known,
unfixed and accepted for the 1.0 beta. Each one must either be fixed or
re-accepted explicitly in the release notes of a subsequent release.

| # | Item | Where | Impact | Recommendation |
|---|------|-------|--------|----------------|
| 1 | **SSRF through a survey's `post_endpoint_url`** — an editor can point a survey at any reachable host, and submission data is POSTed there | `content/survey.py` (`post_endpoint_url`), used by `browser/views.py`, `browser/survey_results.py`, `subscribers.py` | Server-side requests to internal services and cloud metadata endpoints (credential theft, data exfiltration) | Allowlist the target hosts, or at least reject private/link-local addresses; restrict the field to `Manager` |
| 4 | **Exports are not audited** — CSV/JSON/XLSX downloads leave no trace | `converters/`, export views | Data exfiltration without forensic evidence | Write an audit record per export |
| 5 | **Token store**: `generate_tokens()` has no upper bound; `has_token()`/`invalidate()` are separate read-then-write steps | `adapters/token_store.py` | Unbounded ZODB growth; a token can be accepted twice under concurrency | Cap the batch size; make check-and-consume atomic |
| 6 | **Key handling**: no minimum length for the HMAC signature key, no key rotation | `security.py` (`_sign`), `browser/services/auth.py` | Weak keys, permanent compromise after a leak | Enforce a 32-byte minimum and implement rotation with a grace period |
| 7 | **No session binding for issued tokens** | `security.py`, `browser/services/auth.py` | A stolen token is valid from any client | Bind tokens to a session/user claim |
| 8 | **Container image**: runs as root on an unpinned base image | `Dockerfile` (`FROM ubuntu:24.04`, no `USER`) | Container escape escalates to root; non-reproducible base | Add a `USER`, pin the base image by digest |
| 9 | **Dependency pinning**: 22 of 26 runtime dependencies have no version bounds | `setup.py` (`install_requires`) | Non-reproducible installs, silent breaking upgrades | Add upper bounds/constraints for the runtime set |
| 10 | **Bot controls and quotas** — no honeypot, no per-survey submission quota | submission path | Spam submissions consume storage | Honeypot field or proof-of-work; quota per survey |
| 12 | **CSRF enforcement inside the public JSON view** | `views.py` (`save_poll`) | Cross-site submissions | Enforce at the view level, cover it with a publisher-level test |

Fixed after this list was written (1.0b4, security review of 2026-09-23):
**no rate limiting** (#2 — `ratelimit.py`, HTTP 429/503 on `@@save-poll`),
**CSV/XLSX formula injection** (#3 — `converters/spreadsheet.py`) and
**output encoding of stored values rendered by result views** (#11 —
`converters/sanitize.py`, allow-list sanitization of the generated result
HTML). Direct-embed tokens are now also bound to their survey
(`survey_mismatch` / `direct_embedding_not_enabled`).

The submission-validation layer documented above is independent of this list
and does not mitigate items 1–12.

## Reporting

Security issues should be reported directly to the maintainer:

- Andreas Jung | info@zopyx.com
