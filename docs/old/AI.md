# AI Generator

This document describes the AI-powered form generator in `zopyx.surveyjs`, how it works, and how to configure it for hosted providers or local models.

## Concept

The AI Generator is a SurveyJS form assistant that turns a natural-language prompt into a SurveyJS JSON form. It is available per Survey at:

- `@@ai` (AI Generator UI)

The workflow is:
1. Author provides a natural-language prompt describing the form.
2. The AI model returns a SurveyJS JSON definition.
3. The UI renders a preview and lets the author refine or save the form.
4. The saved JSON becomes the current form version.

The generator also supports refinement: you can take the current form JSON and ask the AI to make targeted changes without rebuilding from scratch.

## Providers: Hosted vs. Local

The AI integration uses the Python `llm` package. You can use:

- **Hosted providers** (OpenAI, Anthropic, etc.)
  - Configure a model name and an API key.
  - The API key is set for the request based on the model name.
  - Example models: `gpt-4`, `claude-3-sonnet-20240229`.

- **Local providers (Ollama)**
  - Configure an `Ollama URL` (for example `http://localhost:11434`).
  - When set, the generator routes all requests to Ollama and prefixes the model with `ollama/` if needed.
  - Example models: `llama2`, `mistral`, `llama3`.

## Configuration (Site Setup > Forms)

The AI Generator is configured via the global Forms control panel (Site Setup > Forms).

| Setting | Description |
| --- | --- |
| SurveyJS License Key | Optional SurveyJS license key. Required for commercial SurveyJS Creator usage. |
| AI Model | The model name for the LLM (provider-specific). |
| API Key | API key for the chosen provider (ignored when using Ollama). |
| Ollama URL | If set, use a local Ollama server instead of a hosted provider. |
| Prompt before | Text prepended to the user prompt (system context or instructions). |
| Default prompt | Default text shown in the AI Generator prompt field. |
| Prompt after | Text appended to the user prompt (additional constraints). |

Notes:
- If no model is configured, the generator attempts to use the default model configured in `llm` (`llm set-default MODEL_NAME`).
- API keys are only used for hosted providers. When `Ollama URL` is set, Ollama takes precedence.

## How the AI Generator Uses Prompts

The generator builds a structured prompt that instructs the model to return valid SurveyJS JSON only. It also injects rules such as:
- Include hidden `uuid` and `created` fields.
- Use semantic grouping (related fields on the same row).
- Use a dynamic matrix field for tabular data.
- Prefer a one-page form for classic forms, and paginate for surveys.

The `Prompt before` and `Prompt after` settings are applied around the user’s prompt to standardize results across authors.

## Endpoints

The AI UI uses these server endpoints:

- `@@generate-ai-form` to generate a new form JSON from a prompt.
- `@@refine-ai-form` to refine the current form JSON based on a refinement prompt.
- `@@save-ai-form` to persist the generated JSON as a new form version.

## Troubleshooting

- **"LLM module not available"**: install the `llm` package in the Plone environment.
- **"No AI model configured"**: set `AI Model` in Site Setup > Forms or configure a default model using `llm set-default`.
- **Hosted provider errors**: verify API key and model name.
- **Ollama errors**: verify the Ollama server URL and that the model is available locally.
