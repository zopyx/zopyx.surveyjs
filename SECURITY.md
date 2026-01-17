# Security Policy and Abuse Mitigation

This document describes the security model and built-in measures to reduce abuse of SurveyJS forms in `zopyx.surveyjs`.

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

### Client-side validation (SurveyJS)

SurveyJS runs validation in the browser based on the form schema (required fields, regex, min/max, and other rules). This improves user feedback but must not be relied on for security, because clients can bypass it.

Recommended:
- Define validation rules in the SurveyJS schema.
- Treat client-side validation as usability, not as a security boundary.

### Server-side validation (optional)

Two server-side validation paths are available:

- **Enable validation (experimental)**: a Python validator that checks the submission against the form schema. This is useful for basic validation but may reject complex forms.
- **Force Server Side Validation**: runs a compiled SurveyJS validator binary (Deno) for every submission. This mirrors SurveyJS' own validation engine and is the most reliable option.

Recommended:
- Enable the external validator for forms that require strict validation.
- Ensure the Deno binary is present in `data-validation/dist` and kept up-to-date.
- See `data-validation/README.md` for build and usage details.

## Operational Guidance

To reduce abuse and increase reliability:

- **Use HTTPS** for all endpoints, including POST actions.
- **Restrict POST endpoints** to trusted services; validate payloads on the receiver side as well.
- **Add rate limiting** at the reverse proxy or WAF (not implemented in this package).
- **Monitor logs** for repeated failures or unusually large payload sizes.

## Reporting

Security issues should be reported directly to the maintainer:

- Andreas Jung | info@zopyx.com
