===========
Validation
===========

Survey submissions can be validated in two ways: the Python validator and an
external SurveyJS binary. Both are optional and configurable per survey.

Python validation (experimental)
================================

``Enable validation (experimental)`` enables a Python validation layer that
checks submissions against the form schema before storing or running actions.
It is useful for basic forms but may reject complex SurveyJS structures.

External SurveyJS validation (recommended for strict checks)
============================================================

``Force Server Side Validation`` runs the compiled SurveyJS validator binary
(Deno build) for every submission. This uses SurveyJS' own validation engine
and provides the most accurate results for complex forms.

Binary location:

- ``data-validation/dist/survey-validate-macos-deno``
- ``data-validation/dist/survey-validate-linux-deno``

Payload limits
==============

Each Survey includes ``Max size payload (MB)``. Requests larger than this
limit are rejected with ``HTTP 413`` before validation proceeds.

Error responses
===============

Common error codes returned by ``@@save-poll`` include:

- ``missing_poll_result``
- ``invalid_payload``
- ``request_too_large``
- ``json_too_large``
- ``invalid_json``
- ``missing_form_schema``
- ``external_validator_missing``
- ``external_validation_failed``
- ``external_validator_error``

Logging
=======

Validation emits INFO-level logs with submission size, status, and
server-side validation results.
