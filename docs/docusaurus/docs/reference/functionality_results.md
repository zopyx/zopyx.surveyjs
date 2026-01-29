---
title: "Functionality Results"
sidebar_position: 16
---

This document explains the **Results** view (`@@results`) from both the user interface perspective and the background processing performed on the server. It reflects the current implementation in the codebase.

## Purpose

The Results view provides a complete overview of stored survey submissions (poll results). It lets authorized users:

- Search, filter, sort, and paginate results.
- Preview individual submissions in JSON or table form.
- Download results in JSON/CSV and download the form definition.
- Delete individual or multiple results (Managers only).
- Clear all stored results with a safety confirmation.

## UI Structure

The Results view is rendered by:

- Template: `src/zopyx/surveyjs/browser/results.pt`
- Script: `src/zopyx/surveyjs/browser/static/results.js`
- Styles: `src/zopyx/surveyjs/browser/static/results.css`

### Header

The header displays:

- **Title:** “Stored form data”
- **Storage info:** Which backend storage is used (e.g., ZODB, external storage)

A small **DOCS badge** links to the official documentation:

- https://docs.privacyforms.studio/functionality_results.html

### Storage Disabled Banner

If the survey’s action configuration does **not** include `store`, the UI shows a warning banner explaining that results are not being persisted and therefore cannot be displayed.

### Toolbar

The toolbar supports:

- **Search box** (user, UUID, poll ID, created date)
- **Search button**
- **Reset button**
- **Refresh button**
- **Delete selected** (Managers only)
- **Clear all results**

### Results Grid

The results table is powered by **Tabulator** and supports:

- Remote pagination
- Remote sorting
- Remote filtering
- Row selection (Managers only)

Columns include:

- Date
- User
- Sequence number
- Poll ID
- Action buttons

### Action Buttons per Row

Each row provides:

- **JSON**: Open the raw JSON submission in a modal.
- **Table**: Open a formatted details view of the submission.
- **Details**: Navigate to the full HTML detail page (`@@result-detail`).
- **Download**: Export the submission using selectable formats (e.g., JSON, CSV, PDF depending on converters).
- **Mail** (optional): Mail a submission if mail action is configured.
- **POST** (optional): POST the submission if a POST endpoint is configured.
- **Delete** (Managers only): Delete the individual result.

### Footer Downloads

At the bottom of the view, users can:

- **Download results (JSON)** — all results
- **Download results (CSV)** — all results
- **Download form definition (JSON)** — latest form version

### Modals

The view includes several modal dialogs:

- **JSON viewer** (`view-result-json`)
- **Details viewer** (table view derived from JSON)
- **Delete confirmation** (single)
- **Delete selected confirmation** (batch)
- **Clear all confirmation** (requires typing `clear`)

## Backend Workflow

The Results UI depends on a set of backend endpoints and services in:

- `src/zopyx/surveyjs/browser/views.py`
- `src/zopyx/surveyjs/browser/services/results.py`

### 1) Results Storage

Submissions are stored when the survey action `store` is enabled. Each submission includes:

- `poll_id`
- `created` timestamp
- `user`
- `form_version`
- `result` JSON payload

If storage is disabled, the UI does not show data.

### 2) Results Listing (Remote Table)

The results table loads data from:

- `@@results-data`

This endpoint delegates to:

- `build_results_payload()` in `services/results.py`

The payload includes:

- `data` (page slice)
- `page`
- `last_page`
- `total_rows`

The service supports:

- Pagination (`page`, `size`)
- Sorting (Tabulator `sorters` param)
- Filtering (Tabulator `filters` param)
- Free-text search (`q` parameter)

### 3) Viewing Result JSON

The **JSON** action loads data from:

- `view-result-json?poll_id=...`

The response is the raw stored `result` payload for that submission.

### 4) Details Table View

The **Table** action also loads from `view-result-json`, then renders a structured HTML table client-side using:

- The stored JSON payload
- Field labels inferred from the current form JSON (`get-form-json`)

Matrix and dynamic-matrix answers are rendered as tables for readability.

### 5) Full Detail View

The **Details** action navigates to:

- `@@result-detail?poll_id=...`

The backend builds a rich HTML representation using the latest form definition and converters.

### 6) Downloading Results

Downloads use dedicated endpoints:

- `download-polls-json` — full results export as JSON
- `download-polls-csv` — full results export as CSV
- `download-result` — single result in chosen format
- `download-form-json` — latest form definition

### 7) Deleting Results (Managers only)

Deletion is restricted to users with the **Manager** role.

Endpoints:

- `delete-results` — accepts JSON payload `{ poll_ids: [...] }`

Deletion supports:

- Single-row delete
- Multi-row delete

### 8) Clearing All Results

The **Clear all results** action triggers:

- `clear-results`

This removes all stored submissions. The UI requires typing `clear` to confirm.

### 9) Security and CSRF

- Manager-only actions use a CSRF token (`X-CSRF-TOKEN`).
- The token is embedded in `RESULTS_CONFIG` and attached to delete/clear requests.

## Summary

The Results view provides a comprehensive interface for inspecting stored submissions, with robust filtering and export tools, and tightly controlled destructive actions. The front-end is a Tabulator-driven grid with multiple preview modalities, while the backend exposes structured endpoints for pagination, downloads, and deletion.
