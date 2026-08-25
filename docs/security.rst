========
Security
========

Security in this add-on is about one thing: **keeping form data under your
control while reducing abuse of your forms**. The design follows a
defense-in-depth model — no single mechanism carries the whole burden, and
the mechanisms are layered so that a failure in one layer does not expose
the others.

Implementation status
=====================

The submission-validation hardening is complete for **new** SurveyJS
submission data. ``@@save-poll`` validates and normalizes the payload before
``notify()``, persistence, subscriber processing, mail delivery or configured
external POST actions.

Verified baseline:

* ``bin/test -s zopyx.surveyjs`` — 195 tests, 0 failures, 0 errors, 7 skips;
* ``make test`` — successful, including 96 passing pytest tests;
* Ruff and ``git diff --check`` — successful.

The seven skips are explicitly documented publisher-/ZCML-level cases. Stale
legacy API tests were removed from discovery rather than silently renamed in
the active test suite.

Philosophy
==========

* **Defense in depth.** Permissions gate who may *manage* a survey; tokens
  gate who may *submit* to it; payload limits and server-side validation
  gate *what* may be submitted; audit logging records *what happened*.
  Layers are independent and fail closed where it matters.
* **Fail closed, never fail open.** Wherever a protection depends on shared
  state (the token caches), an unavailable cache **rejects** the request
  (HTTP 503) instead of silently allowing it. A degraded deployment is
  temporarily unusable rather than insecure.
* **Client-side validation is UX, not security.** Everything that happens in
  the browser can be bypassed. The server never trusts the client: it
  re-validates (optionally with the external validator binary) and enforces
  size limits itself.
* **Secrets stay out of logs and screens.** API keys are password fields
  with a keep-mask convention; audit logging redacts tokens, keys, mail
  addresses and endpoints; dedicated signing keys are used for dedicated
  purposes and never fall back to another secret.
* **Minimal exposure.** Endpoints are registered with the least privilege
  they need (``zope2.View`` vs. ``cmf.ModifyPortalContent`` vs.
  ``cmf.ManagePortal``), results-reading endpoints are restricted to
  editors, and features can be switched off site-wide to shrink the attack
  surface.

Threat model
============

The mechanisms below address these concrete threats:

* **Scripted bulk submission / form flooding** — the authenticity token.
* **Replay of captured submissions** — one-time token tracking.
* **Cross-site request forgery** — the authenticity token is bound to the
  form load and cannot be obtained cross-origin; the token-management UI
  additionally uses Plone's CSRF authenticator.
* **Unauthorized access to restricted surveys** — trusted access tokens
  (cached or single-use).
* **Submission against an outdated form** — tokens are bound to the form id
  *and* the form version; a new form version invalidates old tokens.
* **Form scraping and tampered payloads** — optional server-side validation
  (external SurveyJS validator binary) and payload size limits.
* **Embedding abuse (content injection into third-party pages)** — origin
  allowlists, origin-bound signed tokens, one-time token use, CORS only for
  allowlisted origins.
* **Oversized payloads (resource exhaustion)** — the per-survey payload
  limit, enforced with HTTP 413 before parsing.
* **Insider tampering / unaccounted changes** — persistent audit logging
  with content hashes and redacted details.

Configuration options
=====================

All security-relevant options are described in detail in
:doc:`global-options` (site-wide) and :doc:`survey-options` (per survey).
This section explains *what each option is for*.

Global — Security fieldset (Site Setup > Forms)
-----------------------------------------------

``authenticity_token_enabled`` (default: on)
    Master switch for the submission token. On: every submission must carry
    a token issued when the form was loaded. This is the primary defense
    against scripted and cross-site submissions; keep it on unless an
    integration cannot obtain a token.

``authenticity_token_secret``
    HMAC secret signing the tokens. **Required** when the token is enabled.
    Rotate only with care — rotation invalidates all outstanding tokens, so
    visitors must reload the form before submitting.

``authenticity_token_ttl_seconds`` (default: 3600)
    Token lifetime. A long TTL lets visitors with slow sessions submit
    without reloading; a short TTL shrinks the replay window. The 120-second
    clock-skew tolerance is built into validation.

``authenticity_token_issuer`` / ``authenticity_token_audience``
    Expected JWT claims. Change them if you operate multiple sites or
    environments to prevent tokens minted elsewhere from being accepted.

``authenticity_token_cache_path`` (default: ``var/token_cache.db``)
    Where replay tracking and trusted-token metadata live. Must be writable
    by the Plone process and not publicly served.

Global — Logging fieldset
~~~~~~~~~~~~~~~~~~~~~~~~~

``log_ip_addresses`` / ``log_user_agent``
    Not protection, but privacy controls: storing client IPs and user-agent
    strings helps abuse detection and auditing, yet turns them into personal
    data. Enable deliberately and disclose in your privacy policy.

Global — Direct DOM Embedding fieldset
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``embed_direct_global_enabled`` (default: off)
    Master switch for Direct DOM embedding. Off by default — the feature is
    disabled until explicitly enabled.

