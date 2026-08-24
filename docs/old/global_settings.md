# Global Survey Settings

This document describes the global "Forms Settings" for the Plone SurveyJS
add-on. It is based on the available screenshots and covers all tabs shown in
that UI. Defaults reflect the values visible in the screenshots; adjust them if
your installation ships different defaults.

## SurveyJS

These settings control licensing for the SurveyJS components.

| Setting | Possible values | Default value | Explanation |
| --- | --- | --- | --- |
| SurveyJS License Key | SurveyJS license string (text) / empty | Empty (unless configured) | Optional license key used to unlock commercial SurveyJS components. Leave empty to run in evaluation or open-source mode. Store the key exactly as provided by SurveyJS; whitespace or line breaks will invalidate it. |

## AI Provider

These settings select which LLM provider is used for AI-assisted form
generation and how it is authenticated.

| Setting | Possible values | Default value | Explanation |
| --- | --- | --- | --- |
| AI Model | Model identifier string | `gpt-5-nano` | Name of the model passed to the LLM provider when generating forms. Use provider-specific identifiers (e.g., `gpt-4`, `claude-3-sonnet-20240229`). Selecting a larger model typically improves output quality but may increase latency and cost. |
| API Key | Provider API key (secret text) / empty | Empty | Secret key used to authenticate with the selected LLM provider. Stored securely by the add-on. If empty, AI generation will fail unless the provider is configured via environment variables or another external mechanism. |
| Ollama URL | URL (HTTP/HTTPS) / empty | Empty | Optional base URL of an Ollama server (for example, `http://localhost:11434`). When set, the AI generator uses Ollama instead of the default cloud provider. Leave empty to keep the default provider behavior. |

## AI Prompts

These settings define the prompt scaffolding used around the user's input when
building a form. All fields are optional and can be used independently.

| Setting | Possible values | Default value | Explanation |
| --- | --- | --- | --- |
| Prompt before | Multi-line text / empty | Empty | Instructions inserted before the user's prompt. Use this to enforce global rules, tone, or formatting requirements for generated forms. Keeping it short reduces the risk of prompt conflicts. |
| Default prompt | Multi-line text / empty | Empty | Prefilled text shown to the user as a starting prompt. This does not automatically prepend or append to the user's final prompt; it only provides default input text. |
| Prompt after | Multi-line text / empty | Empty | Instructions appended after the user's prompt. Use this to add constraints or mandatory output structure while still letting users supply their own content. |

## Logging

These settings control what additional client metadata is stored alongside form
submissions.

| Setting | Possible values | Default value | Explanation |
| --- | --- | --- | --- |
| Log IP addresses | On / Off | Off | When enabled, the client IP address is stored as part of the submission. This can help with abuse detection and audit trails but may introduce privacy and compliance requirements. |
| Log user agent | On / Off | Off | When enabled, the browser user-agent string is stored with the submission. Useful for diagnostics and statistics; consider privacy implications before enabling. |

## Result Storage

These settings control where survey submissions are stored.

| Setting | Possible values | Default value | Explanation |
| --- | --- | --- | --- |
| Result storage backend | `Plone (ZODB)` / other installed backends | `Plone (ZODB)` | Selects the storage backend for survey results. The default stores results in Plone's ZODB. Additional backends may be available depending on installed add-ons. |
| Database URI | SQLAlchemy database URI / empty | `sqlite:///var/surveyjs-results.db` | Database connection string used by SQL-based storage backends. Examples include `sqlite:///var/surveyjs-results.db` or `postgresql+psycopg2://user:pass@host/db`. Ignored when the ZODB backend is selected. |

## Security

These settings secure form submissions with short-lived authenticity tokens.

| Setting | Possible values | Default value | Explanation |
| --- | --- | --- | --- |
| Enable authenticity token | On / Off | On | Requires a short-lived authenticity token for each submission. Enable this to protect against unauthenticated or replayed submissions. When disabled, submissions can be posted without a token. |
| Authenticity token secret | Secret text (HMAC key) | Configured secret | HMAC secret used to sign authenticity tokens. Keep this private and rotate it only with careful coordination, as rotating the secret invalidates existing tokens. |
| Authenticity token TTL (seconds) | Positive integer (seconds) | `3600` | Lifetime of authenticity tokens in seconds. Shorter TTLs reduce replay risk but require clients to refresh tokens more often. |
| Authenticity token issuer | Text identifier | `zopyx.surveyjs` | Issuer claim embedded in tokens. Use a stable, unique identifier for your site or add-on instance. |
| Authenticity token audience | Text identifier | `zopyx.surveyjs` | Audience claim embedded in tokens. Match this to the expected token consumer; using a distinct value helps prevent token reuse across environments. |
| Authenticity token cache path | Filesystem path | `var/token_cache.db` | Path to the disk-backed cache used to store token metadata. Ensure the path is writable by the Plone process and protected from public access. |
