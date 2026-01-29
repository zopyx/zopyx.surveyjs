---
title: "Actions"
sidebar_position: 6
---

Actions define what happens when a survey submission is received.
Multiple actions can be enabled at the same time.

## Action types

store  
Persist the submission in the Survey results store. Stored submissions
appear in `@@results` and are available for exports and detail views.

mail  
Generate exports in the configured formats and send them as attachments.
Requires `E-Mail recipient` and `Subject`. If no formats are selected,
the system defaults to PDF.

mail-notification  
Send a notification-only email that links to the submission detail view.
Uses the notification subject/body templates.

post  
POST the submission to the configured endpoint. The payload contains the
submission data, the current form JSON, and the survey URL. This action
is only executed when an endpoint URL is configured.

## Execution flow

1.  `@@save-poll` receives and validates a submission.
2.  A submission event is emitted with the payload and metadata.
3.  Subscribers execute enabled actions (store, mail, mail-notification,
    post).
4.  The response is returned to the caller.

## Notes

- If `store` is disabled, submissions still return success but are not
  persisted.
- `mail` and `mail-notification` are independent and can be combined.
- `post` does not block storage or mail; it executes in addition to
  those actions when enabled.