``embed_direct_signing_key``
    Dedicated HMAC key for embed tokens. A dedicated key (not a fallback to
    the authenticity-token secret) limits the blast radius if one key leaks.
    Rotate regularly; rotation invalidates outstanding embed tokens.

``embed_direct_max_origins`` (default: 10)
    Caps the allowed origins per survey — a defense against a misconfigured
    survey allowing an attacker-controlled origin.

Global — General fieldset
~~~~~~~~~~~~~~~~~~~~~~~~~

``features_enabled``
    Reducing exposure: disabling a feature removes its UI entry points
    site-wide.

Per-survey — Form Settings
~~~~~~~~~~~~~~~~~~~~~~~~~~

``access_mode`` (default: ``public``)
    Who may submit:

    * ``public`` — anyone with the URL. Use for open surveys.
    * ``trusted`` — requires a trusted access token in the URL
      (``access_token``/``tt`` parameter). Use to restrict a survey to a
      known group without accounts: generate a link per stakeholder; the
      token is bound to the survey and expires after the TTL.
    * ``trusted-tokens`` — same, but tokens are **single-use**: each token
      is consumed by the first successful submission. Use for one-time
      invitations or vouchers, where each recipient may submit exactly once.

``trusted_access_ttl_hours`` (default: 168)
    Lifetime of *cached* trusted tokens (``trusted`` mode). Shorten it to
    reduce the abuse window for leaked links; lengthen it to avoid
    regenerating tokens frequently.

``force_server_side_validation`` (default: on)
    Server-side re-validation of every submission with the external SurveyJS
    validator binary. On: a tampered or malformed payload is rejected even
    if the client never validated it.

``max_payload_size_mb`` (default: 1)
    Hard size limit; oversized requests get HTTP 413 before any parsing or
    storage. Raise it for file-upload surveys, keep it low otherwise.

Per-survey — Embedding
~~~~~~~~~~~~~~~~~~~~~~

``embedding_mode`` (``none`` / ``iframe`` / ``direct``)
    ``iframe`` is the safe default for embedding (CSP ``frame-ancestors``).
    ``direct`` (Direct DOM) is experimental and unlocks the full embedding
    security stack below — it should stay off unless you need it.

