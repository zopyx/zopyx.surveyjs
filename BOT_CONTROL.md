# Bot Control Concept (Optional Verification)

## Goals
- Protect form submissions from automated abuse while keeping the UX low-friction.
- Keep privacy-first defaults (self-hostable, no external data sharing by default).
- Offer per-form policies and a layered defense so admins can tune sensitivity.

## Design Principles
- **Layered checks**: progressively apply defenses, only escalating if risk is high.
- **Server-side enforcement**: client checks are advisory; server decides accept/deny.
- **Privacy-first**: avoid third-party tracking by default; allow opt-in captchas.
- **Fail safe**: degrade gracefully (e.g., soft-block, queue for review) instead of hard failure.
- **Transparent configuration**: minimal required knobs, sensible defaults.

## Threat Model (Typical Abuse)
- High-volume scripted submissions (spam, data poisoning).
- Credential-stuffing for authenticated forms (out of scope for bot control).
- Replay attacks / token reuse.
- Form scraping and mass submission from headless browsers.

## Layered Defense Strategy

### 1) Passive Signals (No UX Impact)
- **Honeypot field**: hidden field that should remain empty.
- **Timing heuristics**: time-to-first-input, time-to-submit, dwell time.
- **Interaction patterns**: minimal mouse/touch events vs. human-like activity.
- **Submission velocity**: per-IP / per-user / per-form rate limits.
- **Payload heuristics**: repetitive content, known spam patterns, excessive URLs.
- **User agent sanity**: allowlist/denylist, detect obvious automation.

### 2) Soft Enforcement (Low Friction)
- **Progressive rate-limits**: throttling and cooldowns before hard blocks.
- **Proof-of-work (optional)**: short client-side puzzle when risk is medium.
- **Double-submit tokens**: one-time form tokens tied to session & origin.
- **Delayed submission**: introduce random jitter for suspicious sessions.

### 3) Active Challenges (Opt-In)
- **Non-intrusive captchas**:
  - Cloudflare Turnstile (recommended privacy-friendly SaaS option).
  - hCaptcha / reCAPTCHA (enterprise compatibility).
- **Self-hosted alternatives**:
  - Text/image challenge from local dataset.
  - Email verification for high-risk forms.

### 4) Administrative Controls
- **Blocklists/allowlists**: IP, CIDR, country, ASN, or email domain.
- **Audit log**: reason codes and risk scores for each submission.

## Risk Scoring Model
Compute a **risk score (0–100)** based on weighted signals:
- Honeypot triggered (+80).
- Velocity threshold exceeded (+30).
- Very short time-to-submit (+20).
- Suspicious UA (+15).
- Repeated payloads (+25).
- Missing JS tokens (+20).

Decision policy (configurable):
- **0–29**: accept.
- **30–59**: accept + log.
- **60–79**: require challenge.
- **80+**: reject or queue for review.

## Configuration Model (Per Form + Global Defaults)
- `bot_control.enabled` (bool, default: false)
- `bot_control.mode` (`passive` | `adaptive` | `strict`)
- `bot_control.challenge_provider` (`none` | `turnstile` | `hcaptcha` | `recaptcha` | `self_hosted`)
- `bot_control.rate_limits` (per IP/user/form, burst + window)
- `bot_control.risk_thresholds` (accept/log/challenge/reject)
- `bot_control.audit` (enable logging + retention)

## UI/UX Concepts
- Admin UI: “Bot Protection” panel per **public** form with presets (Low/Medium/High).
- End-user: only see a challenge when risk is high.
- Provide clear error messaging and fallback (retry, contact link).

## Integration Points (Conceptual)
- **Frontend**: inject token + optional JS telemetry only when enabled.
- **Backend**: verify tokens, compute risk score, enforce policy.
- **Storage**: store decision metadata with submission (score + reasons).

## Privacy & Compliance
- Default: no third-party calls.
- Explicit consent required if enabling external captchas.
- Document data flows and retention for audit logs.

## Phased Rollout
1. **Phase 1**: Passive signals + rate limits + audit logging.
2. **Phase 2**: Risk scoring + adaptive challenges.
3. **Phase 3**: Optional third-party captcha integrations.

## Decisions / Constraints
- **Authenticated surveys**: no bot control needed by default.
- **Public surveys**: bot control optional and configurable.
- **No manual approval**: enforcement must be accept/log/challenge/reject only.

## Open Questions
- Required compatibility with headless or API-based submissions?
