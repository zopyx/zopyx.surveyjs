# Plone 6.2 with uv — no buildout

A minimal, buildout-free way to get a Plone 6.2 site running with
`zopyx.surveyjs` installed, using only [uv](https://docs.astral.sh/uv/).

## Why this exists

The classic Plone install path uses buildout (`./bin/buildout`), which pulls
in a long `versions.cfg` chain and the `plone.recipe.zope2instance` recipe.
Plone 6.2 is a plain pip distribution, so the entire toolchain can be reduced
to `uv venv` + `uv pip install Plone`. This directory documents and automates
that path.

## What is needed (the recipe)

| Step | Command | Notes |
|------|---------|-------|
| 1. venv | `uv venv --python 3.13 .venv` | Plone 6.2 needs >=3.10; `zopyx.surveyjs` needs >=3.12,<3.14 → use 3.13 |
| 2. Plone | `uv pip install --python .venv/bin/python "Plone==6.2.1"` | The `Plone` meta-package; no buildout, no versions.cfg |
| 3. this package | `uv pip install --python .venv/bin/python -e ../src` | editable install of `zopyx.surveyjs` |
| 4. siblings | `uv pip install --python .venv/bin/python "privacyforms.theme @ git+https://github.com/zopyx/privacyforms.theme.git" "privacyforms.ai @ git+https://github.com/zopyx/privacyforms.ai.git" "privacyforms.pdf @ git+https://github.com/zopyx/privacyforms.pdf.git"` | `zopyx.surveyjs` imports these at ZCML load time; buildout used to fetch them via `auto-checkout` |
| 5. instance | `.venv/bin/mkwsgiinstance -d instance -u admin:adminpw` | `-u` avoids the interactive getpass prompts |
| 6. run | `.venv/bin/runwsgi instance/etc/zope.ini` | serves on 127.0.0.1:8080 by default |
| 7. create site | `curl -u admin:adminpw -X POST http://127.0.0.1:8080/++api++/@sites/classic -H "Content-Type: application/json" -d '{"site_id": "Plone", "title": "Plone", "default_language": "en", "portal_timezone": "UTC"}'` | Plone 6.2 distributions: `classic` or `volto` |
| 8. install add-on | `curl -u admin:adminpw -X POST http://127.0.0.1:8080/Plone/@addons/zopyx.surveyjs/install` | `204` = ok |

## One-command automation

```bash
./uv-plone62/uv-plone62-setup.sh /tmp/plone62-uv
```

Environment overrides: `SITE_ID`, `ADMIN_USER`, `ADMIN_PASS`, `PORT`.

## Pitfalls (learned the hard way)

- **`product_distribution Plone` is gone.** Zope 6's `wsgischema.xml` no
  longer defines `<productdistributions>`; adding it makes Zope refuse to
  start (`unknown type name`). Plone 6.2 registers itself via
  `plone.autoinclude` — nothing to add to `zope.conf`.
- **The old `@@ploneAddSite` wizard form field is `form.submitted:boolean`**
  (ZPublisher `:boolean` suffix), and the SPA behind it posts JSON. Don't
  fight the browser flow — use the REST service `@sites` instead.
- **Site creation needs a request context.** Calling
  `plone.distribution.api.site.create()` from a bare
  `configure_wsgi(); Zope2.app()` script fails with
  `'Application' object has no attribute 'utilities'`. The supported path is
  the `@sites` REST endpoint (`++api++/@sites/<distribution>`) — it runs
  inside a real request and handles CSRF itself.
- **The `privacyforms.*` siblings are required.** `browser/ai.py` imports
  `privacyforms_ai` at module level, so ZCML loading fails without them.
  They are not declared in `setup.py` `install_requires` — with buildout the
  `[sources]`/`auto-checkout` machinery handled that; with uv you must
  install them explicitly (step 4).
- **`mkwsgiinstance` prompts via getpass** (reads from the TTY, not stdin).
  Use `-u NAME:PASSWORD` to make it non-interactive.
- **Python version matters.** `zopyx.surveyjs`'s `setup.py` rejects Python
  <3.12 and >=3.14 (a Rust dependency without 3.14 wheels); Plone 6.2 works
  on 3.13. Pin 3.13.
- **JSON POSTs to `@@ploneAddSite` return the overview page silently** — the
  `AddPloneSite.__call__` reads `request.form`, which ZPublisher does not
  populate from JSON bodies. Use `++api++/@sites/...` (a plone.restapi
  service that reads `json_body(request)`).

## Requirements to install

Plone 6.2.1 + `zopyx.surveyjs` requires about 600 MB of packages in the
venv (including weasyprint, llm, sqlmodel, pillow). First boot takes ~20s;
site creation via `@sites/classic` takes a few seconds.

## Stopping

```bash
kill $(pgrep -f "runwsgi instance/etc/zope.ini")
```
