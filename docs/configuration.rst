=============
Configuration
=============

Survey configuration is stored on each Survey item. Global options are stored
in the Forms control panel (Site Setup > Forms).

Per-survey settings
===================

Actions
-------

.. list-table::
   :header-rows: 1

   * - Field
     - Type
     - Default
     - Description
   * - Actions
     - Set
     - ``store``
     - Submission handling. Options: ``store``, ``mail``, ``mail-notification``, ``post``.
   * - POST endpoint URL
     - URI
     - empty
     - Endpoint to receive JSON payload when the ``post`` action is enabled.

Mail
----

.. list-table::
   :header-rows: 1

   * - Field
     - Type
     - Default
     - Description
   * - E-Mail sender
     - Text
     - empty
     - Sender address for outgoing mail. Required when ``mail`` is enabled.
   * - E-Mail recipient
     - Text
     - empty
     - Primary recipient for mail exports. Required when ``mail`` is enabled.
   * - Subject
     - Text
     - empty
     - Subject for result export emails. Supports ``{poll_id}``.
   * - E-Mail CC
     - List
     - empty
     - CC recipients (one address per line).
   * - E-Mail BCC
     - List
     - empty
     - BCC recipients (one address per line).
   * - Formats
     - Set
     - empty
     - Export formats to attach to result emails.
   * - Body
     - Text
     - empty
     - Mail body for result export emails. Supports ``{created}``, ``{creator}``, ``{formats}``.

Mail notifications
------------------

.. list-table::
   :header-rows: 1

   * - Field
     - Type
     - Default
     - Description
   * - Subject for notifications
     - Text
     - ``Form submitted ({title})``
     - Subject for notification-only emails. Supports ``{title}``, ``{detail_url}``, ``{poll_id}``.
   * - Body for notifications
     - Text
     - See default template
     - Body for notification-only emails. Supports ``{title}``, ``{detail_url}``, ``{poll_id}``.

Form settings
-------------

.. list-table::
   :header-rows: 1

   * - Field
     - Type
     - Default
     - Description
   * - Enable validation (experimental)
     - Bool
     - ``false``
     - Run the Python validator before saving. May reject complex forms.
   * - Force Server Side Validation
     - Bool
     - ``false``
     - Run the external SurveyJS validator binary for each submission.
   * - Max size payload (MB)
     - Int
     - ``1``
     - Maximum accepted submission payload size in megabytes (min 1 MB).

Global settings (Site Setup > Forms)
===================================

.. list-table::
   :header-rows: 1

   * - Setting
     - Description
   * - SurveyJS License Key
     - Optional license key for SurveyJS components.
   * - Log IP addresses
     - When enabled, store client IPs with submissions.
   * - Log user agent
     - When enabled, store user agent strings with submissions.
   * - AI Model
     - LLM model name (provider-specific).
   * - API Key
     - API key for hosted provider models.
   * - Ollama URL
     - Local Ollama server URL. When set, AI generation uses Ollama.
   * - Prompt before
     - Text prepended to the AI prompt.
   * - Default prompt
     - Default text shown in the AI prompt field.
   * - Prompt after
     - Text appended to the AI prompt.
   * - Result storage backend
     - Storage backend for survey results (``zodb`` or ``sqlite``). SQLite stores ``site_id`` and survey id per row.
   * - SQLite path
     - Filesystem path for the SQLite results database. The file can be shared by multiple Plone sites.
