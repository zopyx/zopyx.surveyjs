=====================
Data Validation (CLI)
=====================

The ``data_validation`` package (``src/zopyx/surveyjs/data_validation/``)
contains a CLI validator that checks SurveyJS submissions with SurveyJS's
own ``survey-core`` validation engine. It is invoked by the server when the
per-survey **Force Server Side Validation** setting is enabled (see
:doc:`validation`), and can also be run manually or used as the basis for
custom integration scripts.

Source layout
=============

* ``validate.mjs`` — the validator itself (ESM script, imports
  ``survey-core``).
* ``package.json`` / ``bun.lock`` — the ``survey-core@3.0.2`` dependency
  (``npm validate`` / ``bun validate.mjs`` run the script directly).
* ``validate_data.py`` — the Python wrapper used by the add-on; locates or
  builds the platform binary and runs it with the given JSON files.
* ``deno_build.py`` — self-contained build script using the pinned Deno
  release and SHA256-verified downloads.
* ``Makefile`` — build targets for bun/deno binaries and Docker
  cross-compilation.

CLI usage
=========

.. code-block:: sh

   bun validate.mjs \
     --schema-json ./survey.json \
     --form-json ./data-valid.json \
     --result-json ./output.json

Options:

* ``--schema-json`` (required) — the SurveyJS form JSON.
* ``--form-json`` (required) — the submission JSON.
* ``--result-json`` (optional, default ``output.json``) — where the result
  is written.
* ``--help`` / ``-h`` — usage help.

Relative input paths are resolved against the current working directory,
the executable directory and the module directory (in that order); the
result path is always resolved against the current working directory.

Output
======

The result file contains a ``valid`` boolean and a list of per-question
errors::

    {
      "valid": false,
      "errors": [
        {
          "name": "q1",
          "title": "Question 1",
          "messages": ["The value is required."]
        }
      ]
    }

The process exits with status ``0`` when the submission is valid and ``1``
when validation fails. Errors (missing files, unknown arguments) are
printed to stderr with exit status ``1``; stdout stays clean so consumers
can rely on the exit code and the result file.

Python wrapper
==============

The add-on does not call the binary directly. ``validate_data.py``:

1. resolves the platform binary (``validate-linux`` / ``validate-mac``
   next to the module) and **builds it automatically** when missing or
   older than five days — it downloads the current Deno release from
   GitHub and compiles ``validate.mjs`` with an import map
   (``npm:survey-core@3.0.2``);
2. runs the binary with ``--schema-json``, ``--form-json`` and
   ``--result-json``;
3. returns the exit code to the caller.

Building binaries
=================

Bun build (recommended, smaller binaries — the default of the Makefile):

.. code-block:: sh

   cd src/zopyx/surveyjs/data_validation
   bun install
   bun build --compile --target=bun-linux-x64 \
       --outfile dist/survey-validate-linux validate.mjs
   # macOS: --target=bun-darwin-x64 --outfile dist/survey-validate-macos
   # or simply: make all

Deno build:

.. code-block:: sh

   cd src/zopyx/surveyjs/data_validation
   deno install
   deno compile --allow-read --allow-write --no-check --node-modules-dir=auto \
       --target=x86_64-unknown-linux-gnu \
       --output dist/survey-validate-linux-deno validate.mjs
   # or simply: make deno

Cross-compilation (e.g. a macOS binary from a Linux host) works via the
Docker targets: ``make docker-linux``, ``make docker-mac-extract``.

Binaries land in ``dist/`` for packaging/distribution. At runtime the
wrapper expects the binary **next to the module** (``validate-linux`` /
``validate-mac``) — copy it there or let the auto-build create it. Full
deployment notes: :doc:`installation` → "External survey validation
(deno / bun)".
