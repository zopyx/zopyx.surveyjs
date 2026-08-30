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

**Status:** open

All three diskcache stores (SQLite files) are written and read by every
Zope client process, so their behavior in a ZEO setup — multiple local
clients on one host, or dedicated servers — needs an explicit design.
Current state (verified by inspection and an engine probe):

* Three usage sites, all SQLite-on-local-disk via diskcache:

  * Monitoring counters (``monitoring.py``): per-minute submission
    counters, latency buckets and global stats with 25 h expiry, under
    ``$INSTANCE_HOME/var/surveyjs-monitor`` (``/tmp`` fallback). Pure
    analytics — submissions are durably stored in ZODB/SQL regardless.
  * Auth/token cache (``browser/services/auth.py``): ``issued:``
    markers, ``received:`` auth-token replay markers (24 h) and
    ``trusted:`` trusted-access token metadata (TTL hours), under the
    registry setting ``authenticity_token_cache_path`` with a
    **cwd-relative** default (``var/token_cache.db``).
  * Embed cache (``browser/embed_security.py``): ``embed_token:``
    metadata and ``embed_token_used:`` one-time markers (1 h), under
    ``os.getcwd()/var/embed_token_cache.db`` — hardcoded, no registry
    override, cwd-dependent.

* Diskcache itself is multi-process safe on one host (WAL mode verified,
  atomic ``add`` for one-time markers, fail-closed when the cache is
  unavailable). SQLite over network filesystems (NFS, SMB) is
  explicitly ruled out by ``docs/storage.rst`` and applies to diskcache
  identically.
* Known weaknesses in a ZEO setup:

  * Two of the three paths depend on the process working directory;
    clients started from different directories silently use different
    cache files, which breaks replay protection even on a single host.
  * Monitoring counter increments are non-atomic get/modify/set
    (``monitoring.py``) — concurrent clients lose updates.
  * Multi-server: per-server stores weaken security state — auth-token
    replay markers, trusted-token revocation/expiry and embed one-time
    markers are then per-server, while ``trusted-tokens`` mode (ITokenStore
    in ZODB/SQL) stays cluster-safe. The monitor dashboard shows only
    local traffic.

**Task:** design the diskcache handling concept covering at least:

#. Unify cache path configuration: registry settings for the embed and
   monitoring caches (auth already has one) and resolve all relative
   paths against ``INSTANCE_HOME``, never against the working directory.
#. Per-deployment topology matrix (single process / multiple local ZEO
   clients / dedicated servers with or without a shared filesystem) and
   which guarantees hold in each: replay protection, trusted-token
   revocation and expiry, embed one-time use, monitoring completeness,
   fail-closed behavior.
#. Storage policy for security-critical state (``received:`` replay
   markers, ``trusted:`` token state, ``embed_token_used:`` markers):
   keep durable diskcache on one host, or move to the transactional
   store (ZODB/SQL, the ITokenStore pattern) / a shared in-memory store
   (e.g. Redis) for cluster-correct semantics.
#. Which entries may move to in-memory without safety loss: monitoring
   counters and buckets, ``issued:`` markers, ``embed_token:`` metadata
   — and whether a shared store should replace all three sites.
#. Atomic monitoring increments (``Cache.incr`` / check-and-consume) and
   an explicit decision on cross-server aggregation for the dashboard
   and any future rate limiting.
#. Tests pinning cache-path resolution (INSTANCE_HOME vs. cwd) and
   concurrent counter/one-time-marker behavior.
