# AGENTS.md

This repository is a Plone add-on that integrates SurveyJS. It is primarily a Python/Plone buildout project, with supporting JS/Deno tooling for data validation.

## Quick Orientation
- Python/Plone package lives under `src/`.
- Buildout configs: `buildout.cfg`, `dev.cfg`, `test_plone52.cfg`, `test_plone60.cfg`.
- Deno validator in `data-validation/` (see its README).
- Docs: `README.md`, `DEVELOP.rst`, `docs/`, `EMBEDDING.md`.

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

## Deno Validator
- Build steps and usage are in `data-validation/README.md`.
- The built Deno binary should be placed in `data-validation/dist` (per `README.md`).

## Working Guidelines
- Prefer small, focused changes with clear diffs.
- Avoid introducing new dependencies without a strong reason.
- Keep buildout configs consistent; update `requirements.txt` only when needed.
- If touching security- or validation-related code, add or update tests.

## Notes for Agents
- This is a buildout-based Plone add-on; do not assume pip-only workflows.
- When unsure about config or build steps, consult `DEVELOP.rst` and `README.md`.
