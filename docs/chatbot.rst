=======
Chatbot
=======

The chatbot answers questions about SurveyJS and the survey at hand — how
to build a certain question type, what a setting does, how to fix a
validation error. It is a retrieval-augmented chat: the configured LLM
(see :doc:`ai` and :doc:`global-options`) answers with context retrieved
from a local documentation index, so replies are grounded in the actual
documentation rather than free-form model output.

How it works
============

* **Index**: the ``DocumentationIndexer`` builds a chunked vector index
  (chunks of ~1200 characters with overlap) from two sources:

  * **Local docs** — the project's own documentation (the ``docs/`` sources
    of this add-on).
  * **Remote docs** — the official SurveyJS documentation pages
    (``surveyjs.io``), fetched at index time.

* **Retrieval**: on each question, the chat engine retrieves the ``top_k``
  most relevant chunks (default 6) and builds a prompt that includes the
  current survey context and the retrieved passages.
* **Answer**: the LLM generates the reply from that context; the engine
  also produces a confidence estimate and follow-up suggestions.
* **Streaming**: the API supports ``stream: true`` for token-by-token
  delivery to the UI.

Administration
==============

The chatbot UI (``@@chatbot``, ``cmf.ModifyPortalContent``) offers the
management actions behind the scenes:

* ``@@chatbot-index-local`` — (re)build the index from the project's own
  documentation (run after docs or code changes).
* ``@@chatbot-index-remote`` — fetch the SurveyJS documentation pages and
  index them (requires outbound network access from the Plone host).
* ``@@chatbot-stats`` — usage statistics.
* ``@@chatbot-reset`` — clear the chatbot state/index.
* ``@@chatbot-mgmt`` — management actions (``cmf.ManagePortal``).

These are also exposed as endpoints; see :doc:`endpoints`.

Operational notes
=================

* The chatbot uses the global AI provider configuration (provider, model,
  API key/endpoint) — the provider must be configured before the chatbot
  can answer (see :doc:`ai`).
* The remote index requires the SurveyJS documentation URLs to be
  reachable; behind restrictive firewalls run ``@@chatbot-index-local``
  only, or mirror the remote pages.
* The index is stored per survey; rebuild it after deploying updated
  documentation so answers reflect the current state.
