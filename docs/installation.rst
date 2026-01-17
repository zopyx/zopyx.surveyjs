============
Installation
============

This package is intended for Buildout-based Plone projects.

Buildout
========

1. Add ``zopyx.surveyjs`` to your buildout eggs and rerun buildout.

   .. code-block:: ini

      [buildout]
      eggs +=
          zopyx.surveyjs

2. Restart Plone and install the add-on in the Add-ons control panel.

Optional components
===================

SQLite result storage
  The SQLite backend is bundled via SQLModel. Ensure the configured SQLite
  path is writable by the Plone process (default: ``var/surveyjs-results.db``).
  Each row stores the Plone ``site_id`` to support multiple sites sharing
  a single SQLite file.

External SurveyJS validation (Deno binary)
  Build the Deno validator in ``data-validation/`` and place the binary in
  ``data-validation/dist``. See ``data-validation/README.md`` for details.

AI Generator
  The AI Generator uses the Python ``llm`` package and optionally an API key
  or a local Ollama server. See :doc:`ai` for configuration.
