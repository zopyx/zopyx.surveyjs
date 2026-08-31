# Audit trail logging and governance

Privacy Forms Studio records selected administrative and form-version changes
through `zopyx.plone.persistentlogger`. The audit trail covers form-version
changes, Control Panel changes, metadata updates, and selected embed-security
events.

## Failure handling

Audit logging is deliberately **fail-open**: a failure of the persistent
logging backend must not make an already accepted request fail.

The application wrapper reports the outcome of each write:

- `True` means that the audit entry was written successfully.
- `False` means that the backend could not write the entry.

A failed write means that the corresponding audit event is missing; it is not
considered a successful audit operation. The failure is emitted through the
`zopyx.surveyjs.audit` logger with the audit action and object path. The audit
payload itself is not included in the error message.

Example log message:

```text
Persistent audit logging failed: action=metadata.update path=/example/survey
```

Operators should monitor this logger and investigate repeated failures. Where
strict audit delivery is required, the operational response must include a
retry or backend-recovery procedure; application requests are not blocked by
this wrapper.

## Governance notes

Audit entries are stored persistently on the affected Plone object by the
persistent logger. They should be treated as an operational audit trail, not
as a replacement for a separately governed, immutable compliance archive.
Define and document retention, access control, backup, and export procedures
for the deployment's applicable governance requirements.

The existing persistent logger object-modification behavior is unchanged.
This document describes the failure handling and observability provided by the
application wrapper only.
