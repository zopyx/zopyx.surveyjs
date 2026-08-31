# DISKCACHE in zopyx.surveyjs — Role & Usage

In-depth outline of every diskcache usage site in this add-on, based on the
actual code (`monitoring.py`, `browser/services/auth.py`,
`browser/embed_security.py`, `interfaces.py`, `browser/views.py`) and the
verified inventory in the `plone-zeo-sqlite-concurrency` skill
(`references/zopyx-diskcache-inventory.md`).

## Overview

diskcache (`setup.py:73`, runtime dependency; also in test extras at
`setup.py:92`) is a SQLite-backed key-value cache library. The add-on uses
it as **three independent cache stores** — there is no central cache
module; each usage site opens/uses/closes its own `diskcache.Cache`
instance. Every store is a SQLite database (`cache.db` plus `-wal`/`-shm`
sidecars), so all three inherit SQLite's concurrency characteristics (one
writer at a time, WAL journaling, busy_timeout, "not for network
filesystems").

| # | Store               | Module                       | Character |
|---|---------------------|------------------------------|-----------|
| 1 | Auth/token cache    | `browser/services/auth.py`   | security-critical |
| 2 | Embed token cache   | `browser/embed_security.py`  | security-critical |
| 3 | Monitoring store    | `monitoring.py`              | analytics / rate limit |

## 1) Auth / token cache (`browser/services/auth.py`)

**Purpose.** Three security functions: authenticity-token replay
protection, issued-token bookkeeping, and cached "trusted access" token
state.

**Path** (`interfaces.py:435-440`, `auth.py:83-86`): registry setting
`authenticity_token_cache_path`, default `"var/token_cache.db"` — a
**cwd-relative default** (weakness, see "Known weaknesses" below). Read
via `AuthService._auth_token_cache_path()`.

**Lifecycle pattern.** Every operation opens a fresh `Cache(path)` and
closes it in a `finally`-block (`_token_cache()` at `auth.py:88-95`). A
failed open returns `None`; callers then decide fail-closed or fail-open.

**Key namespaces + TTLs**

- `issued:<token>` (`auth.py:111-113, 141`) — value `"ISSUED"`, TTL 24 h.
  Written when an authenticity token is generated (`build_auth_token`).
  Bookkeeping only — nothing validates against it.
- `received:<token>` (`auth.py:115-117, 398-408`) — value `"RECEIVED"`,
  TTL 24 h. Written with `cache.add()` — the **atomic replay-protection
  marker**. `add()` returns `True` only if the key did not already exist; a
  `False` return means the exact same token was submitted before → HTTP
  403 `auth_token_replay` (`auth.py:400-408`).
- `trusted:<token>` (`auth.py:44-46, 162-169`) — value = metadata dict,
  TTL = per-form `trusted_access_ttl_hours` (default 168 h,
  `auth.py:48-55`). Metadata: `form_id`, `form_version`, `issued_at`,
  `expires_at`, `state`. Used by `trusted` (cached) access mode only.
  Revocation is modeled by rewriting `state` to `"REVOKED"` — checked at
  `auth.py:198-206`.

**Operations used**

- `cache.set(key, value, expire=...)` → issuance + trusted metadata
- `cache.add(key, value, expire=...)` → atomic replay markers
- `cache.get(key)` → trusted metadata lookup

The deliberately distinct primitives matter: `set()` for
"write/overwrite", `add()` for "insert only if absent" — `add()` is the
replay-protection primitive and is atomic across processes (diskcache's
own file locking).

**Fail-closed behavior**

- `require_auth_token` (`auth.py:386-396`): cache unavailable → HTTP 503
  `auth_service_unavailable`, request **rejected** (replay protection must
  not silently degrade).
- `_require_trusted_access_cached` (`auth.py:172-184`): cache unavailable
  → HTTP 503 `trusted_access_cache_unavailable`.

**Role in request flow.** Called from `browser/views.py`:
`get_form_json` (`views.py:505-506` `_require_trusted_access`) and
`save_poll` (`views.py:766-769` trusted access + auth token).
Editors/Managers bypass; direct-DOM embed submissions use the embed token
stack instead (`views.py:673-764`).

## 2) Embed token cache (`browser/embed_security.py`)

**Purpose.** Direct DOM Embedding: token metadata for tracking/revocation
plus one-time-use enforcement (anti-replay for embed JWTs).

**Path** (`embed_security.py:53-59`): hardcoded
`os.path.join(os.getcwd(), "var", "embed_token_cache.db")` — **no registry
override** (weakness). `_get_embed_cache()` returns `None` on any
exception.

**Key namespaces + TTLs**

- `embed_token:<jti>` (`embed_security.py:247-258`) — value = metadata
  dict `{survey_uid, origin, issued_at, expires_at, used: False}`, TTL =
  token TTL + 60 s (tokens live 60-3600 s; `generate_embed_token` clamps
  at line 228). Written on token issuance; informational / revocation
  tracking.
- `embed_token_used:<jti>` (`embed_security.py:328-330`) — value `True`,
  TTL 1 h. One-time marker written with `cache.add()` in
  `mark_token_used()`. `add()` semantics again: `True` = first use
  (allowed), `False` = replay.

