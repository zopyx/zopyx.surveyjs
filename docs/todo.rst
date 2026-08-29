TODO
====

Open design and implementation tasks for the SurveyJS integration.
Entries are removed or rewritten as they are implemented.

Rate limiting concept
---------------------

**Status:** open

The package currently ships monitoring only, not enforcement:

* ``monitoring.check_rate_limit()`` computes per-minute and 5-minute rolling
  averages from diskcache counters, but the function is only called by the
  monitor dashboard (``@@survey-monitor``) for display purposes.
* Nothing in the submission path (``save_poll``) rejects a request based on
  submission rate; there is no 429 response anywhere in the package.
* Counting happens in a subscriber *after* a submission has been accepted,
  so the counters measure accepted traffic, not attempts — rejected floods
  are invisible to them.
* The check itself would need hardening before it can enforce anything:
  it is fail-open by design, the counter update is not atomic
  (get/set instead of ``Cache.incr``), the ``max_per_minute`` limit is a
  hardcoded default, and per-form limits are not exposed.

**Task:** design a rate limiting concept covering at least:

#. Whether enforcement belongs in this package or stays at the reverse
   proxy / WAF layer (the current position in ``SECURITY.md``) — and how
   both layers can be combined without double accounting.
#. Configurable limits: global and per-form thresholds, exposed through
   the Forms control panel / registry.
#. Enforcement point in ``save_poll`` (after authentication/token checks,
   before validation and storage) with a defined response
   (e.g. HTTP 429 with a machine-readable error code, matching the
   existing ``json_error`` contract).
#. Concurrency-correct counting (atomic increments, check-and-consume
   without TOCTOU races) and an explicit fail-open vs. fail-closed policy
   for cache outages.
#. Rate limiting for rejected attempts as well (counting at the entry of
   the request path, not only after acceptance).
#. Documented behavior for embed and direct-DOM submission paths, which
   bypass trusted-access token checks.
