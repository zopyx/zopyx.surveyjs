============
AI Generator
============

The AI Generator converts natural language into a SurveyJS form definition.
It is the part of the add-on where an LLM does the actual form-building
work: an author describes what they need, and the generator produces a
complete SurveyJS JSON schema that can be previewed, refined and finally
activated as the survey's form.

The generator supports three entry points:

* **Prompt-based creation** — "a customer satisfaction survey with 10
  questions, first name and e-mail at the end".
* **Refinement** — "change the rating questions from 1–5 to 1–10 and make
  the e-mail field required".
* **Document conversion** — upload a PDF (including fillable PDFs), DOCX,
  ODT or HTML file and let the AI rebuild it as an online form.

The AI configuration (provider, model, prompts) is global — see
:doc:`global-options`. The machine-readable endpoints are documented in
:doc:`endpoints`.

How it works
============

LLM stack and providers
-----------------------

Generation and refinement run on the Python ``llm`` package, wrapped by the
``privacyforms_ai`` helper library. The provider is selected globally and
the three modes are **mutually exclusive**:

* ``installed`` — a model from the ``llm`` plugin registry (e.g. a
  ``gpt-*``/OpenAI or ``claude-*``/Anthropic model). An API key is optional;
  when present it is exported as ``OPENAI_API_KEY`` or
  ``ANTHROPIC_API_KEY`` depending on the model name.
* ``ollama`` — a local Ollama server. Only the URL is required; the model
  defaults to ``llama3.2`` when not set. The server URL is exported as
  ``OLLAMA_HOST`` and the effective model name is prefixed with ``ollama/``.
  No API key is involved — the model runs on your own machine.
* ``custom`` — any OpenAI-compatible endpoint (e.g. DeepSeek, a self-hosted
  vLLM/TGI server). Requires **all three** of model name, API base URL and
  API key. The model is built via ``AI.get_custom_model()`` with
  ``api_base`` set to your URL.

The resolver is ``build_llm_model()`` in ``browser/services/ai.py``; a
settings dict from ``load_ai_settings()`` is turned into a concrete
``llm`` model instance. On legacy installs without an explicit provider
selection, the provider is derived from the populated fields (Ollama URL
wins, then custom URL, otherwise installed).

Prompt pipeline
---------------

The generator does not send the raw user input to the model. It builds a
structured prompt:

1. A **system-style instruction** positions the model as a SurveyJS expert
   and demands a *pure* SurveyJS JSON object: no markdown, no code fences,
   no explanations, no trailing commas. This keeps the output parseable.
2. **Quality rules** are injected: current SurveyJS v2+ schema conventions,
   clear structure (``title``, ``description``, ``pages``, ``elements``),
   suitable field types, readable names, validation where the prompt makes
   requirements obvious, and "ready to edit in SurveyJS Creator".
3. The global **Prompt before / Prompt after** settings wrap the author's
   text, so site-wide conventions (tone, mandatory sections, output
   constraints) apply to every generation.
4. For **refinement**, the current form JSON is embedded into the prompt
   and the model is asked to return the *full updated* JSON — not a diff.
5. The response is parsed tolerantly: ``extract_json_text()`` pulls the
   JSON object out of the model's reply (handles code fences and prose)
   before it is validated with ``json.loads``.

The temporary form workspace
----------------------------

AI work happens in a **temporary workspace** per survey, stored in
annotations — deliberately separate from the version history. This is the
key architectural detail:

* The working draft lives under ``zopyx.surveyjs.ai.temp_form_json``.
* Every refinement appends the *previous* draft plus the prompt that
  produced the change to a history list
  (``zopyx.surveyjs.ai.temp_form_history``), capped at the **last 5 steps**.
  This gives a bounded undo stack.
* The draft only becomes "real" when explicitly promoted (see workflow).
  Until then, the published survey form is completely untouched.
* Clearing the workspace discards the draft and its history — there is no
  garbage collection or recovery.

Typical workflow
================

