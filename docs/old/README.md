# docs/old — historical notes, NOT authoritative

Everything in this directory is a snapshot of an earlier design or
implementation phase. It is **not** part of the documentation build
(`docs/*.rst` is authoritative), it is **not** shipped in the source
distribution (`MANIFEST.in` prunes this directory), and parts of it describe
features that have been **removed** from the code base.

Do not use these files as a reference for current behaviour. Known
misleading examples:

| File | Why it is outdated |
|---|---|
| `functionality_pdf_import_form.md` | documents the removed `@@import-pdf-form` LLM importer; there is no view, no template and no `ai_generator` module any more |
| `EMBEDDING.md`, `EMBEDDING2.md` | superseded by `docs/embedding.rst` |
| `FORM_DATA_VALIDATION.md`, `FORM_DATA_VALIDATION_IMPLEMENTATION.md` | superseded by `docs/validation.rst` and `SUBMISSION_VALIDATION_REQUIREMENTS.md` |
| `TOKEN_STORE.md`, `implementation-notes-itokenstore.md`, `concept-sql-token-storage.md` | superseded by `docs/storage.rst` and the KV facade |
| `global_settings.md`, `survey_settings.md`, `survey.md`, `CONVERTERS.md`, `AI.md`, `AUDIT_LOGGING.md`, `BOT_CONTROL.md`, `EXTENDED_SECURITY.md`, `PHILOSOPHY.md`, `PLAYWRIGHT_SCREENSHOTS.md`, `PROPOSED_INTERMEDIATE_FORMAT.md`, `SURVEYJS_JSON_FORMAT_RESEARCH.md`, `sec.md`, `security2.md`, `security-public-mode.md`, `security-trusted-token*.md`, `trusted-token-audience-planning.md`, `CODE_ANALYZSIS_CLAUDE.md`, `IMPLEMENTATION_SUMMARY.md` | historical design notes, partly describing removed or renamed features |

For the current state see `docs/index.rst`; for what is deliberately not
implemented see `docs/limitations.rst`.
