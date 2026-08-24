Development setup
=================

The project uses an ``uv``-managed virtual environment on top of the
classic Buildout workflow. The site root of the development instance is
http://localhost:8082/demo.

Setup
-----

Create the virtual environment in the repository root and install the
pinned toolchain (``zc.buildout`` 5.2, setuptools, …)::

    $ uv venv --clear
    $ uv pip install -r requirements.txt

Run buildout — this generates ``bin/instance``, ``bin/test``,
``bin/zopepy`` and the other scripts::

    $ ./bin/buildout

Start Plone::

    $ ./bin/instance fg            # foreground
    # or: $ ./bin/instance start   # background
    # or: $ ./bin/instance stop

Login
-----

* Site root: http://localhost:8082/demo
* Login page: http://localhost:8082/demo/login
* Demo user: ``forms`` / ``formsarecool`` (Plone ``Editor`` role — enough
  for survey editing; the Forms control panel needs ``Manager``).
* Admin credentials are defined in the buildout configuration
  (``base.cfg``: ``admin2``).

Running tests
-------------

Run the full test suite (Plone test runner plus converter tests with
coverage) via the Makefile::

    $ make test

This executes ``bin/test -s zopyx.surveyjs`` and the converter unit tests
under ``bin/zopepy -m coverage``. Alternatively, run just the Plone tests::

    $ bin/test -s zopyx.surveyjs

Building the documentation
--------------------------

The Sphinx documentation under ``docs/`` builds in an ephemeral ``uv``
environment (no persistent venv needed)::

    $ make docs

Data validation binary
----------------------

The optional server-side validation uses a compiled binary built from
``src/zopyx/surveyjs/data_validation/validate.mjs`` (bun or deno). The
runtime wrapper builds it automatically when missing; manual build steps and
cross-compilation are documented in ``docs/installation.rst`` → "External
survey validation (deno / bun)".
