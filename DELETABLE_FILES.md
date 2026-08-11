# DELETABLE_FILES.md

Inventory of files in this repository that are **not needed for a release**
and have only been used for development, analysis, demos, and similar
non-release purposes.

> Release context: `MANIFEST.in` ships exactly `src/zopyx` (graft), `docs`
> (graft), and all `*.rst` at repo root. The items in **section 1** and the
> `.rst` blog posts in **section 3** therefore end up inside the published
> sdist and should be removed before any release. Everything else is repo
> clutter that does not ship but is dead weight.

## 1. Junk / scratch files — WILL ship in the sdist, remove before release

- `src/zopyx/surveyjs/browser/x.html` — scratch file (`<marquee>Hello worls</marquee>`)
- `src/zopyx/surveyjs/browser/x.json` — scratch survey JSON
- `src/zopyx/surveyjs/browser/xx` — scratch JS snippet

These live inside the package, so `graft src/zopyx` puts them in the release.

## 2. Junk / scratch files — repo clutter, not shipped but dead weight

- `xx`, `xx.md`, `out`, `deactivate.png` — scratch files at repo root
- `scripts/x.js` — Plausible snippet scratch file
- `playwright-tests/x.py` — scratch (cuid2 test)
- `uv-plone62/.uv-plone62-setup.sh.swp` — vim swap file (untracked)
- `src/zopyx/surveyjs/locales/autopo.ooo` — autopo (i18n tool) config artifact
- `src/zopyx/surveyjs/browser/static/surveyjs/fetch_surveyjs.bash` — vendoring script for SurveyJS assets (dev-only, but ships inside `static/`)
- `src/zopyx/surveyjs/browser/static/surveyjs/download_creator_i18n.sh` — vendoring script for SurveyJS i18n assets (dev-only, but ships inside `static/`)

## 3. Blog post / marketing drafts

- `BLOG_POST_CUSY.md`, `BLOG_POST_CUSY_OUTPUT.md`
- `BLOG_POST_CUSY.rst`, `BLOG_POST_CUSY_OUTPUT.rst` — **these two DO ship** (root `*.rst`)!
- `BLOG_POST_CUSY.pdf`, `BLOG_POST_CUSY_OUTPUT.pdf`
- `marketing/2026-01-22/plone-announcement.md`

## 4. Analysis / design / planning docs (root level, dev-only)

- `ANALYSIS_2026-06-05.md`
- `AI.md`
- `AUDIT_LOGGING.md`
- `BOT_CONTROL.md`
- `CODE_ANALYZSIS_CLAUDE.md`
- `CONVERTERS.md`
- `CSRF_PROTECTION_CHANGES.md`
- `EMBEDDING.md`, `EMBEDDING2.md` — superseded by `docs/embedding.rst` (note: `AGENTS.md` still references them)
- `EXTENDED_SECURITY.md`
- `FORM_DATA_VALIDATION.md`
- `FORM_DATA_VALIDATION_IMPLEMENTATION.md`
- `IMPLEMENTATION_SUMMARY.md`
- `PHILOSOPHY.md`
- `PLAYWRIGHT_SCREENSHOTS.md`
- `PROPOSED_INTERMEDIATE_FORMAT.md`
- `SURVEYJS_JSON_FORMAT_RESEARCH.md`
- `TOKEN_STORE.md`
- `sec.md`
- `survey.md`
- `xx.md`

## 5. Buildout / dev configuration (not needed for the PyPI release)

- `buildout.cfg`, `base.cfg`, `dev.cfg`, `bobtemplate.cfg`, `.mr.developer.cfg`
- `test_plone52.cfg`, `test_plone60.cfg`, `constraints.txt`
- `tox.ini`, `.travis.yml`, `.gitlab-ci.yml`, `.pre-commit-config.yaml`
- `.env.encrypted`, `.webui_secret_key` — dev secrets, never ship

Keep: `requirements.txt` (buildout bootstrap, referenced by `AGENTS.md`),
`Makefile` (the `sdist.yml` release workflow runs `make sdist`).

