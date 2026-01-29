---
title: "Security2"
sidebar_position: 18
---

This document explains the protections used during form rendering, submission,
and result storage. It covers the checks performed in `@@viewer`,
`@@get-form-json`, and `@@save-poll`, plus the configuration surface at both
global and per-survey levels.

## Scope

These safeguards apply to:

- Rendering forms for end users (`@@viewer` and `@@get-form-json`).
- Submitting survey results (`@@save-poll`).
- Storing results in ZODB or SQL backends.

## Global Configuration (Plone Registry)

All options below live in `IFormsSettings` and affect every survey.

### Authenticity token (JWT) options

These settings require a short-lived, signed token for submissions. Tokens are
embedded in the rendered form and must be sent back on submit.

- `authenticity_token_enabled` (Bool, default: `True`)
  - When enabled, submissions must include a valid JWT in `auth_token`.
  - When disabled, JWTs are not required.

- `authenticity_token_secret` (Password, default: empty)
  - HMAC secret used to sign and verify JWTs.
  - Required if JWT enforcement is enabled.

- `authenticity_token_ttl_seconds` (Int, default: `600`, min: `60`)
  - Token lifetime in seconds.
  - Enforced via the `exp` claim.

- `authenticity_token_issuer` (Text, default: `zopyx.surveyjs`)
  - Expected `iss` claim value.

- `authenticity_token_audience` (Text, default: `zopyx.surveyjs`)
  - Expected `aud` claim value.

- `authenticity_token_cache_path` (Text, default: `var/token_cache.db`)
  - Filesystem location for diskcache.
  - Tracks issued and received tokens for replay prevention.

### Result storage options (security relevant)

- `result_storage_backend` (Choice, default: `zodb`)
  - Selects the storage backend. Validation is unchanged, but persistence and
    operational controls differ.

- `database_uri` (Text, default: `sqlite:///var/surveyjs-results.db`)
  - Database URL for relational result storage.

## Survey-Specific Configuration

These options are set on each Survey content item.

### Form access policy

- `access_mode` (Choice, default: `public`)
  - `public`: Form is accessible without a URL access token.
  - `trusted`: Form requires a trusted access token for rendering and submit.

- `trusted_access_ttl_hours` (Int, default: `168`, min: `1`)
  - Lifetime of trusted access tokens in hours.
  - Drives diskcache expiration and `expires_at` metadata.

### Submission validation and limits

- `max_payload_size_mb` (Int, default: `1`)
  - Maximum request payload size (bytes derived from MB).
  - Checked before JSON parsing.

- `force_server_side_validation` (Bool, default: `True`)
  - Runs an external validator on every submission.
  - Failed validation rejects the submission.

## Security Measures: How They Work

### 1. CSRF protection (Plone default)

Submission requests include the `_authenticator` token (Plone CSRF). The client
sends it and Plone validates it to block cross-site request forgery for
authenticated sessions. Anonymous submissions may still succeed if the view is
public and Plone accepts the authenticator.

### 2. Trusted access token (URL-based access control)

#### Purpose

Limits *form rendering and submission* to users who possess a trusted URL token.

#### Token type and storage

- Opaque short token generated server-side.
- Stored in diskcache under `trusted:<token>` with metadata:

  - `form_id`: survey identifier
  - `form_version`: version at issuance time
  - `issued_at`: ISO timestamp
  - `expires_at`: ISO timestamp
  - `state`: currently `ISSUED`

#### Enforcement points

- `@@get-form-json`: checks for `access_token` in query or form.
- `@@save-poll`: checks for `access_token` in form data.
- PDF submission path: same trusted access check.

#### Failure behavior

- Missing or invalid token -> HTTP 403 with JSON error.
- Cache unavailable -> HTTP 503 with JSON error.
- Form mismatch -> HTTP 403 with JSON error.

### 3. Authenticity token (JWT with replay protection)

#### Purpose

Confirms submissions were rendered by the server (short-lived JWT) and reduces
replay risk.

#### Token creation

- Generated for each form render via `build_auth_token`.
- Embedded in the page (`AUTH_TOKEN` JS variable).
- Claims include:

  - `iss` / `aud`
  - `exp` / `nbf` / `iat`
  - `form_id`
  - `form_version`
  - `jti` (token id)

#### Validation

- `@@save-poll` and PDF submission path verify JWT signature and claims.
- Invalid or expired tokens reject the submission with HTTP 403.

#### Replay protection

- diskcache keys:

  - `issued:<token>` set at issuance
  - `received:<token>` set at first submission

- If `received:<token>` is present, submission is rejected as replay.
- Cache TTL: 24 hours for authenticity tokens.

### 4. Payload size enforcement

- `Content-Length` and raw payload size are checked.
- Requests above `max_payload_size_mb` are rejected with HTTP 413.
- Protects against oversized payloads and memory pressure.

### 5. Server-side validation

- If `force_server_side_validation` is enabled, an external validator runs on
  every submission.
- Validation failures reject the submission (status per validator).

## Token Lifetimes and Defaults

Authenticity JWT (global):
- Default: 600 seconds (10 minutes).
- Min: 60 seconds.

Trusted access token (per survey):
- Default: 168 hours (7 days).
- Min: 1 hour.

Diskcache TTL:
- Authenticity JWT replay cache: 24 hours.
- Trusted access tokens: per-survey TTL.
