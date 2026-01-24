Security Model for Survey Submissions
=====================================

This document describes the security measures implemented for form rendering,
submission, and storage. It focuses on the security checks that happen during
``@@viewer`` / ``@@get-form-json`` / ``@@save-poll`` and the configuration
surface (global and per-survey).

Scope
-----

The measures described here apply to:

- Rendering forms for end users (``@@viewer`` and ``@@get-form-json``).
- Submitting survey results (``@@save-poll``).
- Storing results (ZODB or SQL backends).

Global Configuration (Plone Registry)
-------------------------------------

The following options live in ``IFormsSettings`` and apply across all surveys.

Authenticity token (JWT) options
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These options enforce a short-lived, signed token for form submissions. Tokens
are embedded in the form page and must be presented when submitting.

- ``authenticity_token_enabled`` (Bool, default: ``True``)
  - When enabled, submissions must include a valid JWT in ``auth_token``.
  - When disabled, submissions do not require the JWT.

- ``authenticity_token_secret`` (Password, default: empty)
  - HMAC secret used to sign/verify JWTs.
  - Required when JWT enforcement is enabled.

- ``authenticity_token_ttl_seconds`` (Int, default: ``600``, min: ``60``)
  - JWT lifetime in seconds.
  - Used for ``exp`` claim enforcement.

- ``authenticity_token_issuer`` (Text, default: ``zopyx.surveyjs``)
  - JWT ``iss`` claim to validate issuer.

- ``authenticity_token_audience`` (Text, default: ``zopyx.surveyjs``)
  - JWT ``aud`` claim to validate audience.

- ``authenticity_token_cache_path`` (Text, default: ``var/token_cache.db``)
  - Filesystem path for diskcache storage.
  - Used to track issued/received tokens for replay protection.

Result storage options (security relevant)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``result_storage_backend`` (Choice, default: ``zodb``)
  - Storage backend selection. Does not change validation, but affects
    persistence and operational controls.

