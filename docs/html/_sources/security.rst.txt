========
Security
========

This module focuses on reducing form abuse while keeping data under your
control. Security is a combination of configuration, validation, and
operational practices.

Payload limits
==============

Each Survey defines ``Max size payload (MB)``. Oversized requests are rejected
with HTTP 413 before validation or storage.

Validation
==========

Client-side validation
  SurveyJS enforces schema constraints in the browser. This improves UX but
  is not a security boundary.

Server-side validation
  Use the Python validator or the external SurveyJS validator binary for
  strict checks. See :doc:`validation` and ``data-validation/README.md``.

Operational guidance
====================

- Use HTTPS for all endpoints.
- Restrict POST endpoints to trusted services.
- Apply rate limiting at the reverse proxy or WAF.
- Monitor logs for repeated failures and oversized payloads.
