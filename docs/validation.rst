===========
Validation
===========

Survey submissions can be validated **server-side** with SurveyJS's own
validation engine, compiled into a small standalone binary. This is the
counterpart to the client-side validation that SurveyJS performs in the
browser — the browser checks improve the user experience, the server check
is the security boundary (client-side validation can always be bypassed;
see :doc:`security`).

Pre-validation before event dispatch and storage
------------------------------------------------

The Python boundary validator runs for every new ``@@save-poll`` submission,
independently of the optional external SurveyJS validator. It runs after
request/access checks and before ``notify()``, persistence, mail delivery or
configured external POST processing. A rejected submission cannot reach any
subscriber or post-submit action.

The order is deliberate:

1. **Transport limits:** ``Content-Length`` and the actual request body are
   checked against the survey's maximum payload size. Oversized input is
   rejected with HTTP 413 before JSON parsing.
2. **JSON shape:** ``pollResult`` must be valid JSON whose top-level value is
   an object. Arrays, strings, numbers and ``null`` are rejected. Nested
   values are recursively copied and limited to JSON scalar, list and object
   types.
3. **Schema fields:** field names are collected from the active form schema.
   Unknown fields and orphaned comment fields are rejected. SurveyJS comment
   suffixes use the configured ``commentPrefix``. The ``missing_required``
   check remains available via ``enforce_required_fields=True`` but is disabled
   by default for compatibility.
4. **Text safety:** recursive string checks reject control characters,
   obfuscated ``javascript:`` and ``vbscript:`` schemes, dangerous markup,
   script/SVG/iframe/object/embed elements and ``on*`` event-handler
   attributes. Ordinary text such as ``2 < 3`` remains valid.
5. **Data URLs:** non-file data URLs are limited to Base64 PNG and JPEG images.
   The encoding is strictly decoded and malformed or unsupported URLs are
   rejected.
6. **File structure:** file values must be lists of objects with string
   filename, MIME type and content members. Unsupported members are omitted
   from the normalized result rather than persisted.
7. **Filenames:** names are normalized to Unicode NFC before validation and
   storage. Path separators, traversal, control characters, quotes and
   markup-oriented characters are rejected while international names remain
   supported.
8. **MIME and content:** a restrictive MIME allowlist is enforced. SVG and
   ``application/octet-stream`` are rejected. The declared MIME must match the
   data URL, and decoded bytes must match the expected magic bytes for PNG,
   JPEG, GIF, WebP, PDF, RTF, ZIP and Office formats.
9. **Resource limits:** file count and decoded file-size limits are enforced
   independently of the total request limit.
10. **Canonical hand-off:** validation returns a normalized deep copy and never
    mutates the caller's original payload. Only this copy is passed to the
    optional external validator and, after success, to downstream processing.

Validation failures return the JSON contract::

    {"isSuccess": false, "error": "<code>", "field": "<optional-field>"}

The ``field`` member is omitted for errors without a specific field. Failures
use deterministic error codes, warning-level application logging and a
``zopyx.surveyjs.audit`` entry containing only ``reason``, ``field``,
``origin`` and ``remote_addr``. Submission contents, tokens and secrets are
not logged. Single-use embed/trusted tokens are consumed only after
pre-validation succeeds.

Validation error codes
----------------------

``payload_not_object`` / ``invalid_form_schema``
    The submission or active form schema is not a JSON object.
``unknown_field`` / ``invalid_comment_prefix``
    A field is not in the schema, a comment is orphaned, or ``commentPrefix``
    is invalid.
``missing_required``
    A required question is absent or empty. This check is disabled by default;
    when enabled, ``False`` and ``0`` remain valid values.
``invalid_comment_length`` / ``comment_too_long``
    A comment limit is invalid or the submitted comment exceeds it.
``control_character`` / ``dangerous_url`` / ``html_markup``
    Unsafe text, URL schemes, markup or event-handler attributes were found.
``invalid_value``
    A generic value has an unsupported type.
``invalid_file`` / ``too_many_files`` / ``unsafe_filename``
    File structure, file count or filename validation failed.