## 6. Dev / demo tooling and data

- `embedding_demo1/` — embedding demo page
- `fillable_forms/` — PDF import analysis (sample PDFs, parse scripts)
- `sample_forms/` — demo sample data (found via walk-up in `views.py`; only works in a dev checkout, not in an installed package)
- `schema-validation/` — standalone Deno validation tooling (dev)
- `uv-plone62/` — Plone 6.2 uv-only install scripts/README
- `playwright-tests/` — Playwright screenshot automation (CI + Makefile)
- `scripts/forms/`, `scripts/export_i18n_js.py` — i18n generation sources
- `scripts/convert_blog_post.sh`, `scripts/filecrypt.py`
- `scripts/init_plone.py`, `scripts/build-run-docker.sh`, `surveyjs.licensekey` — demo-site bootstrap + SurveyJS license key (license key only used by `init_plone.py`, NOT by the package at runtime)
- `scripts/*.png/.jpg/.af`, `scripts/logos/` — demo/branding assets
- `mprocs.yaml` — dev process runner

## 7. CI workflows (dev/infra, not part of the release)

Dev-only:

- `.github/workflows/tests.yml`
- `.github/workflows/screenshots.yml`
- `.github/workflows/docker-image.yml`
- `.github/workflows/restarting.yml`
- `.github/actions/setup-plone-buildout/`
- `.github/dependabot.yml`
- `.github/ISSUE_TEMPLATE.md`
- `Dockerfile`, `.dockerignore` — demo image only

Keep for release: `.github/workflows/publish-pypi.yml`,
`.github/workflows/publish-testpypi.yml`, `.github/workflows/sdist.yml`.

## 8. IDE + AI-agent config (dev-only)

- `.idea/` (whole dir, incl. `workspace.xml`)
- `.vscode/settings.json`
- `.claude/skills/frontend-design/` — Claude skill
- `.opencode/`, `opencode.json`, `seed.spec.ts`, `specs/` — untracked OpenCode experiment
- `.github/agents/`, `.github/workflows/copilot-setup-steps.yml` — untracked agent configs

## 9. Local, untracked, invisible-to-git stuff (disk only)

- `app/` — Expo/React-Native mobile experiment (node_modules inside)
- `docs/html/` — Sphinx build output (**not** in `.gitignore`; a release built
  from a checkout containing it would fold it into the sdist via `graft docs`.
  Add `docs/html/` to `.gitignore`.)
- `plone62-uv/` — local Plone 6.2 instance (only ignored content)
- `uv.lock`, `.coverage`, `.pytest_cache`, `eggs/`, `parts/`, `bin/`, `var/`,
  `dist/`, `.venv` — local build/test artifacts (already ignored)

## 10. Gray area — planning docs inside `docs/` (they ship via `graft docs`)

Dev planning notes mixed into the shipped docs tree. The `.rst` files are the
real user-facing docs; consider moving these `.md` planning notes elsewhere:

- `docs/concept-sql-token-storage.md`
- `docs/functionality_pdf_import_form.md`
- `docs/functionality_results.md`
- `docs/global_settings.md`
- `docs/implementation-notes-itokenstore.md`
- `docs/security2.md`
- `docs/security-public-mode.md`
- `docs/security-trusted-token.md`
- `docs/security-trusted-tokens-onetime-use.md`
- `docs/survey_settings.md`
- `docs/trusted-token-audience-planning.md`

## Bottom line

- **Must delete before release** (ships in artifact): `browser/x.html`,
  `browser/x.json`, `browser/xx`, `BLOG_POST_CUSY.rst`,
  `BLOG_POST_CUSY_OUTPUT.rst` (plus the vendoring bash scripts in `static/`).
- **Repo hygiene** (not shipped, but dead weight): sections 2–8,
  roughly 150+ files/dirs.
- **Untracked local stuff** (section 9): add `docs/html/` to `.gitignore`.
