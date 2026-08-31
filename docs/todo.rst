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

Diskcache handling in ZEO deployments
-------------------------------------

**Status:** implemented (backend selection and path configuration)

The three production cache sites now use the shared KV facade and the
registry settings ``kv_cache_backend``, ``kv_cache_directory``,
``kv_cache_database_uri`` and ``kv_cache_lock_timeout_seconds``. Diskcache
paths are resolved against ``INSTANCE_HOME`` and logical stores are isolated
with ``auth``, ``embed`` and ``monitoring`` namespaces. The SQL facade supports
shared PostgreSQL/MySQL deployments; switching backends does not migrate
existing cache entries, so trusted/embed tokens must be reissued.

Remaining design work:

* Monitoring counters still use non-atomic get/modify/set updates.
* A deployment topology matrix and operational migration procedure should be
  added to the administrator documentation.
* Tests should cover live PostgreSQL/MySQL configured-factory operation in
  addition to the existing facade/container contract tests.

* Default deployment: three usage sites use separate SQLite-on-local-disk
  stores via diskcache. With ``kv_cache_backend = rdbms``, all three instead
  share the configured SQL KV store with logical namespaces:

  * Monitoring counters (``monitoring.py``): per-minute submission
    counters, latency buckets and global stats with 25 h expiry, under
    ``$INSTANCE_HOME/var/surveyjs-cache/monitoring``. Pure
    analytics — submissions are durably stored in ZODB/SQL regardless.
  * Auth/token cache (``browser/services/auth.py``): ``issued:``
    markers, ``received:`` auth-token replay markers (24 h) and
    ``trusted:`` trusted-access token metadata (TTL hours), under the
    configured ``authenticity_token_cache_path`` only when explicitly
    customized; otherwise under ``$INSTANCE_HOME/var/surveyjs-cache/auth``.
  * Embed cache (``browser/embed_security.py``): ``embed_token:``
    metadata and ``embed_token_used:`` one-time markers (1 h), under
    ``$INSTANCE_HOME/var/surveyjs-cache/embed`` by default.

* Diskcache itself is multi-process safe on one host (WAL mode verified,
  atomic ``add`` for one-time markers, fail-closed when the cache is
  unavailable). SQLite over network filesystems (NFS, SMB) is
  explicitly ruled out by ``docs/storage.rst`` and applies to diskcache
  identically.
* Known remaining deployment limitations:

  * Monitoring counter increments are non-atomic get/modify/set
    (``monitoring.py``) — concurrent clients can lose updates.
  * Multi-server diskcache deployments remain per-server. Select the RDBMS
    backend with PostgreSQL or MySQL for shared replay, revocation and
    one-time-use state. The monitor dashboard is otherwise local to each
    diskcache store.

**Task:** finish the remaining atomic-counter and deployment-matrix work; the
backend selection, centralized paths and production facade wiring are now
implemented.