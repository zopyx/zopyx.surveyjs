Chatbot
=======

The chatbot (``@@chatbot``) answers questions about the add-on and
SurveyJS: how to configure a setting, which view to use, how validation
works. It is a retrieval-augmented chat — the answers are grounded in the
project's own documentation plus the official SurveyJS documentation,
retrieved and summarized by the configured LLM. Instead of guessing, ask
the bot.

.. image:: _static/screenshots/survey-action-chatbot.png
   :align: center
   :alt: Chatbot

How to get here
---------------

* From the survey landing page, click **Chatbot** (marked **Beta**).
* Directly at ``/my-survey/@@chatbot``.
* The chatbot feature must be enabled globally (default: on) and the AI
  provider must be configured (the chatbot uses the same provider as the
  AI generator).

What you see
------------

**Survey header** — the shared navigation with the headline "Chatbot —
Ask about zopyx.surveyjs usage, configuration, and SurveyJS
documentation."

**Quick Prompts** (sidebar)

  One-click questions that show what the chatbot knows about:

  * How do I configure actions store, mail and post?
  * Which global settings are available under Site Setup > Forms?
  * How do I enable server-side validation for submissions?
  * Which view should I use for editor, viewer, results, and versions?

**Chat area** (main column)

  * **Messages** — the running conversation (your questions and the
    answers).
  * **Sources** — which documentation passages the answer was retrieved
    from; a transparency feature that lets you verify the grounding.
  * **Follow-ups** — suggested follow-up questions generated from the
    answer.
  * **Input** — a textarea for your question, a **Stream response**
    checkbox (answers arrive token by token; switch it off for a single
    complete answer), the **Send** button and a **Clear** button that
    resets the conversation.

What you can do
---------------

Ask a question
~~~~~~~~~~~~~~

1. Type your question (or click a Quick Prompt).
2. Click **Send** (or press Enter in the textarea).
3. Read the answer — and the **sources** it is based on.
4. Continue the conversation with follow-up questions or a new prompt;
   **Clear** starts a fresh conversation.

What to ask about
~~~~~~~~~~~~~~~~~

* SurveyJS question types and form design ("How do I build a matrix
  question?")
* The add-on's settings and views ("What does the access mode do?",
  "Where are the global settings?")
* Validation and troubleshooting ("Why was my submission rejected?")

Tips & notes
------------

* **Answers are grounded in the documentation index** — the local docs
  plus the SurveyJS documentation pages. If the index is stale (e.g.
  after a software update), a manager can rebuild it
  (``@@chatbot-index-local`` / ``@@chatbot-index-remote``, see
  :doc:`chatbot`).
* The remote documentation must be reachable from the Plone host when the
  remote index is built; behind restrictive firewalls only the local
  index may be available.
* The chatbot needs the AI provider configured — otherwise it cannot
  answer (see :doc:`global-options`).
* Treat answers as documentation summaries; for authoritative details on
  settings and endpoints, follow the links in this documentation.

Related documentation
---------------------

* :doc:`chatbot` — how the index and retrieval work, and the management
  actions.
* :doc:`ai` — the shared LLM stack and provider configuration.
* :doc:`views` — the view reference the chatbot is trained on.
