# Direct Embedding Findings (Re-evaluated)

Last re-evaluated: 2026-03-04

## Current findings

### 1. No rate limiting on embed endpoints (High)

There is still no throttling on token generation/config/submission paths (`@@embed-token`, `@@embed-config`, `@@save-poll` embed branch).

- `src/zopyx/surveyjs/browser/embed_direct.py:38`
- `src/zopyx/surveyjs/browser/embed_direct.py:131`
- `src/zopyx/surveyjs/browser/views.py:801`

### 2. `embed_direct_max_origins` global setting is not enforced (Medium)

`get_embed_direct_max_origins()` is imported but unused; effective limit currently comes from schema `max_length=10`, not from the registry control panel setting.

- `src/zopyx/surveyjs/browser/embed_direct.py:29`
- `src/zopyx/surveyjs/browser/embed_security.py:295`
- `src/zopyx/surveyjs/content/survey.py:305`

### 3. Open Shadow DOM exposes form DOM to host-page JavaScript (Medium)

`attachShadow({ mode: 'open' })` allows same-page scripts to inspect/modify field values.

- `src/zopyx/surveyjs/browser/embed_direct.py:449`

### 4. Demo page reveals active token in clear text (Low/Operational)

`@@embed-direct-demo` still displays and offers copy of the live write-capable token. This is acceptable for trusted admin/editor use but increases accidental leakage risk.

- `src/zopyx/surveyjs/browser/embed_direct.py:914`
- `src/zopyx/surveyjs/browser/embed_direct.py:916`

### 5. Missing automated tests for direct embedding flows (Low)

No integration tests currently cover `@@embed-token`, `@@embed-config`, `@@embed-loader`, `@@embed-surveyjs`, or embed submission with `X-Embed-Token`.

- `src/zopyx/surveyjs/tests/integration/test_views.py`
- `src/zopyx/surveyjs/browser/configure.zcml:446`

## Resolved since previous revision

- Global kill-switch bypass: fixed by checks in config view, demo view, and embed submission path.
  - `src/zopyx/surveyjs/browser/embed_direct.py:141`
  - `src/zopyx/surveyjs/browser/embed_direct.py:641`
  - `src/zopyx/surveyjs/browser/views.py:930`
- Replay fail-open: fixed; cache-unavailable now fails closed.
  - `src/zopyx/surveyjs/browser/embed_security.py:323`
- Trailing-slash origin mismatch: fixed; schema now rejects trailing slash.
  - `src/zopyx/surveyjs/content/survey.py:102`
- SRI missing: fixed; loader now computes and applies SHA-384 integrity + `crossOrigin='anonymous'`.
  - `src/zopyx/surveyjs/browser/embed_direct.py:295`
  - `src/zopyx/surveyjs/browser/embed_direct.py:560`
  - `src/zopyx/surveyjs/browser/embed_direct.py:572`
- Added dedicated asset endpoint for CORS-safe SurveyJS script serving.
  - `src/zopyx/surveyjs/browser/embed_direct.py:238`
  - `src/zopyx/surveyjs/browser/configure.zcml:446`

## Updated ratings (0..10)

- Functionality completeness: **9/10**
- Security posture: **7/10**
- EMBEDDING2.md accuracy vs current implementation: **4/10** (document is now significantly stale)

## Validation limits

Re-evaluation performed by source inspection against current workspace files. Runtime tests were not executed in this pass.
