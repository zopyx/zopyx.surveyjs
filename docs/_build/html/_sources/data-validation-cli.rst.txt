=====================
Data Validation (CLI)
=====================

The ``data-validation`` folder contains a CLI tool that validates SurveyJS
submissions using SurveyJS' own ``survey-core`` validator. The tool is used by
the server when ``Force Server Side Validation`` is enabled.

CLI usage
=========

.. code-block:: sh

   bun validate.mjs \
     --schema-json ./survey.json \
     --form-json ./data-valid.json \
     --result-json ./output.json

Required options:

- ``--schema-json``: SurveyJS form JSON
- ``--form-json``: Submission JSON

Optional:

- ``--result-json``: Output file (defaults to ``output.json``)

Output
======

The output JSON contains a ``valid`` boolean and a list of per-question errors.
The process exits with status ``0`` on success and ``1`` on validation failure.

Building binaries
=================

Deno binaries are built with:

.. code-block:: sh

   make deno-mac
   make deno-linux

Binaries are placed in ``data-validation/dist``. See ``data-validation/README.md``
for full build instructions.
