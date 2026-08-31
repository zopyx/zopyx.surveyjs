==============
Global options
==============

These options are stored in the Plone registry and edited in the Forms
control panel (Site Setup > Forms). They provide site-wide defaults and
switches. Per-survey settings generally take precedence over the global
defaults (notably for the Mail settings). Survey-specific options live in
the :doc:`survey-options`.

The control panel is organized into the tabs below.

.. image:: _static/screenshots/controlpanel-general.png
   :align: center
   :alt: Forms control panel (General tab)

General
-------

.. list-table::
   :header-rows: 1

   * - Setting
     - Description
   * - SurveyJS License Key
     - Optional license key for the commercial SurveyJS components. Without
       a key the components run in evaluation/open-source mode, which shows
       the SurveyJS watermark and may limit certain features. Enter the key
       exactly as provided by SurveyJS — whitespace or line breaks invalidate
       it. Leave empty to stay in evaluation mode. How the key is provided
       to the site at build time (key file, 1Password, GitHub secret) is
       documented in :doc:`deployment-secrets`.
   * - Features enabled
     - Toggles which features are available in the UI site-wide. Options:
       ``ai`` (AI-assisted form generation), ``chatbot`` (the form chatbot),
       ``dashboard`` (the results dashboard), ``pdf-generator`` (PDF export
       of results) and ``fillable-pdf`` (fillable PDF workflows). Default:
       ``ai``, ``dashboard``, ``pdf-generator``. Unchecking a feature hides
       its entry points from the user interface; the underlying data is not
       deleted.

AI
--

.. image:: _static/screenshots/controlpanel-ai.png
   :align: center
   :alt: Forms control panel (AI tab)

These settings select the LLM used for AI-assisted form generation and how it
is reached. The three provider modes are **mutually exclusive** — configure
exactly one of them:

* **installed** (default) — uses the LLM provider bundled with the
  installation. Configure *AI Model* and, if the provider requires it,
  *API Key*.
* **ollama** — a local Ollama server. Set *Ollama URL*; *Ollama Model*
  defaults to ``llama3.2`` when empty. No API key is needed because the
  model runs on your own machine.
* **custom** — any OpenAI-compatible API endpoint. Requires **all three**
  fields: *LLM Name*, *LLM API URL* and *Custom API Key*.

