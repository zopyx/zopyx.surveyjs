============
AI Generator
============

The AI Generator converts a natural-language prompt into a SurveyJS JSON
form. It supports generating new forms and refining existing forms.

Concept
=======

- Authors provide a prompt describing the desired form.
- The AI model returns SurveyJS JSON.
- The UI renders a preview and allows refinement.
- Saving creates a new form version.

Providers
=========

The AI integration uses the Python ``llm`` package and supports:

Hosted providers
  Use a hosted model (OpenAI, Anthropic, etc.) with a model name and API key.

Local models (Ollama)
  Configure an Ollama server URL. When set, requests are routed to Ollama and
  the model name is prefixed with ``ollama/``.

Configuration (Site Setup > Forms)
==================================

.. list-table::
   :header-rows: 1

   * - Setting
     - Description
   * - AI Model
     - Model name (provider-specific).
   * - API Key
     - API key for hosted providers.
   * - Ollama URL
     - Local Ollama server URL (overrides hosted providers).
   * - Prompt before
     - Text prepended to the user prompt.
   * - Default prompt
     - Default text shown to authors.
   * - Prompt after
     - Text appended to the user prompt.

Endpoints
=========

- ``@@generate-ai-form`` generates form JSON from a prompt.
- ``@@refine-ai-form`` refines the current form JSON.
- ``@@save-ai-form`` saves the generated JSON as a new version.

Troubleshooting
===============

- Ensure ``llm`` is installed.
- Configure an AI model or set a default via ``llm set-default``.
- Verify API keys or Ollama availability.