1. Open ``@@ai`` on the survey.
2. **Start**: either copy the latest form version into the workspace
   (``@@ai-copy-latest-to-temp`` — the recommended base for refinements),
   upload a document (``@@ai-upload``), or just type a prompt.
3. **Create or refine**: submit a prompt (``@@ai-chat-refine``). With an
   empty workspace this generates a draft from scratch; with an existing
   draft it returns the full updated JSON.
4. **Iterate**: refine again, preview the draft, and use the history
   controls (``@@ai-restore-history-step`` / ``@@ai-delete-history-step``)
   to undo individual steps.
5. **Promote**: ``@@ai-store-temp-version`` saves the draft as a new form
   version — it becomes the active form. The workspace is cleared.

Document conversion
===================

``@@ai-upload`` accepts PDF, DOCX, ODT and HTML files (extension or MIME
type based). For PDFs the converter first tries to **extract fillable-PDF
field metadata** (ids, types, labels); this metadata is handed to the model
together with the document content, and a field mapping between the PDF and
the generated survey is stored on the survey. The conversion prompt adds
**layout fidelity** requirements: preserve grouping, section order and
row/column structure (via ``panel``, ``paneldynamic``, ``multipletext`` or
matrix elements) so the online form feels like the original document. When
the draft is generated from a plain prompt or a non-PDF file, any stale PDF
field mapping is cleared.

Configuration & operational notes
=================================

* The global AI settings live in **Site Setup > Forms → AI**; see
  :doc:`global-options` for the full field reference.
* **"Configured" means**: installed → a model name is set; ollama → the URL
  is set (model optional, defaults to ``llama3.2``); custom → model name,
  URL *and* API key are all set. The control panel enforces mutual
  exclusivity by clearing the fields of inactive provider groups on save.
* **API keys are write-only**: the control panel uses a keep-mask
  convention — an empty submitted key never overwrites the stored one.
* **Model choice matters**: larger models generally produce structurally
  better forms but are slower and more expensive. Start with the
  provider's default, then switch when the output quality is insufficient.
* **Prompt scaffolding pays off**: a good "Prompt before" (global rules,
  tone, mandatory sections) standardizes output across all authors; keep it
  short to avoid conflicts with the user's own instructions.
* The **AI connection test** buttons in the forms-settings AI panels call
  ``@@ai-test`` and report provider/model/endpoint reachability before you
  rely on generation.
* The workspace is **per survey** and not shared; promote or export drafts
  you want to keep, because ``@@ai-clear-temp-storage`` removes them
  permanently.

Endpoints
=========

All endpoints require ``cmf.ModifyPortalContent`` and operate on the survey
(see :doc:`endpoints` for parameters and responses):

* ``@@ai-chat-refine`` — create or refine the temp form from a prompt.
* ``@@ai-upload`` — convert an uploaded document into a draft.
* ``@@ai-copy-latest-to-temp`` — copy the active form into the workspace.
* ``@@ai-store-temp-version`` — promote the draft to a form version.
* ``@@ai-restore-history-step`` / ``@@ai-delete-history-step`` — undo
  management.
* ``@@ai-clear-temp-storage`` — discard the workspace.
* ``@@ai-test`` — provider connectivity test (site root, Manager).

Troubleshooting
===============

* **"AI model not configured"** — the active provider is incomplete:
  installed needs a model name, ollama needs a URL, custom needs all three
  fields. Check Site Setup > Forms → AI.
* **"privacyforms_ai package not found"** — the helper package is missing
  from the Plone environment; install it (it is a regular dependency of the
  add-on).
* **Ollama errors** — verify the server URL is reachable from the Plone
  host and that the model is pulled locally (``ollama list``).
* **Custom endpoint errors** — check that the base URL is the
  OpenAI-compatible API root (not a chat path), that the key is valid, and
  that the endpoint is reachable (the ``@@ai-test`` button reports this).
* **Invalid JSON from the model** — retry; if it persists, the model may be
  too weak for complex requirements. Switch to a larger model or split the
  request into smaller steps.
