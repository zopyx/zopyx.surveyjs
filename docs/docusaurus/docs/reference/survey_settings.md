---
title: "Survey Settings"
sidebar_position: 19
---

This document describes the Survey/Form settings visible in the Plone add-on UI.
It is based on the available screenshots and covers the following groups:

- Actions
- Mail
- Mail notifications
- Form Settings
- PDF Form
- Embedding

If additional tabs (Default, Settings, Ownership, Dates) contain fields, add them
to this document following the same table structure.

## Actions

These options control what happens when a survey is submitted. Multiple actions
can be enabled at the same time.

| Setting | Possible values | Explanation |
| --- | --- | --- |
| Store | On / Off | Persists each submission in Plone so results can be reviewed later in the CMS. Disable if you want to avoid storing data locally. |
| Mail | On / Off | Sends exported results as email attachments. Requires the Mail tab fields (sender, subject, recipient) to be filled in. |
| Mail (notification only) | On / Off | Sends a notification email without attachments. Uses the templates from the Mail notifications tab. |
| POST to endpoint | On / Off | Forwards the submission payload as JSON to a configured HTTP endpoint. Requires the POST endpoint URL to be set. |
| POST endpoint URL | URL (HTTP/HTTPS) | Target endpoint that receives the JSON payload when POST to endpoint is enabled. Leave empty to disable posting even if the action is selected. |

## Mail

These options define how result export emails are composed and delivered when
the Mail action is enabled.

| Setting | Possible values | Explanation |
| --- | --- | --- |
| E-Mail sender | Email address | Sender address used for outgoing result emails. Mandatory when the Mail action is selected. |
| Subject | Text with optional placeholder | Subject line for result export emails. Supports `{poll_id}` to include the submission ID. Mandatory when the Mail action is selected. |
| E-Mail recipient | Single email address | Primary recipient for result exports and notifications. Mandatory when the Mail action is selected. |
| E-Mail CC | One email per line | Optional CC recipients for result export emails. Each line represents one address. |
| E-Mail BCC | One email per line | Optional BCC recipients for result export emails. Each line represents one address. |

## Mail notifications

These options define the notification-only email content used when the
Mail (notification only) action is enabled.

| Setting | Possible values | Explanation |
| --- | --- | --- |
| Subject for notifications | Text with optional placeholders | Subject line for notification-only emails. Supports `{title}`, `{detail_url}`, and `{poll_id}` placeholders. |
| Body for notifications | Text with optional placeholders | Email body for notification-only messages. Supports `{title}`, `{detail_url}`, and `{poll_id}` placeholders. |

## Form Settings

These options control validation, payload size, and access mode.

| Setting | Possible values | Explanation |
| --- | --- | --- |
| Force Server Side Validation | On / Off | Runs the external SurveyJS validator binary on every save or submit to ensure server-side validation. |
| Max size payload (MB) | Positive integer | Maximum allowed size of the submission payload in megabytes. Submissions exceeding this limit are rejected. |
| Access mode | Public / Trusted access token | Controls whether the form is publicly accessible or requires a trusted access token in the URL. |
| Trusted access token TTL (hours) | Positive integer (hours) | Lifetime of trusted access tokens in hours. Applies when Access mode is set to require a trusted access token. |

## PDF Form

These options enable a PDF-based form workflow.

| Setting | Possible values | Explanation |
| --- | --- | --- |
| Fillable PDF form | Upload a PDF file / None | Optional upload. Providing a fillable PDF enables the PDF-based workflow for this survey. Leaving it empty keeps the standard web form workflow. |

## Embedding

These options control whether the form can be embedded elsewhere.

| Setting | Possible values | Explanation |
| --- | --- | --- |
| Embedding mode | None / Iframe | Controls whether this survey may be embedded. Select Iframe to allow embedding; choose None to disallow it. |
