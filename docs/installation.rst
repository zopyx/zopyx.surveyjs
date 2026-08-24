============
Installation
============

This package is a Plone add-on. Installing it has two parts: setting up the
package in a Buildout-based Plone project, and — optionally — building the
external survey validator binary. The toolchain is managed with ``uv``; the
Plone instance itself is still assembled by Buildout.

Prerequisites
=============

* Python 3.13 (downloaded and managed automatically by ``uv``)
* ``uv`` (see https://docs.astral.sh/uv/)
* A Buildout-based Plone project (Plone 5.2 or 6.0; the repository ships
  ``test_plone52.cfg`` and ``test_plone60.cfg`` buildout configurations)
* Only for the optional validator build: ``bun`` or ``deno`` on the PATH
  (the add-on can also fetch Deno itself, see below)

Setup with uv (recommended)
===========================

The repository is set up with ``uv``-managed virtual environments; the same
recipe works for a fresh checkout and for the development instance:

.. code-block:: shell

    # 1. Create the virtual environment in the repository root
    uv venv --clear

    # 2. Install the pinned toolchain (zc.buildout 5.2, setuptools, …)
    uv pip install -r requirements.txt

    # 3. Run buildout — generates bin/instance, bin/test, bin/zopepy, …
    ./bin/buildout

    # 4. Start Plone
    ./bin/instance fg          # foreground
    # or: ./bin/instance start # background
    # or: ./bin/instance stop

The development site root is http://localhost:8082/demo; log in with
``forms`` / ``formsarecool`` (Editor role) or the admin account from the
buildout configuration.

Why uv?

* ``uv pip install`` is dramatically faster than classic pip and uses a
  shared content-addressed cache.
* ``requirements.txt`` pins the buildout toolchain
  (``zc.buildout==5.2.0``, ``setuptools==81.0.0``, …), so buildout runs in
  a reproducible environment regardless of the system Python.
* The same uv-managed environment is used by the Makefile targets
  (``make test``, ``make docs``, ``make sdist``).

Buildout
========

Classic buildout installation of the add-on itself:

1. Add ``zopyx.surveyjs`` to your buildout eggs and rerun buildout.

   .. code-block:: ini

      [buildout]
      eggs +=
          zopyx.surveyjs

2. Restart Plone and install the add-on in the **Add-ons** control panel.

3. The buildout generates the usual scripts: ``bin/instance`` (Plone),
   ``bin/test`` (Plone test runner) and ``bin/zopepy`` (Python interpreter
   with the Zope environment). The Makefile's ``make test`` runs the test
   suite through these scripts with coverage.

Verifying the installation
==========================

Run the test suite to confirm everything is wired up correctly:

.. code-block:: shell

    make test

External survey validation (deno / bun)
=======================================

The optional "Force Server Side Validation" feature (per-survey setting,
default on) runs every submission through an external validator binary. The
validator is a single compiled executable built from
``validate.mjs`` (SurveyJS schema checks against ``survey-core`` 3.x), so no
Node.js runtime is needed on the Plone host.

Source layout

The validator lives in ``src/zopyx/surveyjs/data_validation/``:

* ``validate.mjs`` — the validation script (ESM, imports ``survey-core``).
* ``package.json`` / ``bun.lock`` — the ``survey-core@^3.0.0`` dependency
  (``npm validate`` / ``bun validate.mjs`` run the script directly).
* ``deno_build.py`` — self-contained build script (downloads Deno itself).
* ``validate_data.py`` — the Python wrapper that locates and invokes the
  binary at submission time.
* ``validate-linux`` / ``validate-mac`` — the runtime binaries the wrapper
  expects (next to the module).

Runtime auto-build (no manual step)

If the binary is missing or older than five days, the wrapper builds it
automatically: ``deno_build.py`` downloads the current Deno release from
GitHub, compiles ``validate.mjs`` with an import map
(``npm:survey-core@^3.0.0``) and writes ``validate-linux`` (or
``validate-mac``) next to the module. No Deno installation is required on
the Plone host for this path — the script fetches it into a temporary
directory.

Manual build with bun (recommended for packaging)

Bun produces smaller, self-contained binaries and is the default in the
included Makefile:

.. code-block:: shell

    cd src/zopyx/surveyjs/data_validation
    bun install                                   # fetch survey-core
    bun build --compile --target=bun-linux-x64 \
        --outfile dist/survey-validate-linux validate.mjs
    # macOS:
    bun build --compile --target=bun-darwin-x64 \
        --outfile dist/survey-validate-macos validate.mjs

    # or simply: make all   (bun install + both targets)

Manual build with deno

.. code-block:: shell

    cd src/zopyx/surveyjs/data_validation
    deno install
    deno compile --allow-read --allow-write --no-check --node-modules-dir=auto \
        --target=x86_64-unknown-linux-gnu \
        --output dist/survey-validate-linux-deno validate.mjs

    # or simply: make deno  (both macOS and Linux targets)

Cross-compilation

Building a macOS binary from a Linux host (or vice versa) works through the
Docker targets in the Makefile:

.. code-block:: shell

    make docker-linux        # survey-validate-deno:linux image
    make docker-mac-extract  # build macOS binary and copy it out of the image

Deploying the binary

The ``dist/`` directory is for packaging/distribution. At runtime the
wrapper looks for the binary **next to the module**
(``data_validation/validate-linux`` on Linux); copy the freshly built
binary there (or let the auto-build path create it) so server-side
validation is active. The binary is replaced automatically when it is older
than five days or when ``validate.mjs`` changes.

Optional components
===================

Relational result storage
  The SQLModel backend supports SQLite, PostgreSQL, and MySQL. Ensure the
  configured database URI is reachable by the Plone process (default:
  ``sqlite:///var/surveyjs-results.db``). Each row stores the Plone
  ``site_id`` to support multi-site deployments. Configure it under
  Site Setup > Forms → Storage.

AI Generator
  The AI Generator uses the Python ``llm`` package plus the
  ``privacyforms_ai`` helper and supports installed, Ollama and custom
  OpenAI-compatible providers. See :doc:`ai` and :doc:`global-options`.

Development workflow
====================

* ``make test`` — Plone test runner (``bin/test -s zopyx.surveyjs``) plus
  converter tests with coverage.
* ``make docs`` — builds this documentation with Sphinx in an ephemeral
  ``uv`` environment (no persistent venv needed).
* ``make sdist`` — builds the source distribution via
  ``uv run python setup.py sdist``.
