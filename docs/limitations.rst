Known limitations and roadmap
=============================

This page lists what the add-on does **not** implement and how a deployment
is expected to compensate. Everything here is a known gap of the 1.0 beta,
not an oversight of the documentation: where a feature is missing, the
feature documentation points to this page.

Rate limiting
-------------

**Status: enforced in ``@@save-poll``, thresholds site-wide (not per form).**

* ``save_poll`` meters every submission *attempt* per survey and client
  address before the payload is parsed and answers HTTP 429
  (``rate_limited``, with a ``Retry-After`` header) over the configured
  one-minute/one-hour limits. An unmeterable request — the bucket store is
  unavailable — is refused with HTTP 503 (``rate_limit_unavailable``) instead
  of being admitted. See :doc:`security` → "Submission rate limiting".
* Thresholds are global (``submission_rate_limit_per_minute`` /
  ``_per_hour`` in the Forms control panel); there are no per-form limits.
* The bucket update is a read-modify-write on the KV store, so two fully
  concurrent requests can admit one request more than the limit allows. The
  counter is bounded, so this does not accumulate.
* ``monitoring.check_rate_limit()`` still computes per-minute and 5-minute
  rolling averages from the KV counters for the monitor dashboard
  (``@@survey-monitor``) and remains fail-open — it is display data, not the
  enforcement point.
* Those monitoring counters are fed by a subscriber *after* a submission has
  been accepted, so they measure accepted traffic, not attempts. Rejected
  floods are visible in the limiter's own buckets and in the
  ``submission.rate_limited`` audit events instead.

**Deployment guidance:** keep an additional limit at the reverse proxy or WAF
in front of Plone (see :doc:`security` and ``SECURITY.md``); it protects the
process from traffic that never reaches Plone, the built-in limiter protects
your submission/mail/AI budget from what does.

**Roadmap:** per-form thresholds and an atomic counter increment.

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
``post_endpoint_url``, unaudited exports, token-store atomicity, key length
and rotation, missing session binding, container hardening, dependency
pinning, bot controls, CSRF). Submission rate limiting, CSV/XLSX formula
injection and the output encoding of rendered result values were fixed in
1.0b4 and are documented in :doc:`security`.

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
