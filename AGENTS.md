# AGENTS.md

This repository is a Plone add-on that integrates SurveyJS. It is primarily a Python/Plone buildout project, with supporting bun/deno tooling for data validation.

## Quick Orientation
- Python/Plone package lives under `src/`.
- Buildout configs: `buildout.cfg`, `dev.cfg`, `test_plone52.cfg`, `test_plone60.cfg`.
- Validation binary (bun/deno) in `src/zopyx/surveyjs/data_validation/` (auto-built at runtime; see `docs/installation.rst`).
- Docs: `README.md`, `DEVELOP.rst`, `docs/`.

## Setup (Buildout, uv)
1. Create a virtualenv in the repo root:
   `uv venv --clear`
2. Install requirements:
   `uv pip install -r requirements.txt`
3. Run buildout:
   `./bin/buildout`
4. Start Plone in foreground:
   `./bin/instance fg`
5. or Start Plone in background:
   `./bin/instance start`
6. or stop Plone running in background:
   `./bin/instance stop`


## Site root

The site root is 

http://localhost:8082/demo


## Login 

You can login through http://localhost:8082/demo/login

Login in as user `forms` and password `formsarecool` which gives you the Plone `Editor`role.


See `DEVELOP.rst` for details.

## Tests
- Run tests via Makefile (uses `uv` + coverage):
  `make test`

## Validation Binary (bun/deno)
- Sources and build tooling live in `src/zopyx/surveyjs/data_validation/`
  (`validate.mjs`, `Makefile`, `package.json`, `deno_build.py`). There is no
  `data-validation/` directory at the repo root.
- At runtime the wrapper `validate_data.py` expects the platform binary
  (`validate-linux` / `validate-mac`) **next to the module** and builds it
  automatically (it downloads Deno itself) when missing or older than 5 days.
- Manual builds (bun or deno compile) write to `dist/` via the package
  Makefile (`make all`, `make deno`) for packaging/distribution; copy the
  binary next to the module to activate server-side validation.
- Full build instructions: `docs/installation.rst` → "External survey
  validation (deno / bun)".

## Working Guidelines
- Prefer small, focused changes with clear diffs.
- Avoid introducing new dependencies without a strong reason.
- Keep buildout configs consistent; update `requirements.txt` only when needed.
- If touching security- or validation-related code, add or update tests.

## Git Operations
- **NEVER commit automatically.** Always ask the user for explicit confirmation before committing.
- **Run tests yourself:** Before asking to commit, run `make test` (or `bin/test -s zopyx.surveyjs`) yourself.
- **If tests pass:** Ask the user for permission to commit and push.
- **If tests fail:** Fix the issues first, then ask for permission to commit.
- Use Conventional Commits for all commit messages with **extensive/detailed descriptions**.
- Example format:
  ```
  feat: add token store adapter for survey access control
  
  - Implement ITokenStore interface with generate_tokens(), has_token(), invalidate()
  - Use BTrees.OOBTree for efficient ZODB storage
  - Add browser view @@token-store for token management
  - Generate 32-character URL-safe tokens using secrets.token_urlsafe()
  - Add CSV download of unused tokens
  - Include comprehensive test coverage
  
  All 67 tests pass.
  ```
- Be explicit and verbose in commit messages. Prefer extensive descriptions over short, ambiguous ones.
- Do not commit if tests are failing or were not run, unless the user explicitly approves and the commit message states this clearly.

## Notes for Agents
- This is a buildout-based Plone add-on; do not assume pip-only workflows.
- When unsure about config or build steps, consult `DEVELOP.rst` and `README.md`.