- ``database_uri`` (Text, default: ``sqlite:///var/surveyjs-results.db``)
  - Database URL for relational result storage.

Survey-Specific Configuration
-----------------------------

These options are defined on each Survey content item.

Form access policy
~~~~~~~~~~~~~~~~~~

- ``access_mode`` (Choice, default: ``public``)
  - ``public``: Form is accessible without a URL access token.
  - ``trusted``: Form requires a trusted access token in the URL for both
    rendering and submission.

- ``trusted_access_ttl_hours`` (Int, default: ``168``, min: ``1``)
  - Lifetime of trusted access tokens in hours.
  - Drives diskcache expiration and ``expires_at`` metadata.

Submission validation and limits
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``max_payload_size_mb`` (Int, default: ``1``)
  - Maximum request payload size (bytes derived from MB).
  - Enforced before JSON parsing.

- ``validation_enabled`` (Bool, default: ``False``)
  - Server-side SurveyJS schema validation.
  - If enabled, invalid submissions are rejected.

- ``force_server_side_validation`` (Bool, default: ``False``)
  - Executes external validator for every submission.
  - If validator fails, submission is rejected.

Security Measures: How They Work
--------------------------------

1. CSRF protection (Plone default)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Submission requests include a ``_authenticator`` token (Plone CSRF). This is
sent by the client and validated by Plone. It prevents cross-site request
forgery for authenticated sessions. Anonymous users may still submit if the
view is public and the authenticator is accepted by Plone.

2. Trusted access token (URL-based access control)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Purpose
^^^^^^^

Restricts *form rendering and submission* to users who have a trusted URL token.

Token type and storage
^^^^^^^^^^^^^^^^^^^^^^

- Opaque short token generated server-side.
- Stored in diskcache under ``trusted:<token>`` with metadata:

  - ``form_id``: survey identifier
  - ``form_version``: version at issuance time
  - ``issued_at``: ISO timestamp
  - ``expires_at``: ISO timestamp
  - ``state``: currently ``ISSUED``

Enforcement points
^^^^^^^^^^^^^^^^^^

- ``@@get-form-json``: checks for ``access_token`` in query or form.
- ``@@save-poll``: checks for ``access_token`` in form data.
- PDF submission path: same trusted access check.

Failure behavior
^^^^^^^^^^^^^^^^

- Missing or invalid token -> HTTP 403 with JSON error.
- Cache unavailable -> HTTP 503 with JSON error.
- Form mismatch -> HTTP 403 with JSON error.

3. Authenticity token (JWT with replay protection)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Purpose
^^^^^^^

Ensures submissions were rendered by the server (short-lived JWT) and mitigates
replay attacks.

Token creation
^^^^^^^^^^^^^^

- Generated per form render via ``build_auth_token``.
- Embedded in the page (``AUTH_TOKEN`` JS variable).
- Claims include:

  - ``iss`` / ``aud``
  - ``exp`` / ``nbf`` / ``iat``
  - ``form_id``
  - ``form_version``
  - ``jti`` (token id)

Validation
^^^^^^^^^^

- ``@@save-poll`` and PDF submission path validate JWT signature and claims.
- If invalid or expired, submission is rejected with HTTP 403.

Replay protection
^^^^^^^^^^^^^^^^^

- diskcache keys:

  - ``issued:<token>`` set at issuance
  - ``received:<token>`` set at first submission

- If ``received:<token>`` is present, submission is rejected as replay.
- Cache TTL: 24 hours for authenticity tokens.

4. Payload size enforcement
~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``Content-Length`` and raw payload size are checked.
- Requests exceeding ``max_payload_size_mb`` are rejected with HTTP 413.
- Protects against oversized payloads and memory pressure.

5. Schema validation (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- If ``validation_enabled`` is true, submissions are validated against the
  stored SurveyJS schema.
- Invalid submissions return HTTP 400 with error info.

6. External validation (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- If ``force_server_side_validation`` is enabled, an external validator
  is executed on every submission.
- On failure, submission is rejected (status per validator).

Token Lifetimes and Defaults
----------------------------

Authenticity JWT (global):
- Default: 600 seconds (10 minutes).
- Min: 60 seconds.

Trusted access token (per survey):
- Default: 168 hours (7 days).
- Min: 1 hour.

Diskcache TTL:
- Authenticity JWT replay cache: 24 hours.
- Trusted access tokens: per-survey TTL.

Operational Notes
-----------------

- ``@@trusted-access-token`` endpoint requires ``cmf.ManagePortal`` permission.
- ``@@viewer`` and ``@@save-poll`` are public views, but are protected by the
  configured token checks.
- If diskcache is unavailable and trusted access is required, requests are
  rejected (fail closed).

Common Scenarios
----------------

Public form, basic anti-replay
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``access_mode = public``
- ``authenticity_token_enabled = True``
- JWT + replay protection active, but anyone can view the form.

Trusted access link
~~~~~~~~~~~~~~~~~~~

- ``access_mode = trusted``
- Issue token via ``@@trusted-access-token`` (manager).
- Only users with the link can load and submit the form.

Hardening suggestions
---------------------

- Keep the JWT secret private and rotate it when needed.
- Use short JWT TTLs for high-risk forms.
- Use trusted access for invitation-only surveys.
- Consider one-time tokens if you need strict single-use access.

Threat Model
------------

This section outlines realistic threat scenarios and how the current security
controls mitigate them. It also calls out residual risks so operators can
decide whether additional hardening is needed.

Assets to protect
~~~~~~~~~~~~~~~~~

- **Survey integrity**: prevent unauthorized or tampered submissions.
- **Survey availability**: avoid abuse that degrades service or storage.
- **Access control**: ensure private surveys are not publicly accessible.
- **Operational trust**: maintain auditability and reliability of submissions.

Actors and capabilities
~~~~~~~~~~~~~~~~~~~~~~~

- **Casual attacker**: can access public URLs, attempt direct POSTs, replay
  previous submissions, or spam the endpoint.
- **Automated bot**: can programmatically submit at scale, attempt to reuse
  tokens, or brute-force weak access controls.
- **Leaked link recipient**: a legitimate trusted access link is shared
  beyond intended recipients.
- **Insider**: authorized manager who can generate tokens or change settings.

Threats and mitigations
~~~~~~~~~~~~~~~~~~~~~~~

Unauthorized submission (direct POST without UI)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Scenario**: An attacker submits data directly to ``@@save-poll`` without ever
loading the form, attempting to bypass the UI.

**Mitigations**:

- **JWT authenticity token**: enabled by default and required for submissions.
  Requests without a valid ``auth_token`` are rejected.
- **Claim binding**: token includes ``form_id`` and ``form_version`` so it
  cannot be reused across different surveys or versions.
- **Short TTL**: reduces the window in which a stolen token is useful.

**Residual risk**:

- If the JWT secret is compromised, a skilled attacker could mint tokens.
  Rotate the secret and keep it out of logs or public config.

Replay attacks (duplicate submissions)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Scenario**: An attacker replays a previously valid JWT or payload to create
duplicate entries.

**Mitigations**:

- **diskcache replay protection**: each JWT is tracked as
  ``received:<token>`` and further use is rejected.
- **TTL on replay entries**: 24-hour TTL limits cache growth.

**Residual risk**:

- If diskcache is unavailable or its data is lost, replay defense resets.
  This is acceptable for many deployments but should be considered in
  high-assurance environments.

Unauthorized form access (private form exposure)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Scenario**: A survey should be restricted, but the URL is guessed or shared.

**Mitigations**:

- **Trusted access mode**: requires a URL token for both form rendering and
  submission. Without the token, the form JSON is not delivered.
- **Server-side validation**: access enforcement is not only client-side;
  ``@@get-form-json`` and ``@@save-poll`` verify the token.

**Residual risk**:

- Trusted access tokens are shareable links by design. If a link is leaked,
  any holder can access until it expires. Use short TTLs for sensitive forms.

Token brute-force or guessing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Scenario**: An automated attacker tries to guess valid access tokens or JWTs.

**Mitigations**:

- **Opaque trusted access tokens**: URL tokens are random and URL-safe,
  stored server-side, and have sufficient entropy to resist guessing.
- **JWT signature**: forged tokens will fail HMAC validation.

**Residual risk**:

- No built-in rate limiting exists. If the system is exposed to the public
  internet, consider adding rate limits at the reverse proxy or WAF layer.

Mass submission / denial of service
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Scenario**: An attacker floods ``@@save-poll`` with large or frequent
submissions to exhaust resources.

**Mitigations**:

- **Payload size limits**: strict ``max_payload_size_mb`` checks reject
  oversized submissions early.
- **Optional validation**: schema validation rejects malformed or incomplete
  submissions.

**Residual risk**:

- Repeated small submissions can still create load. Rate limiting or
  application-level throttling may be required for public-facing surveys.

Cross-site request forgery (CSRF)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Scenario**: A third-party site attempts to submit a form on behalf of a user.

**Mitigations**:

- **Plone CSRF token** (``_authenticator``) is required for form submission.
  This mitigates CSRF in authenticated contexts.
- **JWT authenticity token** is a second guard for submissions.

**Residual risk**:

- Anonymous forms are still accessible by design. CSRF is less meaningful in
  anonymous contexts, but JWT and trusted access still apply.

Data tampering between render and submit
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Scenario**: A user modifies the client-side payload to include fields not in
the schema or invalid values.

**Mitigations**:

- **Server-side validation** when enabled rejects invalid payloads.
- **External validation** (optional) provides an additional strict check.

**Residual risk**:

- Validation is optional by configuration. If disabled, the system will store
  any payload.

Information leakage via form metadata
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Scenario**: The form JSON or form version data exposes internal details.

**Mitigations**:

- **Trusted access** blocks form JSON delivery without a token.
- **JWT** does not expose sensitive data; it embeds only form identifiers.

**Residual risk**:

- In public mode, form JSON is available to anyone with access to the form URL.
  Use trusted access for sensitive surveys.

Insider or misconfiguration risk
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Scenario**: A manager accidentally disables security or sets weak values.

**Mitigations**:

- **Defaults** are secure: authenticity tokens enabled, TTLs set.
- **Per-survey access mode** defaults to public but is explicit.

**Residual risk**:

- Misconfiguration can reduce protection. Operational guidance and reviews are
  recommended for sensitive deployments.

Recommended Hardening by Risk Level
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Low risk (public surveys)
^^^^^^^^^^^^^^^^^^^^^^^^^

- Keep JWT authenticity enabled.
- Keep default payload size limits.
- Consider turning on schema validation for data quality.

Medium risk (semi-private)
^^^^^^^^^^^^^^^^^^^^^^^^^^

- Enable trusted access with a short TTL (e.g., 24–72 hours).
- Keep JWT authenticity enabled.
- Enable validation and consider external validation.

High risk (invitation-only, sensitive data)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Enable trusted access with short TTLs and rotate links regularly.
- Consider one-time access tokens (not implemented by default).
- Enforce strict validation and external validation.
- Add rate limiting at the proxy / network layer.
