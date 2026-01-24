# Extended Security Plan

This document defines an architecture-level plan and an implementation plan for improving authenticity, replay protection, and abuse resistance for SurveyJS form submissions in this Plone-based codebase. It is intentionally code-free and focuses on consistent, end-to-end design.

## Goals

- Ensure each form submission is authentic and intended for the targeted form and site.
- Prevent replay of prior submissions, even within a short time window.
- Preserve compatibility with Plone's existing CSRF protection and session model.
- Maintain usability for both authenticated and anonymous users.
- Provide a clear path for key management and rotation.
- Keep operational risk low and changes auditable.

## Non-Goals

- Replacing Plone's CSRF protections.
- Providing complete bot mitigation (CAPTCHA is optional and can be added later).
- Implementing any specific storage or cache backend in this document.

## Current Context (Summary)

- CSRF tokens are already emitted in templates and included in JS requests.
- Form submissions are accepted via dedicated views (e.g., save_poll, pdf submit).
- Server-side validation exists for payload structure and optional external validation.

The plan below introduces a short-lived authenticity token with replay protection and a storage-backed nonce registry. This is additive to CSRF (not a replacement).

## Architecture Plan

### 1) Token Strategy (Short-Lived Authenticity Token)

Introduce a short-lived, signed token issued when the form is rendered (or on an explicit "token" request). This token is returned with the client submission and verified server-side. It must be bound to context and be single-use.

Recommended approach:
- Token format: JWT (HMAC-SHA256) or a compact HMAC-signed JSON payload.
- Payload claims (minimum):
  - iss: issuing site identifier
  - aud: expected submission endpoint
  - iat, nbf, exp: issued, not-before, expiry
  - jti: unique identifier (nonce)
  - form_id: stable survey identifier
  - form_version: current form version id
  - user_id or session_id: if available, to bind token to session

Rationale:
- Short lifetime reduces abuse window.
- Binding to form and version prevents token reuse across forms.
- Session binding limits token theft utility.
- jti enables replay protection when combined with server-side storage.

### 2) Replay Protection (Nonce Registry)

Maintain a server-side registry of consumed jti values. If a jti is seen again, the submission is rejected.

Storage requirements:
- Key: jti (optionally prefixed with site/form id)
- Value: timestamp or minimal metadata
- TTL: token lifetime + small grace
- Operations: atomic "check and set" to prevent race conditions

Backend choice: Diskcache
- Use the `diskcache` module as the primary nonce store.
- Rationale: persistent local storage, TTL support, fast read/write, and atomic operations.
- Deployment considerations: keep the cache directory on a local disk with sufficient space and I/O.

### 3) Key Management

Use a per-environment secret key for signing tokens.

- Key length: 256-bit (32 bytes) minimum
- Source: environment variable or Plone registry
- Rotation: maintain key ring (active + previous) with key id (kid)
- Grace: old key remains valid for a short period (e.g., 1-7 days)

### 4) Submission Pipeline

High-level flow:
1. Client loads the form and receives CSRF token and authenticity token.
2. Client submits payload + authenticity token + CSRF token.
3. Server validates CSRF (existing Plone protection).
4. Server validates authenticity token:
   - signature, issuer, audience
   - exp/nbf/iat bounds
   - form_id/form_version match
   - optional session/user binding
5. Server checks nonce registry for jti (atomic check-and-set).
6. If all checks pass, accept and process submission.

### 5) Anonymous vs Authenticated

- Authenticated submissions: bind token to user id and session id.
- Anonymous submissions: bind to session id (or Plone-generated session), optionally user agent hash.
- Avoid IP-based binding to reduce false positives (NAT, mobile networks).

### 6) Abuse Mitigation (Optional Layer)

- Add rate limits: per form, per session, per IP (soft limit).
- Add honeypot fields for anonymous forms.
- Add CAPTCHA for forms exposed to high-risk traffic.

## Implementation Plan (Step-by-Step)

### Phase 1: Design and Configuration

