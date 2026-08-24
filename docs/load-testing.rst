Load testing
============

The repository ships a small, dependency-free load test for the survey
submission pipeline, built on `k6 <https://k6.io>`_ (Grafana's HTTP load
testing tool). k6 is a single binary — nothing is installed into the
buildout environment.

What it exercises
-----------------

The script in ``loadtest/survey-load.js`` simulates a realistic visitor
session against a running instance:

1. **Login** — POST ``/demo/login_form`` with the editor credentials
   (the Plone login form requires the ``buttons.login`` submit field).
2. **Read path** — GET the survey viewer page; the page carries a fresh
   single-use ``auth_token`` and a CSRF token in JSON script tags.
3. **Write path** — POST ``@@save-poll`` with a valid answer set,
   including the auth and CSRF tokens. This runs the full server-side
   validation (external deno/bun binary) and the ZODB store subscribers.

Every submitted answer set passes the external validator, so failures
shown by the test are real server-side problems, not payload rejections.

Running it
----------

::

   k6 run loadtest/survey-load.js

Default: a **constant-arrival-rate stress test** — exactly 20
submissions/second for 60 seconds (~1200 iterations, up to 100 VUs).
The arrival rate is enforced by k6's executor, so the iteration count
does not depend on how fast the server responds; iterations that cannot
start in time are dropped and reported.

All settings can be overridden via environment variables:

``K6_SURVEY_URL``
   Survey viewer URL to load (default: the multilingual demo survey).
``K6_LOGIN_URL``
   Plone login form URL (default: ``http://localhost:8082/demo/login_form``).
``K6_USER`` / ``K6_PASSWORD``
   Credentials used for the per-VU login.
``K6_RATE``
   Submissions per second (default: 20).
``K6_DURATION``
   Test duration (default: 60s).

The demo surveys are private, so a logged-in session is required.
Using an account with manager-level rights skips the auth-token checks
entirely (``can_manage_portal_content`` bypasses trusted access and
token validation in ``views.py``).

Pitfalls and known behaviour
----------------------------

* **k6 session-cookie jar bug** — on the k6 2.2.0 development build the
  default cookie jar drops the ``__ac`` cookie between iterations, which
  silently logs every VU out after its first iteration. The script
  therefore manages the session cookie manually (``redirects: 0`` plus an
  explicit ``Cookie`` header). Keep that workaround if the script is
  updated.
* **Auth tokens are single-use** — each iteration fetches a fresh token
  from the viewer page; a token must never be reused (replay protection
  returns 403).
* **ZODB ConflictError hotspot** — at 5 VUs the submission storage
  (shared ``BTrees.OOBTree`` buckets) already produces conflicts; Zope
  retries them, but the retry re-executes ``save_poll`` with an already
  consumed auth token, so every conflict surfaces as a client-visible
  403 (observed: 9–12% of submissions at 5 VUs, growing with the stored
  result count). This is the current scaling ceiling of the write path.
* **Submissions are real** — every successful iteration stores a
  submission in the ZODB. Use a throwaway survey or clear results
  afterwards (``@@clear-results``) to keep a demo site clean.

Observed baseline (2026-08, dev instance)
-----------------------------------------

Light load (5 VUs, stages, ~250 iterations):

* Read path and successful submissions: p(95) ≈ 175 ms, avg ≈ 118 ms.
* External validation: ~95 ms per submission.
* ~9–12% of submissions failed via the conflict/replay interaction
  described above; HTTP-level errors on the read path: 0.

Stress load (20 submissions/s for 60s, up to 100 VUs):

* The instance saturates: p(95) latency ≈ 17.4 s (vs 175 ms at 5 VUs),
  avg ≈ 8.7 s on *successful* requests too — the whole request path
  degrades, not just the writes.
* Target 1200 iterations: only ~317 completed, 884 dropped by the
  executor; ~481 submissions were stored server-side (dropped k6
  iterations still sent their requests).
* Server-side in 60s: 195 ZODB ConflictErrors and 187 auth-token
  replays; submit success rate ≈ 62%.

The ZODB conflict/replay interaction is the scaling ceiling: it caps the
write path well below 20 submissions/s on a single-instance setup.
