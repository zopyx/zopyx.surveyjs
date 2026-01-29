---
title: "Views"
sidebar_position: 7
---

Survey views are accessed by appending the view name to the Survey URL
(e.g. `/my-survey/@@viewer`).

## UI views

| View | Permission | Purpose |
|----|----|----|
| `@@view-main` | `zope2.View` | Landing page with navigation to survey tools. |
| `@@viewer` | `zope2.View` | Public survey rendering and submission. |
| `@@viewer-embed` | `zope2.View` | Embed-friendly viewer for iframes (requires embedding allowed). |
| `@@editor` | `cmf.ModifyPortalContent` | SurveyJS Creator visual editor. |
| `@@results` | `cmf.ModifyPortalContent` | Results listing and export controls. |
| `@@result-detail` | `cmf.ModifyPortalContent` | Detailed view of a single submission. |
| `@@form-versions` | `cmf.ModifyPortalContent` | Manage form versions (preview, restore, download). |
| `@@ai` | `cmf.ModifyPortalContent` | AI Generator UI. |
| `@@pdf-importer` | `cmf.ManagePortal` | PDF form importer (beta). |
| `@@forms-settings` | `cmf.ManagePortal` | Global Forms control panel. |

## Service endpoints

| View | Permission | Purpose |
|----|----|----|
| `@@get-form-json` | `zope2.View` | Return the current form JSON. |
| `@@save-form-json` | `zope2.View` | Save form JSON from the editor. |
| `@@save-poll` | `zope2.View` | Submit a survey response. |
| `@@get-polls-json` | `zope2.View` | Return stored submissions with metadata. |
| `@@get-polls-json2` | `zope2.View` | Return only submission payloads. |
| `@@download-form-json` | `zope2.View` | Download current form JSON as an attachment. |
| `@@download-polls-json` | `zope2.View` | Download all stored submissions as JSON. |
| `@@download-polls-csv` | `zope2.View` | Download all stored submissions as CSV. |
| `@@download-result` | `cmf.ModifyPortalContent` | Download a single submission in a selected format. |
| `@@mail-result` | `cmf.ModifyPortalContent` | Send export email for a single submission. |
| `@@post-result` | `cmf.ModifyPortalContent` | POST a single submission to the configured endpoint. |
| `@@clear-results` | `cmf.ModifyPortalContent` | Clear all stored submissions. |
| `@@view-result-json` | `cmf.ModifyPortalContent` | Return JSON for a single submission. |
| `@@delete-results` | `cmf.ModifyPortalContent` | Delete selected submissions. |
| `@@download-version` | `cmf.ModifyPortalContent` | Download a specific form version. |
| `@@restore-version` | `cmf.ModifyPortalContent` | Restore a previous form version. |
| `@@toggle-version-lock` | `cmf.ModifyPortalContent` | Lock or unlock a form version. |
| `@@delete-version` | `cmf.ModifyPortalContent` | Delete a form version. |
| `@@upload-version` | `cmf.ModifyPortalContent` | Upload a form version JSON file. |
| `@@view-version-json` | `cmf.ModifyPortalContent` | Return JSON for a form version. |
| `@@generate-ai-form` | `cmf.ModifyPortalContent` | Generate a form JSON via AI. |
| `@@save-ai-form` | `cmf.ModifyPortalContent` | Save the AI-generated form JSON. |
| `@@refine-ai-form` | `cmf.ModifyPortalContent` | Refine a form JSON via AI. |
| `@@import-pdf-form` | `cmf.ManagePortal` | Import a form from a PDF. |
