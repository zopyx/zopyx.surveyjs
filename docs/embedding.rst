=========
Embedding
=========

Surveys can be embedded into external websites in two ways, controlled by
the per-survey **Embedding mode** setting (``none`` / ``iframe`` /
``direct``):

* **Iframe** — the classic, recommended and secure option. The survey runs
  in an iframe on the external page; no further configuration is needed
  beyond enabling the mode.
* **Direct DOM** (experimental) — the survey is injected directly into the
  embedding page without an iframe. Seamless integration, but requires a
  global master switch, a signing key and per-survey origin allowlists.
  The full security model is described in :doc:`security`.

When embedding is disabled (mode ``none``), the embed views return
HTTP 403.

Iframe embedding
================

Quick start:

1. Edit the survey and set **Embedding mode** to **Iframe**.
2. Embed the embed view (``@@viewer-embed``) in an iframe:

.. code-block:: html

   <iframe
     src="https://your-plone-site.com/surveys/customer-satisfaction/@@viewer-embed"
     width="100%"
     height="800"
     style="border: 0;"
     loading="lazy"
     title="Customer Satisfaction Survey">
   </iframe>

Security: for the embed view the add-on clears ``X-Frame-Options`` and
sets ``Content-Security-Policy: frame-ancestors *`` instead. When
embedding is disabled, the view returns 403. Submissions from the iframe
are subject to the same protection as the normal viewer (access mode,
authenticity token — see :doc:`security`).

Direct DOM embedding
====================

Prerequisites (all three):

1. **Global master switch**: *Enable Direct DOM Embedding globally* in
   Site Setup > Forms → Direct DOM Embedding (off by default).
2. **Signing key**: *Embed Token Signing Key* (dedicated HMAC key; rotate
   regularly).
3. **Per-survey configuration**: Embedding mode = *Direct*, plus at least
   one entry in *Allowed origins for direct embedding* — the origins of
   the pages that may embed the survey (e.g. ``https://example.com``;
   HTTPS required, HTTP only for localhost, no path or trailing slash;
   max 10 per survey, globally capped by *Maximum origins per survey*).

Embedding a survey

The embedding page includes the loader script (``@@embed-loader``) and
obtains a short-lived, origin-bound embed token (``@@embed-token``; the
public ``@@embed-config`` endpoint serves the loader configuration). On
submission, the page sends the token in the ``X-Embed-Token`` header
together with the ``Origin`` header; the server validates the origin
against the allowlist, the token signature/expiry and its one-time use
before accepting the submission.

Key properties (implemented in ``embed_security.py``):

* Tokens are HS256 JWTs bound to the survey and to a single origin
  (the token's ``origin`` claim must match the request's ``Origin``).
* Tokens expire after the per-survey **Embed token TTL** (default 300 s,
  60–3600 s) and are **single-use for submissions** — a replayed token is
  rejected (``token_already_used``).
* CORS headers are set only for allowlisted origins (never a wildcard);
  responses include ``X-Content-Type-Options: nosniff``,
  ``X-Frame-Options: DENY`` and ``Referrer-Policy``.
* If the global master switch is off, embed submissions are rejected
  (``feature_disabled``).

Demo and helpers

* ``@@embed-direct-demo`` — a demo page for Direct DOM embedding
  (``cmf.ModifyPortalContent``).
* ``@@embedded-demo`` — a Manager-only demo page showing iframe embedding.
* ``@@embed-surveyjs`` — serves the SurveyJS assets for embedded surveys.

Related documentation
=====================

* :doc:`security` — the embedding security stack in detail (origin
  validation, tokens, CORS discipline).
* :doc:`endpoints` — ``@@embed-token``, ``@@embed-config``,
  ``@@embed-loader`` and the submission flow.
* :doc:`survey-options` — the per-survey Embedding settings.
* :doc:`global-options` — the global Direct DOM Embedding settings.
