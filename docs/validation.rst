===========
Validation
===========

Survey submissions can be validated **server-side** with SurveyJS's own
validation engine, compiled into a small standalone binary. This is the
counterpart to the client-side validation that SurveyJS performs in the
browser — the browser checks improve the user experience, the server check
is the security boundary (client-side validation can always be bypassed;
see :doc:`security`).

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
   per-question error messages. The result is written as JSON:
   ``{"valid": true|false, "errors": [{"name", "title", "messages": [...]}]}``.
4. The Python wrapper maps the outcome:

   * ``valid: true`` — the submission proceeds (stored, mailed, POSTed).
   * ``valid: false`` — the submission is rejected with **HTTP 400**
     (``external_validation_failed``) and the per-question error details are
     returned in the response body; nothing is stored.
   * binary missing → **HTTP 500** ``external_validator_missing``; the
     binary crashed or produced no result → **HTTP 500**
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
  missing or older than five days (it downloads Deno itself into a
  temporary directory — no manual step required).
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
