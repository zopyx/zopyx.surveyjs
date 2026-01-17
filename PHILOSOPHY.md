# Philosophy

`zopyx.surveyjs` is built on a simple premise: privacy first, control always.

## Privacy First

Surveys and forms often contain sensitive data. This module keeps all form definitions and submissions inside your Plone site and under your control. Data is stored in your database, exported only on request, and never shared with third parties by default.

## All on Your Server

You run the stack. You decide where the data lives, how it is backed up, and which integrations are allowed. The module does not require any external SaaS services to function.

Optional integrations (mail delivery, POST to endpoints, AI generation, external validation binaries) are deliberately explicit and configurable. Nothing leaves your server unless you enable it.

## Transparent and Auditable

Everything happens in clear, inspectable code paths:
- Actions are explicit (store, mail, post).
- Validation is configurable and can be enforced server-side.
- Exports are generated on demand.

## Practical Security

Security is treated as an operational concern, not a checkbox. The module includes:
- Payload limits per survey.
- Client-side and optional server-side validation.
- Clear logging for submission flows.

## Open by Design

The goal is not only to provide a rich form builder, but to do so in a way that keeps ownership, compliance, and long-term maintenance with the operator, not the vendor.