.. list-table::
   :header-rows: 1

   * - Setting
     - Description
   * - AI Provider
     - Selects the provider mode: ``installed``, ``ollama`` or ``custom``.
       The modes are mutually exclusive; switching the provider changes which
       of the fields below are relevant. Default: ``installed``.
   * - AI Model
     - The model name passed to the selected provider (e.g. ``gpt-5-nano``
       for the installed provider, ``deepseek-chat`` for a custom endpoint).
       The choice list is provider-specific. Larger models usually produce
       better forms but are slower and more expensive. Leave empty to use
       the provider's default model.
   * - API Key
     - API key for hosted provider models. Stored securely (password field,
       not shown in plain text). If empty, AI generation fails unless the
       provider is configured through another mechanism.
   * - Ollama URL
     - Base URL of a local Ollama server, e.g. ``http://localhost:11434``.
       When set, AI generation uses Ollama instead of the default provider.
       Only relevant in ``ollama`` mode.
   * - Ollama Model
     - The model name on the Ollama server (e.g. ``llama3.2``). If empty,
       ``llama3.2`` is used. Only relevant in ``ollama`` mode.
   * - LLM Name
     - The model name as expected by the custom endpoint, e.g.
       ``deepseek-chat``. Only relevant in ``custom`` mode.
   * - LLM API URL
     - Base URL of the custom OpenAI-compatible API endpoint, e.g.
       ``https://api.deepseek.com``. Only relevant in ``custom`` mode.
   * - Custom API Key
     - API key for the custom endpoint. Stored securely. Only relevant in
       ``custom`` mode.
   * - Prompt before
     - Text/instructions inserted **before** the user's prompt when a form
       is generated. Use this to enforce global rules, tone or formatting
       requirements for every generated form. Keep it short to avoid
       conflicts with the user's own instructions.
   * - Default prompt
     - Default text shown in the AI prompt field of the form generation UI.
       This only prefills the input; it is not automatically prepended or
       appended to the user's final prompt.
   * - Prompt after
     - Text/instructions appended **after** the user's prompt. Use this to
       add constraints or a mandatory output structure (e.g. "always include
       a validation section") while still letting users supply their own
       content.

Logging
-------

.. image:: _static/screenshots/controlpanel-logging.png
   :align: center
   :alt: Forms control panel (Logging tab)

.. list-table::
   :header-rows: 1

   * - Setting
     - Description
   * - Log IP addresses
     - Store the submitting client's IP address together with each
       submission. Helpful for abuse detection and audits, but introduces
       privacy and data-protection obligations (the IP is personal data).
       Default: off.
   * - Log user agent
     - Store the submitting browser's user-agent string with each
       submission. Useful for diagnostics and statistics; like the IP
       address it may be considered personal data. Default: off.

Mail
----

Global defaults for outgoing result-export e-mails. Per-survey Mail settings
override these values; surveys without their own Mail settings inherit them.

.. image:: _static/screenshots/controlpanel-mail.png
   :align: center
   :alt: Forms control panel (Mail tab)

.. list-table::
   :header-rows: 1

   * - Setting
     - Description
   * - E-Mail sender
     - Default sender address for outgoing mail (e.g.
       ``no-reply@example.org``). Used whenever a survey has no sender of
       its own.
   * - E-Mail recipient
     - Default primary recipient for notifications and result exports.
   * - Subject
     - Default subject for result export e-mails. Supports ``{poll_id}``.
   * - E-Mail CC
     - Default CC recipients (one address per line).
   * - E-Mail BCC
     - Default BCC recipients (one address per line).
   * - Formats
     - Default export formats to attach when Mail sends results (``text``,
       ``md``, ``html``, ``pdf``, ``csv``, ``xlsx``, ``xml``, ``docx``).
   * - Body
     - Default body text for result export e-mails. Supports ``{created}``,
       ``{creator}`` and ``{formats}``.

Storage
-------

.. image:: _static/screenshots/controlpanel-storage.png
   :align: center
   :alt: Forms control panel (Storage tab)

.. list-table::
   :header-rows: 1

   * - Setting
     - Description
   * - Result storage backend
     - Where survey results and access tokens are stored:

       * ``zodb`` (default) — results live in Plone's ZODB object database
         next to the surveys. No external infrastructure required.
       * ``rdbms`` — results are written to a relational database. Rows
         include the ``site_id`` and the survey id, which makes it easy to
         run cross-site reports or integrate the data with external BI
         tooling via SQL.
   * - Database URI
     - SQLAlchemy-style database URI for the results database, e.g.
       ``sqlite:///var/surveyjs-results.db`` (default) or
       ``postgresql+psycopg2://user:pass@host/db``. Ignored when the
       ``zodb`` backend is selected.

Migrating results between backends
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Existing ZODB results can be migrated to the relational backend with the
helper in ``storage_migration.py`` (run from a Zope/Plone console script)::

    from zopyx.surveyjs.storage_migration import migrate_zodb_results_to_rdbms
    count = migrate_zodb_results_to_rdbms(context, database_uri="postgresql+psycopg2://user:pass@host/db")

The function copies the stored submissions (with ``site_id``, ``poll_id``
and sequence numbers) into the configured database and returns the number
of migrated rows. Switch the backend in the control panel afterwards; the
two backends are independent, so the ZODB data remains in place as a
backup.

The KV cache backend is configured independently from result storage. It is
used for authenticity-token replay protection, trusted-access token metadata,
Direct DOM embed-token one-time-use markers, and monitoring data.

.. list-table:: KV cache settings
   :header-rows: 1

   * - Setting
     - Description
   * - KV cache backend
     - ``diskcache`` (default) stores the caches in local SQLite-backed
       diskcache directories. ``rdbms`` uses the SQL KV facade and is the
       recommended choice when multiple application servers must share replay
       and one-time-use state.
   * - KV cache directory
     - Base directory for the ``diskcache`` backend. Default:
       ``var/surveyjs-cache``. Relative paths are resolved against
       ``INSTANCE_HOME``. Separate ``auth``, ``embed`` and ``monitoring``
       namespaces are created below this directory.
   * - KV cache database URI
     - SQLAlchemy URI for the ``rdbms`` backend. PostgreSQL or MySQL are
       recommended for multi-server deployments. This setting is required
       when the RDBMS KV backend is selected; the result storage URI is not
       used implicitly.
   * - KV cache lock timeout
     - Diskcache lock timeout in seconds. Default: ``5.0``; ``0`` disables
       waiting for a lock. This setting does not control SQL query timeouts.

The cache backend is deliberately not inferred from ``Result storage
backend``. This prevents changing result persistence from unexpectedly
changing security-cache behavior. See ``DISKCACHE.md`` in the repository root
for the complete backend, namespace, migration and deployment guidance.

RDBMS driver note
~~~~~~~~~~~~~~~~~

Selecting ``rdbms`` does not install a database driver automatically. SQLite
uses Python's built-in ``sqlite3`` driver. PostgreSQL requires either
``psycopg2``/``psycopg`` and MySQL requires either ``pymysql`` or
``mysqlconnector``. The KV facade additionally supports DuckDB through
``duckdb-engine`` and ``duckdb``; DuckDB is not a shared multi-host ZEO
backend. Install the selected driver's package in the same Python environment
as Plone. See :doc:`storage` for the complete Result Storage versus KV
support matrix and installation examples.

Security
--------

.. image:: _static/screenshots/controlpanel-security.png
   :align: center
   :alt: Forms control panel (Security tab)

.. list-table::
   :header-rows: 1

   * - Setting
     - Description
   * - Enable authenticity token
     - Require a short-lived authenticity token for every form submission.
       The token is issued to the visitor when the form is loaded and must be
       presented with the submission; this prevents unauthenticated and
       replayed submissions (e.g. scripted bulk posting). Default: on.
       Disable only when an integration cannot obtain a token.
   * - Authenticity token secret
     - HMAC secret used to sign authenticity tokens. Keep it private and
       stable: rotating it invalidates all outstanding tokens, so existing
       visitors would have to reload the form before submitting.
   * - Authenticity token TTL (seconds)
     - Lifetime of authenticity tokens in seconds. Default: ``3600`` (one
       hour, minimum 60). Shorter TTLs reduce the replay window but force
       visitors with a slow form session to reload.
   * - Authenticity token issuer
     - Issuer claim embedded in tokens. Default: ``privacyforms.studio``.
       Use a stable, unique identifier for your site.
   * - Authenticity token audience
     - Audience claim embedded in tokens. Default: ``privacyforms.studio``.
       A distinct audience value prevents tokens being accepted in other
       contexts or environments.
   * - Authenticity token cache path
     - Filesystem path of the diskcache used to store token metadata.
       Default: ``var/token_cache.db``. The path must be writable by the
       Plone process and should not be publicly accessible.

Direct DOM Embedding
--------------------

The Direct DOM embedding feature lets external websites embed a survey
without an iframe, by injecting the survey directly into the embedding page.
It requires **all** of the following: the global master switch below, a
signing key, and per-survey allowed origins (see the Embedding tab on the
survey).

.. image:: _static/screenshots/controlpanel-embedding.png
   :align: center
   :alt: Forms control panel (Embedding tab)

.. list-table::
   :header-rows: 1

   * - Setting
     - Description
   * - Enable Direct DOM Embedding globally
     - Master switch for the whole feature. Default: off. While it is off,
       no survey can be embedded via Direct DOM regardless of the per-survey
       Embedding settings.
   * - Embed Token Signing Key
     - HMAC key used to sign embed tokens. Keep it secret and rotate it
       regularly; rotating invalidates previously issued embed tokens.
   * - Maximum origins per survey
     - Upper limit for the number of allowed origins per survey (default
       ``10``, range 1–100). This caps the blast radius if a survey is
       configured carelessly — a survey can never allow more origins than
       this value, even if the list field would permit more.
