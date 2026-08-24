# Trusted-Token Audience Extensions (Planning)

## Overview
Survey already has a trusted-token mode. The requested extension is an invite-only audience workflow per survey, based on uploaded lists (CSV with name/email). The system sends individualized survey links protected by single-use tokens. This document sketches concepts, risks, and decisions rather than implementation.

## Goals
- Allow per-survey audience upload (CSV).
- Issue unique tokens per audience entry and email personalized links.
- Support one-time access semantics with clear user/admin experience.
- Handle incremental audience list updates safely.

## Core Design Questions
- Identity key: email only, or email + external ID?
- Token semantics: one-time on submit vs one-time on first open.
- Reopen policy: allow resuming drafts, or final submit only?
- Link validity: no expiry, fixed expiry, or rolling expiry from send?

## Audience List Ingestion
- Validate CSV schema (min: name, email). Optional external ID.
- Deduplicate by chosen identity key.
- Provide a preview/diff before applying changes to avoid accidental mass updates.

## Audience Entry States
Suggested per-entry states:
- New
- Invited (token issued)
- Link Sent
- Opened
- In Progress
- Completed
- Revoked

These states must survive list updates and be auditable.

## Incremental Updates
The key risk is breaking idempotency and existing progress.

Recommendations:
- Preserve existing entry state when re-uploading the list.
- New entries: create token and mark for invite.
- Existing entries with changed metadata (name): update metadata, keep token.
- Removed entries: soft-remove or revoke; retain audit trail.
- Provide a diff view before applying updates.

## Lost Links and Resends
Resending creates security and UX tradeoffs.

Options:
- Resend same token: simple, but leakage risk remains.
- Issue new token: safer, but can break in-progress users.

Recommendation:
- Default to resend same token.
- Provide explicit “reset link” action that invalidates old token with warning.
- Log all resends and resets.

## Token Semantics and Security
- Tokens should be long, random, and scoped to survey + entry.
- Avoid PII in URLs; map token to entry server-side.
- One-time semantics should be enforced at submit (preferred), not at first open, to allow resuming.
- Optional token expiry can reduce link leakage but may harm long-running surveys.

## Email Delivery and Throughput
Plone mass email can be slow and may hit provider limits.

Considerations:
- Batch sending and rate limits.
- Background queue to avoid blocking.
- External SMTP or delivery service for scale and tracking.
- Track sent/bounced/opened/clicked if available.

## UX for Admins
- Per-survey audience manager with statuses.
- “Send invites to new entries only.”
- Manual resend/reset per entry.
- Summary metrics: total invited, opened, completed.

## UX for Invitees
- Clear messaging for expired/revoked/used links.
- If already completed, show confirmation rather than error.
- If link reset, old link should explain replacement.

## Edge Cases
- Shared inboxes: need external ID to distinguish people.
- Forwarded emails: token misuse; consider optional email confirmation step.
- Partial submissions: allow resume to avoid frustration.

## Audit and Compliance
- Log list uploads, entry changes, sends, and token resets.
- Retain audit trail even for removed entries.
- Ensure data retention and consent policies are documented.

## Default Policy Suggestions
- Identity key: email (plus optional external ID if available).
- Token validity: until completion or explicit revocation.
- Resend: same token; reset link only when explicitly requested.
- List update: add new, keep existing, soft-remove deletions.
