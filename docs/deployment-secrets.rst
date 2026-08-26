=============================
License Key and AI Parameters
=============================

The SurveyJS license key and the AI generator parameters are written into the
Plone registry by ``scripts/init_plone.py`` while the demo site is built. How
the values reach that script differs between local development, a local
Docker build, and the GitHub CI/CD pipeline. This page documents all three
paths.

Registry records
================

.. list-table::
   :header-rows: 1

   * - Setting
     - Registry record
     - Purpose
   * - SurveyJS License Key
     - ``zopyx.surveyjs.interfaces.IFormsSettings.surveyjs_license_key``
     - License for the commercial SurveyJS components. Without a key the
       editor/viewer run in evaluation mode and show the SurveyJS
       "Unlicensed" watermark.
   * - AI model
     - ``zopyx.surveyjs.interfaces.IFormsSettings.ai_model``
     - Model for the AI generator (a ``schema.Choice`` against the
       ``AIModels`` vocabulary, i.e. only models known to the ``llm`` plugin
       registry are accepted).
   * - AI API key
     - ``zopyx.surveyjs.interfaces.IFormsSettings.ai_api_key``
     - Provider API key for the AI generator (``schema.Password``; empty
       values are ignored, so a blank key never overwrites a stored one).

Key format
==========

SurveyJS expects the **raw key** in the format ``<uuid>;1=YYYY-MM-DD``
(49 characters, e.g. ``…;1=2027-01-15``) — base64-encoded values produce the
"Unlicensed" watermark even when the record is set. ``init_plone.py``
normalizes the value automatically: if the value (or its padding-tolerant
base64 decoding) does not match the raw-key pattern it is stored unchanged.

SurveyJS license key — sources and precedence
=============================================

``configure_surveyjs_license()`` in ``scripts/init_plone.py`` resolves the
key in this order:

1. **Key file** — ``surveyjs.licensekey`` (next to the repository root or in
   the current working directory). This is the mechanism used by the CI/CD
   pipeline.
2. **1Password fallback** — ``op read "op://Private/SurveyJS License
   Key/Licence"`` via the 1Password CLI. The field is spelled **"Licence"**
   (British spelling, not "License") and lives in the personal "Private"
   vault. This path is for **local development only** — it relies on the
   desktop-app authentication of the ``op`` CLI and is not usable in CI
   (1Password service accounts cannot be granted access to personal vaults,
   so a ``OP_SERVICE_ACCOUNT_TOKEN`` in GitHub Actions cannot read this
   item).

Failure handling is fail-open: a missing file, missing ``op`` CLI, timeout,
or non-zero exit logs a message and the demo continues without a license key
(watermark visible).

AI parameters — environment variables
=====================================

``configure_ai_model_from_env()`` reads two environment variables:

* ``AI_MODEL`` — the model name (e.g. ``gpt-4o``). In CI this is the GitHub
  secret ``AI_MODEL``; locally it comes from ``.env``.
* ``AI_API_KEY`` — the provider API key (CI name). ``OPENAI_API_KEY`` is
  kept as a fallback for local ``.env`` setups.

Validation is fail-closed for the model: ``ai_model`` is a ``schema.Choice``
against the ``AIModels`` vocabulary, so an invalid model name raises
``ConstraintNotSatisfied`` and aborts the whole init run (a CI build with a
typo'd model fails loudly instead of silently shipping an unconfigured AI).
A missing key (or model) simply skips the corresponding record.

CI/CD — Docker build (``docker-image.yml``)
===========================================

The Docker image builds the demo site at image build time
(``RUN … ./bin/instance run /app/scripts/init_plone.py``). The two value
sources are injected differently:

.. list-table::
   :header-rows: 1

   * - Value
     - CI source
     - Transport into the build
   * - SurveyJS license key
     - GitHub secret ``SURVEYJS_KEY``
     - The workflow writes ``surveyjs.licensekey`` into the checkout; the
       Dockerfile ``COPY . /app`` ships it into the image; ``init_plone.py``
       reads it (file precedence) and the same ``RUN`` removes it again.
   * - AI model / API key
     - GitHub secrets ``AI_MODEL``, ``AI_API_KEY``
     - Passed to ``docker/build-push-action`` as BuildKit secrets
       (``id=ai_model`` / ``id=ai_api_key``) and mounted into the init
       ``RUN`` via ``--mount=type=secret,…,env=AI_MODEL`` /
       ``env=AI_API_KEY``. The values are visible **only during that build
       step** — they never land in image layers or the image config
       (``docker history`` / ``docker inspect`` stay clean).

The CI build log shows the successful wiring (values are masked by GitHub):

.. code-block:: text

   Configured AI model from environment: ***
   Configured AI API key from environment
   Configured SurveyJS license key from file: ***

Notes:

* The license key stays in the image in two places regardless of the
  transport: the ``COPY`` layer (plaintext file) and the built ``Data.fs``
  (the registry record). The image is private on GHCR, so exposure is
  limited to accounts with registry access. A BuildKit secret mount for the
  key file would only remove the redundant plaintext copy — it is
  deliberately not implemented.
* ``surveyjs.licensekey`` must **not** be added to ``.dockerignore`` —
  otherwise ``COPY`` skips it and ``init_plone.py`` falls back to the
  (unavailable) 1Password path, producing an image without license. It is
  in ``.gitignore`` to prevent accidental commits.
* Missing AI secrets (not configured in the repository settings) skip the
  mount and fail open — the image is built without AI configuration.

Local Docker build (``make build``)
===================================

A plain ``docker build`` does not provide the BuildKit secrets, so the AI
parameters stay unset (fail-open). To test the AI wiring locally pass dummy
secrets:

.. code-block:: shell

   AI_MODEL=gpt-4o AI_API_KEY=sk-test-… docker build \
       --secret id=ai_model,env=AI_MODEL \
       --secret id=ai_api_key,env=AI_API_KEY \
       -t privacyforms/demo .

For the license key, place a ``surveyjs.licensekey`` file in the repository
root (the local ``op`` CLI fallback also works when the 1Password desktop
app is running).

Important: ``.env`` never reaches the Docker image
==================================================

``.dockerignore`` excludes ``.env`` from the build context, and the build
receives no environment variables. The ``.env`` chain
(``.env.encrypted`` → ``scripts/filecrypt.py`` → ``load_env_file()``) and
the ``SURVEY_SMTP_*`` / ``OPENAI_API_KEY`` variables therefore apply to
**local non-Docker development only** — the Docker image is configured
exclusively through the CI secrets described above.

Verification
============

* Registry: Site Setup → Forms → SurveyJS fieldset (license key) / AI
  fieldset (model, key), or ``api.portal.get_registry_record`` for the
  records listed above.
* Editor DOM: the survey editor template renders
  ``data-license-key`` from the registry record; a raw 49-character value
  there means the license is active.
* CI log: the three "Configured …" lines shown above (masked values).