``embed_direct_origins``
    The allowlist. Origins are normalized (scheme://host) and matched
    strictly; HTTPS is required outside localhost. Every token and CORS
    decision is evaluated against this list.

``embed_direct_token_ttl`` (default: 300s, 60–3600)
    Lifetime of embed tokens. Short values minimize the window in which a
    stolen token is usable.

Internal security measures
==========================

Authenticity token (anti-CSRF / anti-replay)
--------------------------------------------

A short-lived JWT signed with HMAC-SHA256 (HS256), issued by ``@@viewer``
and required by ``@@save-poll`` in the ``auth_token`` form field:

* Claims: ``iss``, ``aud``, ``iat``, ``nbf``, ``exp``, ``jti`` (random),
  ``form_id`` and ``form_version``. Validation checks the signature with a
  constant-time comparison, pins the algorithm to HS256, enforces all time
  claims with 120 s skew, and requires issuer, audience, form id *and form
  version* to match.
* **Version binding** is the interesting part: a token is only valid for the
  form version it was issued for. Publishing a new form version
  automatically invalidates all outstanding tokens — nobody can submit
  against a stale schema.
* **Replay protection** is stateful: every received token is recorded in a
  diskcache (atomic add, 24 h TTL). A second submission with the same token
  is rejected with ``auth_token_replay`` (403). If the cache is
  unavailable, the request is rejected (503) — fail closed.

Trusted access tokens
---------------------

* ``trusted`` mode: tokens are ``secrets.token_urlsafe(16)`` values stored
  with metadata (form id, form version, issued/expiry, state) in the same
  diskcache. Validation checks existence, the ``REVOKED`` state and the form
  binding. Tokens travel as ``access_token`` or ``tt`` request parameters.
* ``trusted-tokens`` mode: tokens come from the ITokenStore adapter
  (managed in ``@@token-store``: generate, CSV import/export, stats). They
  are validated with ``has_token`` and **consumed only after a successful
  submission** (``invalidate(reason="user_submission")``) — a failed
  submission does not burn the token. Editors and Managers bypass the
  checks; the token store view itself is CSRF-protected with Plone's
  authenticator and permission-checked.

Direct DOM embedding stack
--------------------------

* Tokens are PyJWT HS256 JWTs with a dedicated signing key, verified with
  fixed ``aud``/``iss`` values (``embed-client`` / ``privacyforms.studio``)
  and an **origin claim** that must equal the request's ``Origin`` header.
* **One-time use**: the token's ``jti`` is atomically marked used at
  submission time; a replayed token is rejected
  (``token_already_used``, 403). Cache failure → reject (fail closed).
* **Origin validation**: HTTPS only (HTTP tolerated solely for
  localhost/127.0.0.1/::1), no path, query, fragment or trailing slash;
  allowlist comparison on normalized ``scheme://host``.
* **CORS discipline**: preflight and responses carry CORS headers only for
  allowlisted origins (no wildcard). Unknown origins get an empty 204 — the
  browser blocks the actual request. Responses additionally set
  ``X-Content-Type-Options: nosniff``, ``X-Frame-Options: DENY`` and
  ``Referrer-Policy: strict-origin-when-cross-origin``.

Payload and validation hardening
--------------------------------

* Payload size is enforced against ``Content-Length`` *and* the actual body
  before JSON parsing (``413 request_too_large`` / ``json_too_large``).
* With ``force_server_side_validation`` enabled, submissions are handed to the
  external SurveyJS validator binary; a failed validation returns the
  error (with details) and the submission is not stored.
* The Python boundary validator additionally requires a top-level object and
  rejects unknown fields where applicable. The ``missing_required`` check is
  retained behind ``enforce_required_fields=True`` but is disabled by default
  for compatibility.
* When enabled, the ``missing_required`` check rejects empty required values;
  it is disabled by default. Dangerous markup and event-handler attributes,
  control characters and unsafe URL schemes remain enforced.
* Structured files use a restrictive MIME allowlist, valid Base64 data URLs,
  MIME consistency checks and magic-byte verification. SVG and
  ``application/octet-stream`` are rejected by default.
* File count, file size and payload limits are enforced. Unicode filenames are
  normalized to NFC before storage. Normalization operates on a copy and does
  not mutate the caller's payload.
* Validation failures use deterministic error codes and warning-level logging
  without recording submission contents. Invalid submissions are stopped
  before event dispatch and storage.
* Single-use embed/trusted tokens are consumed only after validation succeeds.

The complete validation contract is documented in
:doc:`validation`; the requirement-by-requirement evidence is in
``SUBMISSION_VALIDATION_REQUIREMENTS.md``.

Known residual scope
--------------------

The submission validator is not a blanket fix for unrelated security findings.
The following remain separate work items unless implemented elsewhere:

* CSRF enforcement in the public JSON view itself, or publisher-level tests
  proving the surrounding Plone protection layer;
* SSRF validation for configured ``post_endpoint_url`` destinations;
* output encoding for stored values rendered by result views;
* rate limiting, quotas, bot controls, dependency pinning and key rotation.

Permission model
----------------

* Public rendering (``@@viewer``, ``@@get-form-json``) is ``zope2.View`` but
  subject to the survey's access mode and token checks.
* Everything that reads or mutates results and forms
  (``@@get-polls-json*``, downloads, version endpoints, AI) requires
  ``cmf.ModifyPortalContent``; ``@@delete-results`` re-checks Manager
  inside; administration (``@@forms-settings``, ``@@token-store``,
  ``@@survey-monitor``, ``@@llm-models``) requires ``cmf.ManagePortal``.

Audit logging
-------------

Persistent audit entries (via the persistent logger) record:

* Form version changes — including a SHA-256 of the JSON, page/element/
  question counts and added/removed question names, so a form change can be
  attributed and reconstructed.
* Control panel changes and metadata updates.
* Embed security events (``embed.token.issued`` / ``embed.token.validated``,
  ``embed.submission.accepted`` / ``embed.submission.rejected`` with
  reason).

All details are **redacted by default**: mail subjects/bodies/addresses,
POST endpoints and anything whose field name contains ``password``,
``secret``, ``token``, ``apikey``/``api_key`` is logged only as a redaction
marker with length/count — never with its value.

Secrets handling
----------------

* Secrets use ``zope.schema.Password`` fields and a keep-mask convention in
  the control panel: an empty submitted value never overwrites a stored key.
* Dedicated keys are dedicated: the embed signing key does not fall back to
  the authenticity-token secret; both are stored in the Plone registry
  (ZODB), not in files or code.

Operational guidance
====================

* Serve everything over HTTPS; the origin validation requires it outside
  localhost anyway.
* Put rate limiting on submission endpoints at the reverse proxy or WAF —
  the authenticity token stops scripted submission from *within* a browser
  session, but a determined client can always fetch a fresh token; rate
  limiting is the complementary control.
* Protect and monitor the token cache paths (``var/token_cache.db``,
  ``var/embed_token_cache.db``): they contain replay/token state and must be
  writable by Plone but not publicly served.
* Watch the logs for repeated ``auth_token_replay``, oversized-payload
  rejections and ``embed.submission.rejected`` entries — they are the
  visible signs of probing or abuse.
* Rotate the two signing secrets (authenticity token secret, embed signing
  key) on a schedule or after a suspected leak, and plan for the resulting
  token invalidation (visitors reload the form; embeds re-issue tokens).

Further reading
===============

* :doc:`global-options` — all global settings, defaults and field reference.
* :doc:`survey-options` — per-survey settings, including access mode and
  embedding.
* :doc:`endpoints` — the endpoints these measures protect, with parameters
  and error codes.
* :doc:`validation` — client- and server-side validation details.
