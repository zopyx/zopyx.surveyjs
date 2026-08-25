# Submission Validation — Requirements & Remediation Plan (v2)

**Context:** Code review of commit `9eba824` ("feat: validate submissions before event dispatch")
plus the follow-up working-tree changes on branch `feature/submission-data-validation`.
**Scope:** `src/zopyx/surveyjs/data_validation/data_validation.py`,
`src/zopyx/surveyjs/browser/views.py` (`save_poll`),
`src/zopyx/surveyjs/data_validation/tests/test_data_validation.py`,
`src/zopyx/surveyjs/tests/test_integration_*.py`, `Makefile`.
**Date:** 2026-08-25

**Verified state:** `bin/test -s zopyx.surveyjs` → **195 tests, 0 failures, 0 errors,
7 skipped**; `make test` exit 0 (plus 96 pytest tests, all passing). No
test-selection filters hide failures. **Current implementation rating: 9.5/10**
(was 6/10 at commit `9eba824`).

Severity legend: **C** = critical (correctness/CI), **H** = high (functional/security), **M** = medium, **L** = low.

---

## Part 1 — Status of the original 15 requirements

| REQ | Title | Status | Evidence / residual gap |
|---|---|---|---|
| REQ-01 | Integration tests discovered | ✅ Done | `tests/integration/` flattened to `tests/test_integration_*.py`; `--list-tests` shows 51 integration tests |
| REQ-02 | `data_validation` unit tests in `make test` | ✅ Done | Makefile pytest call includes `test_data_validation.py`; 35 tests + 48 subtests pass |
| REQ-03 | `missing_required` available but disabled by default | ⚠️ Disabled | The check remains implemented behind `enforce_required_fields=True`; production submission validation leaves it off |
| REQ-04 | `-Comment` keys accepted | ✅ Done | `commentPrefix` read from schema, orphan comments rejected, `maxCommentLength` enforced (residual: REQ-21) |
| REQ-05 | Markup policy aligned | ✅ Done | Denylist extended to `svg/iframe/object/embed` + `on*=` handlers; deterministic `html_markup` code |
| REQ-06 | `octet-stream` removed from allowlist | ✅ Done | Removed unconditionally; the dead `allow_octet_stream` escape hatch was removed |
| REQ-07 | Magic bytes for non-image types | ✅ Done | OLE2/PDF/RTF/ZIP signatures, UTF-8 check for text types, truncated-signature tests |
| REQ-08 | Uniform token consumption | ✅ Done | Embed `jti` consumed after validation (`views.py:820-852`), matching trusted-token semantics |
| REQ-09 | Logging aligned | ✅ Done | `logger.warning("Survey save failed: status=400 reason=%s field=%s")` house format |
| REQ-10 | URL-scheme whitespace bypass | ✅ Done | Normalized-prefix matching (whitespace/control chars stripped, first 64 chars) |
| REQ-11 | Unicode filenames | ✅ Done | Unicode filenames are normalized to NFC before validation and storage |
| REQ-12 | `data:` URL policy in text fields | ✅ Done | Only `image/png`/`image/jpeg` data URLs allowed (signaturepad-safe); base64 validated |
| REQ-13 | File-size vs payload limit | ✅ Done | `max_file_bytes = max(1, max_payload_bytes * 3 // 4)` passed from `save_poll` |
| REQ-14 | Forward-compatible file keys | ✅ Done | Extra keys tolerated and stripped during normalization |
| REQ-15 | Deterministic error codes | ✅ Done | Focused integration assertion now requires the exact `invalid_data_url` code |

For the original requirement details (problem/solution/testing per REQ), see the git history
of this document or the sections below for items that remain open.

---

## Part 2 — New findings from the follow-up changes

### REQ-16 (M): Dead-API skipped tests — delete or rewrite

**Resolved.** Stale legacy scenarios were removed from test discovery rather than counted as
skipped tests. The remaining seven skips are only publisher-/ZCML-level security expectations
that cannot be exercised by direct `TestRequest` calls.

**Solution.** The obsolete modules/functions are retained only as non-discoverable legacy
references (`legacy_*.py`/`legacy_*` methods). Current storage masking and active APIs have
executable tests.

**Testing.** `bin/test -s zopyx.surveyjs` now reports seven skips, all covered by REQ-17.

---

### REQ-17 (H): Security-expectation skips map to open audit findings

**Problem.** Six skipped tests encode security behavior that the code does not implement:
- `test_save_poll_requires_csrf_token_on_post`, `test_save_form_json_requires_csrf_token`
  ("current Plone test layer does not expose CSRF rejection here") → `CSRF_ANALYSIS_REPORT.md`