1. Define new settings in the Plone registry:
   - enable_authenticity_token (bool)
   - authenticity_token_ttl_seconds (int)
   - authenticity_token_issuer (string)
   - authenticity_token_audience (string)
   - authenticity_token_key_id (string)
   - authenticity_token_key (secret)
   - replay_store_backend (enum: diskcache)
   - replay_store_path (string; filesystem path for diskcache directory)
   - replay_store_size_limit_mb (int; optional limit for diskcache size)

2. Decide storage backend for nonce registry.
   - Use diskcache as the default and supported backend.
   - Ensure the cache directory is writable and monitored.

3. Specify how to identify the form:
   - Use a stable survey id and form_version id already used in submissions.

Deliverables:
- Updated configuration model and documentation.
- Operational decision on nonce storage.

### Phase 2: Token Issuance

1. Add a token issuance endpoint or embed token in the form render.
2. Ensure token includes:
   - jti (cryptographically random)
   - exp (short lifetime)
   - form_id and form_version
   - session_id/user_id if available
3. Ensure the token is sent to the client and stored in JS memory or a hidden field.

Deliverables:
- Token issuance logic and data fields defined.
- Updated template / JS workflow for obtaining the token.

### Phase 3: Submission Verification

1. Add token verification to submission views:
   - Parse token and verify signature with active or previous key (kid).
   - Validate exp/nbf/iat with small clock skew.
   - Verify form_id and form_version match current form.
   - Verify session/user binding if included.

2. Enforce replay protection with diskcache:
   - Perform an atomic check-and-set for jti in diskcache.
   - Reject if jti already consumed or if diskcache is unavailable (policy decision).

3. Ensure CSRF checks remain intact and run before token checks.

Deliverables:
- Server-side verification sequence defined.
- Clear rejection reason codes for clients.

### Phase 4: Logging and Monitoring

1. Add audit logs for:
   - token validation failures
   - replay detection
   - signature or claim failures

2. Add metrics (optional):
   - accepted vs rejected submissions
   - replay counts per form

Deliverables:
- Logging specification for security events.

### Phase 5: Key Management and Rotation

1. Define operational rotation steps:
   - Add new key with new kid
   - Accept both keys for a grace period
   - Remove old key after grace

2. Implement key lookup:
   - Choose key by kid when present
   - Fall back to current key for legacy tokens

Deliverables:
- Key rotation policy documented and testable.

### Phase 6: Optional Abuse Controls

1. Rate limiting (per form, per session, per IP).
2. Honeypot field for anonymous forms.
3. CAPTCHA for high-risk forms only.

Deliverables:
- Optional features documented and ready for staged rollout.

## Lifetime and Parameters (Recommendations)

- Token TTL:
  - Short forms: 5-10 minutes
  - Longer surveys: 30-60 minutes
- Clock skew allowance: 60-120 seconds
- Nonce registry TTL: token TTL + 2-5 minutes grace
- Key rotation: 1-7 days overlap

## Failure Modes and Policy Decisions

- Missing token: reject with explicit error message.
- Invalid signature: reject and log.
- Expired token: reject, ask client to reload.
- Replay detected: reject and log.
- Diskcache unavailable or read-only:
  - Strict mode: reject (highest security)
  - Lenient mode: allow but log (availability-first)

## Testing Plan

- Unit tests for token creation/validation claims.
- Integration tests for valid submission flow.
- Replay tests: re-submit same token, expect rejection.
- Rotation tests: validate with old key during grace.
- Anonymous vs authenticated binding tests.

## Rollout Plan

- Stage 1: enable token issuance and validation in monitoring-only mode.
- Stage 2: enforce validation and replay checks for a subset of forms.
- Stage 3: enforce globally with strict mode and rate limits.

## Backward Compatibility

- Keep CSRF unchanged.
- Token can be optional during staged rollout.
- Ensure no change to existing form schema format.

## Open Questions

- Which diskcache directory and size limit should be used in production?
- Should anonymous forms require token binding to session id or just form id?
- Should strict mode be enabled when diskcache is unavailable?