``disallowed_mime_type`` / ``mime_mismatch``
    The MIME type is not allowed or does not match the data URL.
``invalid_data_url`` / ``invalid_base64`` / ``file_too_large``
    File data is malformed or exceeds its decoded byte limit.
``invalid_file_content``
    Magic bytes or text encoding do not match the declared file type.

Server-side validation (external SurveyJS binary)
=================================================

The per-survey setting **Force Server Side Validation** (Form Settings tab,
default: **on**) runs every submission through the external validator
binary before the submission is stored or any action is executed. The
binary is a compiled executable built from ``validate.mjs`` (SurveyJS
``survey-core`` 3.x) — no Node.js runtime is needed on the Plone host.

Validation pipeline
-------------------

1. ``@@save-poll`` receives the submission and passes the hardening checks
   (payload size, access mode, authenticity token).
2. When *Force Server Side Validation* is enabled, the submission payload
   and the current form schema are written to a temporary directory and the
   validator binary is invoked with the two JSON files.
3. The binary loads the schema into a SurveyJS model, applies the payload
   via ``survey.data``, runs ``survey.validate()`` and collects the
   per-question error details. The result is written as JSON:
   ``{"valid": true|false, "errors": [{"name", "title", "codes": [...],
   "messages": [...]}]}``. Each error carries a stable machine-readable
   ``codes`` entry (e.g. ``required``, ``email``, ``numeric``) plus a
   human-readable ``messages`` entry — survey-core's empty default texts
   (notably for required questions) are mapped to readable strings.
4. The Python wrapper maps the outcome:

   * ``valid: true`` — the submission proceeds (stored, mailed, POSTed).
   * ``valid: false`` — the submission is rejected with **HTTP 400**
     (``external_validation_failed``) and the per-question error details are
     returned in the response body; nothing is stored.
   * binary missing → **HTTP 500** ``external_validator_missing``; the
     validator timed out (30 s) → **HTTP 500** ``external_validator_timeout``;
     the binary crashed or produced no result → **HTTP 500**
     ``external_validator_error``.

When the setting is off, submissions are accepted based on the client-side
validation only (plus the hardening checks) — faster, but the server
trusts the client.

Binary location and building
----------------------------

* Source and build tooling:
  ``src/zopyx/surveyjs/data_validation/`` (``validate.mjs``, ``Makefile``,
  ``package.json``, ``deno_build.py``).
* At runtime the wrapper expects the platform binary **next to the module**
  (``validate-linux`` / ``validate-mac``) and builds it automatically when
  missing or older than five days. The Deno release is pinned in
  ``deno_build.py`` and its archive digest and executable version are verified
  before compilation.
* Manual builds with bun or deno, cross-compilation via Docker, and
  packaging notes: see :doc:`installation` → "External survey validation
  (deno / bun)".
* CLI usage of the validator itself: :doc:`data-validation-cli`.

Payload limits
==============

The per-survey **Max size payload (MB)** setting (default 1 MB, minimum 1)
is enforced *before* validation: requests larger than the limit are
rejected with **HTTP 413** (``request_too_large`` / ``json_too_large``)
and are never parsed or validated. This protects the validator (and the
rest of the pipeline) from oversized or malicious payloads.

Error responses
===============

Common error codes returned by ``@@save-poll``:

* ``400`` — ``missing_poll_result``, ``invalid_payload``,
  ``invalid_json``, ``missing_form_schema``, ``external_validation_failed``
  (with per-question details)
* ``403`` — ``invalid_origin``, ``invalid_token``,
  ``token_already_used`` (embed submissions)
* ``413`` — ``request_too_large``, ``json_too_large``
* ``500`` — ``external_validator_missing``, ``external_validator_error``
  (binary not found or failed to produce a result)

Logging
=======

Validation emits INFO-level logs with the submission hash, schema and
payload sizes, the validator return code and the elapsed time, so failed
or slow validations are traceable in the Plone logs (see :doc:`security`
for the log-monitoring guidance).

Related documentation
=====================

* :doc:`data-validation-cli` — the validator CLI tool itself.
* :doc:`installation` — building and deploying the validator binary.
* :doc:`security` — the other checks that protect submissions.