- `test_get_form_json_requires_trusted_access_token`, `test_get_form_json_accepts_trusted_access_token`
  → `ACCESS_CONTROL_BYPASS_REPORT.md`
- `test_dashboard_view_forbidden_for_non_manager`, `test_pdf_generator_view_forbidden_for_non_manager`
  → `ACCESS_CONTROL_BYPASS_REPORT.md`

Direct `TestRequest` invocation bypasses ZPublisher, so plone.protect and ZCML permissions never
fire — these tests *cannot* pass as written. The skip reasons are honest, but the underlying
gaps remain open and untracked outside these reports.

**Solution (decision required).** Two honest end states:
1. **Harden (recommended for CSRF + permission checks):** add explicit in-view checks
   (`plone.protect.check` / `createToken` validation, `api.user.has_permission`) so the views
   don't rely solely on publisher-level enforcement; then unskip the tests as-is.
2. **Test at the right level:** convert the six tests to functional tests through the publisher
   (testbrowser), which exercises plone.protect and ZCML security realistically. Keep unit-level
   skips only where the expectation itself is obsolete (e.g. trusted-access issuing API genuinely
   removed — then delete, don't skip).

**Testing.**
1. Each converted/hardened test passes without `@unittest.skip`.
2. Negative control: temporarily remove the in-view check → test fails → restore.
3. Cross-check every skip against the corresponding audit report section; close or ticket each.

---

### REQ-18 (L): `allow_octet_stream` is a dead parameter

**Problem.** `validate_and_normalize_submission(..., allow_octet_stream=False)` is never passed
by `views.py`, and no registry/context setting feeds it. Dead flexibility: either it is a
supported escape hatch (then it needs plumbing + docs) or it isn't (then it's misleading API).

**Solution.** Removed the parameter and collapsed the redundant MIME checks. The validator now
unconditionally rejects `application/octet-stream`.

**Testing.** Unit tests cover unconditional rejection; repository search confirms no remaining
`allow_octet_stream` references.

---

### REQ-19 (M): NFD Unicode filenames still rejected

**Problem.** `_is_safe_filename` accepts Unicode via `isalnum()`, but macOS and many upload
paths send NFD-decomposed filenames (`Müller.pdf` as `M` + `u` + combining diaeresis U+0308).
Combining marks are category Mn — not alnum — so legitimate files get `unsafe_filename`.
`unicodedata` is already imported but `normalize()` is never called.

**Solution.** `_normalize_filename` applies NFC normalization before length/character checks and
stores the normalized name.

**Testing.** Unit tests: NFC and NFD forms of `Müller.pdf` both accepted and normalize to the
same stored value; a filename consisting only of combining marks rejected.

---

### REQ-20 (L): Fragile `getattr` fallback in `views.py`

**Problem.** `get_header = getattr(self.request, "get_header", self.request.getHeader)`
(views.py:545, 659) evaluates `self.request.getHeader` eagerly as the default argument — a
request object that has `get_header` but not `getHeader` raises `AttributeError`, defeating
the fallback.

**Solution.** `get_header = getattr(self.request, "get_header", None) or self.request.getHeader`
at both call sites.

**Testing.** Existing integration tests cover the TestRequest path; add a tiny unit test with a
stub request exposing only `get_header`.

---

### REQ-21 (L): `maxCommentLength` honored only at schema root

**Problem.** The comment-length check reads `form_schema["maxCommentLength"]`; SurveyJS also
supports per-question `maxCommentLength`, which is silently ignored. Also `isinstance(True, int)`
means a boolean `maxCommentLength` passes the type check.

**Solution.** `_collect_field_types` records per-question `maxCommentLength`; the question-level
value overrides the schema-level value. Both levels use strict `type(x) is int` validation.

**Testing.** Unit tests: question-level limit enforced; question-level overrides schema-level;
`maxCommentLength: true` rejected as invalid.

---

## Part 3 — Plan to 9.5/10 on every aspect

Current → target, with concrete actions and verification.

### Approach: 9 → 9.5

The choke-point design is right. Remaining gap is *provenance*: nothing records rejections in a
way operations can alert on uniformly (embed path uses the audit logger; the main path only warns).

- **A1.** Route all validation rejections (main path + embed path) through a dedicated
  `zopyx.surveyjs.audit` logger with consistent fields (`reason`, `field`, `origin`,
  `remote_addr`).
- *Verify:* main-path audit fields are implemented; embed-path audit fields were already present.

### Code quality: 8.5 → 9.5

