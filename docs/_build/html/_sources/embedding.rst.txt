=========
Embedding
=========

Surveys can be embedded into external sites using the embed view and the
public embed JavaScript API.

Quick start
===========

1. Enable embedding on the Survey (Allow Embedding).
2. Include the embed script on the external site.
3. Add a container with the survey URL.

.. code-block:: html

   <script src="https://your-plone-site.com/++resource++zopyx.surveyjs/embed.js"></script>

   <div class="surveyjs-embed"
        data-survey-url="https://your-plone-site.com/surveys/customer-satisfaction">
   </div>

Configuration
=============

Declarative options are provided via ``data-*`` attributes:

- ``data-survey-url`` (required)
- ``data-height`` (default ``600px``)
- ``data-width`` (default ``100%``)
- ``data-auto-resize`` (default ``false``)

Security
========

Embedding is opt-in. When embedding is enabled:

- The ``X-Frame-Options`` header is removed for the embed view.
- ``Content-Security-Policy: frame-ancestors *`` is set.
- CORS headers are added to allow cross-origin access.

The embed view is ``@@viewer-embed`` and is designed for use within iframes.

Further details
===============

See ``EMBEDDING.md`` and the example page at
``++resource++zopyx.surveyjs/embed-example.html`` for full examples.