**Fail-closed behavior.** `mark_token_used`
(`embed_security.py:313-333`): cache unavailable → returns `False` →
`views.py:840-845` rejects the submission ("fail-closed: deny rather than
allow replay").

**Role in request flow** (`views.py` `save_poll`, lines 673-764, 840-845):
embedded clients send `X-Embed-Token`; the view validates origin allowlist
+ JWT signature (`validate_embed_token`), and **after the full submission
pipeline succeeds** marks the `jti` used via `mark_token_used(jti)`. The
one-time mark is the last gate before the response is accepted.

## 3) Monitoring store (`monitoring.py`)

**Purpose.** Submission statistics (dashboard time series), per-form
breakdowns, processing-time latency buckets, and rate limiting. Pure
analytics plus an optional rate-limit gate.

**Path** (`monitoring.py:46-64`): `$INSTANCE_HOME/var/surveyjs-monitor`,
else `/tmp/surveyjs-monitor-<site_id>` (`site.getId()`), final fallback
`/tmp/surveyjs-monitor`. Opened with `Cache(cache_dir, timeout=5)`
(`monitoring.py:73`) — `timeout` here is diskcache's **lock** timeout, not
the SQLite busy timeout.

**Key namespaces** (`monitoring.py:27-31`) **+ TTL**

- `sub:<YYYYMMDDHHMM>` — global per-minute submission buckets
- `form:<uid>:<YYYYMMDDHHMM>` — per-form per-minute buckets
- `duration:<YYYYMMDDHHMM>` — global per-minute latency buckets
- `form-duration:<uid>:<...>` — per-form latency buckets
- `global:stats` — defined, reserved

All entries expire after 25 h (`monitoring.py:186, 260`) so every time
window (5 m…24 h) is fully covered.

**Operations used**

- read-modify-write counters: `cache.get(key, {})` → mutate dict →
  `cache.set(key, data, expire=25h)` (`_increment_counter` lines 146-189,
  `_record_duration_bucket` lines 227-262). **NOT ATOMIC** — get/modify/set
  loses updates under concurrent clients (known weakness; classified as
  "may be in-memory").
- `cache.iterkeys()` full scans for aggregation: `get_submission_stats`
  (lines 442, 486, 552, 592), `_get_form_time_series` (line 350),
  `_get_form_breakdown` (line 552), `cleanup_old_data` (line 723). The
  dashboard reads are O(keys) scans, not indexed queries.
- `cache.delete(key)` in `cleanup_old_data` (line 739).

**Fail-open behavior.** Monitoring **never** breaks submissions:
`record_submission` (lines 98-100) and `record_submission_duration`
(line 199) silently return when the cache is unavailable;
`_increment_counter` catches everything (lines 188-189);
`check_rate_limit` returns `(True, {"error": ...})` — i.e. rate limiting
**fails open** (lines 662-663): it degrades to allowing everything when
the cache is missing.

**Role in request flow.** `record_submission` runs as an event subscriber
on the submission event; `record_submission_duration` is called from
`save_poll` right after the event fires (`views.py:888-890`).
`check_rate_limit` is the hook for the rate-limiting concept
(`docs/todo.rst`; not yet wired as a hard gate).

## Cross-cutting: what diskcache gives the app

- **Persistent TTL storage without Redis**: expiry is enforced lazily by
  diskcache; values are pickled Python dicts.
- **Atomic `add()`** = the anti-replay primitive used in BOTH security
  stores (`received:`, `embed_token_used:`). This is the single most
  important API choice in the codebase.
- **Multi-process safety on one host**: diskcache's file locking makes
  `add()` atomic across Zope clients sharing the same cache file.
- **SQLite defaults**: diskcache 5.x sets `journal_mode=WAL` by default
  and relies on the DBAPI busy_timeout (5000 ms) — so WAL is correctly in
  force for all three stores without explicit PRAGMA code.

## Known weaknesses / concurrency semantics (verified, ZEO-relevant)

1. **cwd-dependent paths break replay protection on one host**: the auth
   default (`"var/token_cache.db"`) and the hardcoded embed path
   (`os.getcwd()/var/embed_token_cache.db`) resolve per-process when Zope
   clients start from different directories → silently different cache
   files → replay markers no longer shared. Only the monitoring store
   anchors to `INSTANCE_HOME`. (GitHub issue #33, `docs/todo.rst`.)
2. **Non-atomic counters**: monitoring increments are get/modify/set →
   lost updates under concurrent clients. Use `Cache.incr` if counts must
   be exact.
3. **Multi-server (dedicated ZEO servers / multiple hosts)**: per-server
   stores mean replay markers, trusted-token revocation/expiry and embed
   one-time markers become **per-server** → guarantees weaken between
   servers. Fail-closed 503s do NOT catch this (they only fire when the
   cache is MISSING, not when it diverges). NFS sharing is not an option
   (SQLite over NFS unsupported).
4. **Cluster-safe alternative already in-repo**: `trusted-tokens` mode
   uses `ITokenStore` (ZODB or SQL backend) — transactional, shared; the
   pattern for security-critical state.

## Security classification (durable+shared vs in-memory)

**MUST stay durable + shared** (disk or Redis, never process-local
memory):

- `received:` replay markers
- `trusted:` trusted-access state (revocation/expiry)
- `embed_token_used:` one-time markers

**MAY be in-memory** without safety loss:

- monitoring counters/buckets/stats (analytics; disk only buys dashboard
  history across restarts)
- `issued:` markers, `embed_token:` metadata (informational)

## Tests & docs

- `tests/test_integration_views.py` references diskcache (replay/trusted
  access integration coverage).
- Docs: `docs/security.rst`, `docs/survey-options.rst` (trusted TTL
  field), `docs/global-options.rst`, `docs/todo.rst` ("Diskcache handling
  in ZEO deployments" — status open; "Rate limiting concept" uses the same
  counters). Older analysis docs under `docs/old/` also reference it.
- Dependency declared in `setup.py` `install_requires` and test extras.

## Bottom line

diskcache is load-bearing for **security** (replay protection and
one-time-use via atomic `add()`, fail-closed) and for **analytics**
(monitoring counters, fail-open). Its main risk surface in production is
path resolution (cwd dependence) and per-server divergence in multi-server
ZEO setups — both tracked in issue #33 / `docs/todo.rst`.
