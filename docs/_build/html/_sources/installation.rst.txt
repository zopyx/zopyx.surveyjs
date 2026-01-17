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

External SurveyJS validation (Deno binary)
  Build the Deno validator in ``data-validation/`` and place the binary in
  ``data-validation/dist``. See ``data-validation/README.md`` for details.

AI Generator
  The AI Generator uses the Python ``llm`` package and optionally an API key
  or a local Ollama server. See :doc:`ai` for configuration.
