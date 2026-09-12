Known limitations and roadmap
=============================

This page lists what the add-on does **not** implement and how a deployment
is expected to compensate. Everything here is a known gap of the 1.0 beta,
not an oversight of the documentation: where a feature is missing, the
feature documentation points to this page.

Rate limiting
-------------

**Status: monitoring only, no enforcement.**

* ``monitoring.check_rate_limit()`` computes per-minute and 5-minute rolling
  averages from the KV counters, but the function is only called by the
  monitor dashboard (``@@survey-monitor``) for display purposes.
* Nothing in the submission path (``save_poll``) rejects a request based on
  submission rate; there is no HTTP 429 response anywhere in the package.
* Counting happens in a subscriber *after* a submission has been accepted,
  so the counters measure accepted traffic, not attempts. Rejected floods
  are invisible to them.
* The check is fail-open by design, the counter update is not atomic
  (get/set instead of an atomic increment), ``max_per_minute`` is a
  hardcoded default and per-form limits are not exposed.

**Deployment guidance:** enforce rate limiting at the reverse proxy or WAF in
front of Plone (see :doc:`security` and ``SECURITY.md``).

**Roadmap:** configurable global and per-form thresholds in the Forms control
panel, an enforcement point in ``save_poll`` (after authentication/token
checks, before validation and storage) with a machine-readable HTTP 429
response, atomic counting, and a documented policy for cache outages.

Automatic survey data → PDF merge
---------------------------------

**Status: not implemented.** The fillable-PDF feature fills a template from
the values submitted in the fill form itself, keyed by the raw PDF field
names. Values from stored survey responses are **not** written into the
template, signature fields are never filled, and the "In Form" column is
informational only. See :doc:`ui-fillable-pdf` for what the workflow actually
does.

PDF filling additionally requires PyMuPDF, which is an optional extra
(``pip install "zopyx.surveyjs[pdf]"``) because it is dual-licensed
(AGPL-3.0 or a commercial Artifex licence). Without it the download is
refused with an error message.

Security items tracked outside this page
----------------------------------------

The submission hardening (validation and normalization before ``notify()``,
storage, mail actions and external POST actions) is implemented and
documented in :doc:`validation`. It does **not** cover unrelated findings;
the unfixed items are itemised with impact and recommendation in
``SECURITY.md`` → "Remaining security work" (SSRF through a configured
``post_endpoint_url``, missing rate limiting, CSV/XLSX formula injection,
unaudited exports, token-store atomicity, key length and rotation, missing
session binding, container hardening, dependency pinning, bot controls,
output encoding, CSRF).

Multi-server and container deployments
--------------------------------------

* **Monitoring counters are not atomic** — concurrent clients can lose
  increments under load.
* **Diskcache deployments are per server.** For shared replay protection,
  revocation and one-time-use state across servers, select the RDBMS backend
  (PostgreSQL or MySQL) with ``kv_cache_backend = rdbms``; the monitor
  dashboard stays local to each diskcache store.
* Switching KV backends does not migrate existing entries, so trusted and
  embed tokens must be reissued afterwards.
* The default deployment uses three separate SQLite-on-local-disk stores.
  SQLite over network filesystems (NFS, SMB) is not supported — see
  :doc:`storage`.
* Tests against live PostgreSQL/MySQL containers run only with
  ``RUN_DB_CONTAINER_TESTS=1`` (the CI test job sets it); a local
  ``make test`` skips them.

Removed and unwired code
------------------------

* The LLM-based PDF import helper (``extract_mode="llm"``), the pdfcpu
  extraction pipeline (``pdf_forms.py``) and the standalone pdfcpu CLI
  wrapper (``pdf_form_extract.py``) were removed before the 1.0 beta: they
  were unreachable (no view, no caller, no documented use) and the wrapper
  duplicated the supported ``privacyforms.pdf`` extractor. The pdfcpu binary
  is therefore no longer installed in the container image either.
* The supported PDF paths are the AI generator (``@@ai-upload``) and the
  fillable-PDF workflow.
* ``docs/old/`` contains historical notes, including descriptions of removed
  features. It is not part of the documentation build and not shipped in the
  source distribution; ``docs/*.rst`` is authoritative.