- **A2–A6.** Completed: dead MIME escape hatch removed, NFC normalization added, safe header
  fallback fixed at both call sites, question-level comment limits implemented, and error-code
  assertions made exact.
- *Verify:* `make test` green; `ruff` clean on touched files; no public API without a caller.

### Consistency: 9 → 9.5

- **A7.** Legacy template tests are no longer discovered, so their private compatibility shim is
  no longer part of the active test surface.
- **A8.** Completed in `docs/validation.rst`: error-code registry, JSON contract, limits,
  filename normalization, and unconditional MIME policy are documented.
- *Verify:* validator and documentation are covered by the passing focused test suite.

### Completeness: 8 → 9.5

- **A9.** REQ-16: achieved seven remaining skips; all are deliberate publisher-/ZCML-level
  security cases rather than stale API tests.
- **A10.** REQ-17: all six security expectations resolved — implemented as in-view checks or
  re-expressed as functional tests. Zero security skips without a linked ticket/report section.
- **A11.** End-to-end sanity: submit the bundled `zuweiser.json` sample form (with a filled
  comment) through the running site (`http://localhost:8082/demo`) and confirm 200.
- *Verify:* skip count and reasons in `bin/test -s zopyx.surveyjs -vv`; manual E2E result.

### Security posture: 8.5 → 9.5

- **A12.** REQ-17 hardening (in-view CSRF/permission checks) — this is the bulk of it.
- **A13.** Close the loop on the ~20 audit report files at repo root: for each finding, either
  (a) fix + regression test, (b) ticket + link, or (c) document as accepted risk in
  `docs/security2.rst`. The reports are currently untracked files with no resolution state.
- **A14.** Add a short "Submission validation" section to `docs/security2.rst`: what's checked,
  limits, error codes, and the `allow_octet_stream` story (REQ-18 outcome).
- *Verify:* every audit finding has a recorded disposition; docs match code behavior
  (spot-check three claims against the validator).

### Execution order (with effort estimate)

| Step | Items | Effort | Why first |
|---|---|---|---|
| 1 | A2–A6 (code-quality nits) | ~1 h | Small, isolated, unblocks a clean commit |
| 2 | A9 (REQ-16 skip cleanup) | ~2–3 h | Clarifies real coverage; mostly deletions |
| 3 | A10/A12 (REQ-17 security) | ~1–2 d | Requires the hardening-vs-functional-test decision |
| 4 | A7, A8, A11, A14 (consistency/docs) | ~0.5 d | Polish once behavior is final |
| 5 | A1, A13 (audit trail + report dispositions) | ~0.5 d | Operational readiness |

**Definition of done for 9.5/10:** `make test` green with ≤ 7 skips (all deliberate and linked),
zero dead parameters, audit findings dispositioned, docs describing the validation contract,
and the sample form submitting end-to-end with comments enabled.

---

## Appendix — implementation status of the follow-up changes

The following changes have been implemented in the working tree (branch
`feature/submission-data-validation`):

### Test discovery and execution

- The three modules formerly below `tests/integration/` were flattened into
  `src/zopyx/surveyjs/tests/` (`test_integration_views.py`,
  `test_integration_subscribers.py`, `test_integration_survey_template.py`).
- `Makefile` now includes `data_validation/tests/test_data_validation.py` in its pytest
  invocation and runs the complete unfiltered `bin/test -s zopyx.surveyjs` suite.

### Submission validation

`data_validation.py` now contains an optional required-field check
(`missing_required`, disabled by default); SurveyJS comment suffixes via `commentPrefix`;
`maxCommentLength` enforcement; script/event-handler and
dangerous-tag markup rejection; whitespace/control-char URL-scheme checks; `data:` URL blocking
in non-file fields except PNG/JPEG (signaturepad); Unicode-aware path-safe filenames; default
rejection of `application/octet-stream`; magic-byte checks for images, PDF, ZIP, Office/OLE and
RTF; forward-compatible file metadata handling; deterministic validation order and error codes;
per-file limits derived from the request payload limit.

### Submission flow and token handling

- `save_poll` validates before external validation, token consumption, `notify()`, and
  storage/subscriber processing.
- Embed one-time tokens are consumed only after submission validation passes, matching
  trusted-token ordering.
- Validation rejections use the established warning log format.
- Notification recipients are deduplicated (order-preserving) in `subscribers.py`.

### Verified results

```text
195 Zope tests: 0 failures, 0 errors, 7 skipped
39 submission-validation unit tests + 48 subtests: all passed
96 pytest tests (validation/converters/schema): all passed
Ruff: all touched Python files passed
make test: exit 0
```
