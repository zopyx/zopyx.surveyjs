# zopyx.surveyjs

## Overview

`zopyx.surveyjs` integrates [SurveyJS](https://surveyjs.io) with Plone. It lets you design surveys/forms with the SurveyJS Creator, store submissions in Plone, and distribute or export results in multiple formats.

Key capabilities:
- SurveyJS Creator-backed form designer stored as JSON.
- Submission handling with configurable actions: store in Plone, email exports, or POST to an endpoint.
- Export formats for results (text, Markdown, HTML, PDF, CSV, XLSX, XML, DOCX, JSON).
- Optional validation on submission (experimental Python validator and/or external SurveyJS validator binary).
- Per-form payload size limits.

SurveyJS licensing: the Creator is not free for commercial usage. Refer to the SurveyJS license for details.

## Installation

This package is intended for Buildout-based Plone projects.

1. Add `zopyx.surveyjs` to your buildout eggs and run buildout.

   ```ini
   [buildout]
   eggs +=
       zopyx.surveyjs
   ```

2. Restart Plone and install the add-on in the Add-ons control panel.

3. Optional: server-side SurveyJS validation (external binary)
   - Build the Deno binary in `data-validation/` and place it in `data-validation/dist`.
   - See `data-validation/README.md` for details.

## Usage

1. Create a new Survey content item in Plone.
2. Use the SurveyJS Creator to design the form; the form definition is stored as JSON.
3. Configure actions and settings on the Survey (see configuration section below).
4. Submit the form and access results from the Survey item.
5. Export results using the configured formats or send them via email.

## Survey Configuration (Per-Survey Fields)

All configuration is per Survey item.

### Actions

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| Actions | Set | `store` | Submission handling. Options: `store` (store in Plone), `mail` (send export email), `mail-notification` (notify without attachments), `post` (POST JSON to endpoint). |
| POST endpoint URL | URI | empty | Endpoint to receive the JSON payload when the `post` action is enabled. |

#### Actions in depth

Actions are evaluated for every submission and can be combined.

- `store`: persists the submission (poll data plus metadata such as poll ID, timestamp, form version, and sequence number). Stored results power the results view and export endpoints. When `store` is disabled, submissions return success but are not persisted.
- `mail`: sends a result export email for every submission. Attachments are generated in the formats selected under `Formats`. Requires `E-Mail recipient` and `Subject`, and uses the `Body` template with `{created}`, `{creator}`, and `{formats}`.
- `mail-notification`: sends a notification-only email per submission with a link to the result detail view. Uses `Subject for notifications` and `Body for notifications` templates with `{title}`, `{detail_url}`, `{poll_id}`.
- `post`: performs an HTTP POST to the configured endpoint with a payload containing the poll data, the current form JSON, and the survey URL. Uses a 10-second timeout and logs failures.

### Mail

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| E-Mail sender | Text | empty | Sender address for outgoing mail. Required when `mail` action is enabled. |
| E-Mail recipient | Text | empty | Primary recipient for mail exports/notifications. Required when `mail` action is enabled. |
| Subject | Text | empty | Subject for result export emails. Supports `{poll_id}`. Required when `mail` action is enabled. |
| E-Mail CC | List | empty | CC recipients (one address per line). |
| E-Mail BCC | List | empty | BCC recipients (one address per line). |
| Formats | Set | empty | Export formats to attach to result emails. |
| Body | Text | empty | Body for result export emails. Supports `{created}`, `{creator}`, `{formats}`. |

### Mail Notifications

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| Subject for notifications | Text | `Form submitted ({title})` | Subject for notification-only emails. Supports `{title}`, `{detail_url}`, `{poll_id}`. |
| Body for notifications | Text | `Hello,`<br><br>`A new form submission was received for "{title}".`<br>`You can review the submitted data here:`<br>`{detail_url}`<br><br>`Regards,`<br>`Privacy Forms Studio` | Body for notification-only emails. Supports `{title}`, `{detail_url}`, `{poll_id}`. |

### Form Settings

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| Enable validation (experimental) | Bool | `false` | Server-side validation via the Python validator. May reject complex forms; use with care. |
| Force Server Side Validation | Bool | `false` | Run the external SurveyJS validator binary on every save/submit. Requires a Deno-built binary in `data-validation/dist`. |
| Max size payload (MB) | Int | `1` | Maximum accepted submission payload size in megabytes (minimum 1 MB). |

### Global Settings (Site Setup > Forms)

| Setting | Default | Description |
| --- | --- | --- |
| SurveyJS License Key | empty | Optional license key for SurveyJS components. |
| Log IP addresses | `false` | When enabled, store client IP addresses with submissions. |
| Log user agent | `false` | When enabled, store user agent strings with submissions. |
| AI Model | empty | LLM model name for the AI generator. |
| API Key | empty | API key for hosted LLM providers. |
| Ollama URL | empty | Local Ollama server URL; when set, AI uses Ollama. |
| Prompt before | empty | Text prepended to the AI prompt. |
| Default prompt | empty | Default prompt text shown in the AI UI. |
| Prompt after | empty | Text appended to the AI prompt. |
| Result storage backend | `zodb` | Storage backend for survey results (`zodb` or `rdbms`). |
| Database URI | `sqlite:///var/surveyjs-results.db` | SQLAlchemy database URI for the results database. |

### Storage Backends

Survey results can be stored in the ZODB (default) or in a relational database via SQLModel. Relational rows include the Plone site id (`site.getId()`) and the survey identifier to support multi-site deployments on the same DB.

To migrate existing ZODB results to a relational database, run a Zope/Plone console script and call:

```python
from zopyx.surveyjs.storage_migration import migrate_zodb_results_to_rdbms

migrate_zodb_results_to_rdbms(context)
```

## Views and Endpoints

The Survey type exposes UI views and service endpoints. View names are appended to the Survey URL (for example: `/my-survey/@@viewer`).

### UI Views

| View | Permission | Purpose |
| --- | --- | --- |
| `@@view-main` | `zope2.View` | Landing page with navigation to the main survey tools. |
| `@@viewer` | `zope2.View` | Renders the survey for end users and submits responses. |
| `@@viewer-embed` | `zope2.View` | Embed-friendly viewer for iframes (requires embedding to be enabled on the survey). |
| `@@editor` | `cmf.ModifyPortalContent` | SurveyJS Creator visual editor for building the form. |
| `@@results` | `cmf.ModifyPortalContent` | Results listing with export, mail, and post actions. |
| `@@result-detail` | `cmf.ModifyPortalContent` | Detailed view of a single submission. |
| `@@form-versions` | `cmf.ModifyPortalContent` | Manage saved form versions (preview, restore, download). |
| `@@ai` | `cmf.ModifyPortalContent` | AI form generator UI. |
| `@@pdf-importer` | `cmf.ManagePortal` | PDF form importer UI (beta). |
| `@@forms-settings` | `cmf.ManagePortal` | Site control panel for global form settings. |

### Service Endpoints

| View | Permission | Purpose |
| --- | --- | --- |
| `@@get-form-json` | `zope2.View` | Returns the current form JSON. |
| `@@save-form-json` | `zope2.View` | Saves the form JSON from the editor. |
| `@@save-poll` | `zope2.View` | Submits a response; enforces payload limits and runs validations/actions. |
| `@@get-polls-json` | `zope2.View` | Returns stored submissions with metadata. |
| `@@get-polls-json2` | `zope2.View` | Returns only the stored result payloads. |
| `@@download-form-json` | `zope2.View` | Downloads the current form JSON as an attachment. |
| `@@download-polls-json` | `zope2.View` | Downloads all stored submissions as JSON. |
| `@@download-polls-csv` | `zope2.View` | Downloads all stored submissions as CSV. |
| `@@download-result` | `cmf.ModifyPortalContent` | Downloads a single submission in a selected export format. |
| `@@mail-result` | `cmf.ModifyPortalContent` | Sends export email for a single submission. |
| `@@post-result` | `cmf.ModifyPortalContent` | POSTs a single submission to the configured endpoint. |
| `@@clear-results` | `cmf.ModifyPortalContent` | Clears all stored submissions. |
| `@@view-result-json` | `cmf.ModifyPortalContent` | Returns JSON for a single submission. |
| `@@delete-results` | `cmf.ModifyPortalContent` | Deletes selected submissions. |
| `@@download-version` | `cmf.ModifyPortalContent` | Downloads a specific form version JSON. |
| `@@restore-version` | `cmf.ModifyPortalContent` | Restores a previous form version. |
| `@@toggle-version-lock` | `cmf.ModifyPortalContent` | Locks or unlocks a form version. |
| `@@delete-version` | `cmf.ModifyPortalContent` | Deletes a form version. |
| `@@upload-version` | `cmf.ModifyPortalContent` | Uploads a form version JSON file. |
| `@@view-version-json` | `cmf.ModifyPortalContent` | Returns JSON for a form version. |
| `@@generate-ai-form` | `cmf.ModifyPortalContent` | Generates a form JSON via AI (server endpoint). |
| `@@save-ai-form` | `cmf.ModifyPortalContent` | Saves the AI-generated form JSON. |
| `@@refine-ai-form` | `cmf.ModifyPortalContent` | Refines an existing form via AI (server endpoint). |
| `@@import-pdf-form` | `cmf.ManagePortal` | Imports a form from a PDF (server endpoint). |

## External SurveyJS Validation (Optional)

When `Force Server Side Validation` is enabled, the submission handler invokes the compiled Deno validator from `data-validation/dist`:

- macOS: `data-validation/dist/survey-validate-macos-deno`
- Linux: `data-validation/dist/survey-validate-linux-deno`

See `data-validation/README.md` for build and usage details.

## Author

Andreas Jung | info@zopyx.com | www.zopyx.com

Paid service for `zopyx.surveyjs` is available on request.
