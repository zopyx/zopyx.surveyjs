=========
Endpoints
=========

The endpoints are the machine-readable HTTP interfaces of the SurveyJS
integration: JSON APIs, submission handling, downloads and management
actions. User-facing pages are documented separately in :doc:`views`.

Conventions
===========

URL pattern
    Endpoints live on the survey object unless noted otherwise::

        https://example.org/demo/my-survey/@@<endpoint-name>

    Site-root endpoints (``@@forms-settings``, ``@@ai-test``,
    ``@@llm-models``, ``@@survey-monitor``) are called on the site root.

HTTP methods
    Mutating endpoints are invoked with **POST**, read-only endpoints with
    **GET**. Parameters are sent as form data (``application/x-www-form-urlencoded``)
    or as JSON body, as noted per endpoint.

Permissions
    * ``zope2.View`` — publicly callable (subject to the survey's access
      mode and authenticity-token settings).
    * ``cmf.ModifyPortalContent`` — requires the Editor role or Manager.
    * ``cmf.ManagePortal`` — requires the Manager role.

JSON responses
    Successful endpoints answer with JSON, usually ``{"isSuccess": true}``
    or a data object. Errors use a JSON body with ``error`` and optional
    ``message`` fields plus a matching HTTP status::

        {"isSuccess": false, "error": "invalid_json", "message": "..."}

Survey access protection
    Public submission endpoints (``@@save-poll``, ``@@get-form-json``)
    enforce the survey's configuration:

    * **Access mode**: for ``trusted`` / ``trusted-tokens`` surveys, a valid
      token must be supplied as ``access_token`` (query/form) or ``tt``
      (form) parameter, unless the caller has the ``cmf.ModifyPortalContent``
      permission.
    * **Authenticity token**: when enabled globally (default), submissions
      must carry the token issued by ``@@viewer`` in the ``auth_token`` form
      field. Direct DOM embed submissions bypass both checks when they
      present a valid ``Origin`` header and ``X-Embed-Token``.

Submission & form API
=====================

``@@get-form-json``
    GET · ``zope2.View`` · returns the latest form schema as JSON — the data
    the SurveyJS renderer needs. Enforces the access mode (see above).

    Example::

        curl "https://example.org/demo/my-survey/@@get-form-json"

``@@save-poll``
    POST · ``zope2.View`` · stores a survey submission. The form field
    ``pollResult`` carries the submission payload as a JSON string. Enforces
    access mode, authenticity token (``auth_token`` field) and, when
    enabled, the external server-side validation.

    Example::

        curl -X POST "https://example.org/demo/my-survey/@@save-poll" \
             --data-urlencode 'auth_token=…' \
             --data-urlencode 'pollResult={"question1":"answer"}'

    Errors

    * ``400`` — ``missing_poll_result``, ``invalid_payload``,
      ``invalid_json``, ``missing_form_schema``
    * ``403`` — ``invalid_origin``, ``invalid_token``,
      ``token_already_used``, ``feature_disabled`` (direct embed only)
    * ``413`` — ``request_too_large`` / ``json_too_large`` (payload exceeds
      the survey's "Max size payload" setting)

    Success response: ``{"isSuccess": true}``; when the ``store`` action is
    disabled the response additionally contains ``stored: false``.

``@@save-form-json``
    POST · ``zope2.View`` · saves the form JSON from the visual editor. Form
    field ``surveyText`` carries the complete SurveyJS form schema as a JSON
    string. Creates a new (unlocked) form version. Response:
    ``{"isSuccess": true}``.

Results API
===========

``@@get-polls-json``
    GET · ``cmf.ModifyPortalContent`` · all stored submissions, each with
    metadata (``poll_id``, ``created``, ``user``, ``form_version``) and the
    result payload.

``@@get-polls-json2``
    GET · ``cmf.ModifyPortalContent`` · like ``@@get-polls-json``, but
    returns only the submission payloads (without metadata).

``@@view-result-json``
    GET · ``cmf.ModifyPortalContent`` · JSON of a single submission.
    Parameter: ``poll_id``. Returns ``{"error": "Poll result not found"}``
    for unknown ids.

``@@results-data``
    GET · ``cmf.ModifyPortalContent`` · paginated, filterable results
    payload for the results table UI (Tabulator).

``@@delete-results``
    POST · ``cmf.ModifyPortalContent`` (Manager-only check inside) · deletes
    one or more submissions. Accepts a JSON body ``{"poll_ids": [...]}`` or
    the form fields ``poll_id`` / ``poll_ids``. Response: the deletion
    result as JSON.

``@@clear-results``
    POST · ``cmf.ModifyPortalContent`` · clears **all** stored submissions
    of the survey, then redirects to the survey view.

Download endpoints
==================

All download endpoints answer with a ``Content-Disposition: attachment``
header and a descriptive filename.

``@@download-form-json``
    GET · ``cmf.ModifyPortalContent`` · current form schema as
    ``<id>-survey-form.json``.

``@@download-polls-json``
    GET · ``cmf.ModifyPortalContent`` · all submissions (with metadata) as
    ``<id>-survey-data.json``. Optional date-range filters ``from`` /
    ``to`` (flexible date parsing, e.g. ``2026-08-01``).

``@@download-polls-csv``
    GET · ``cmf.ModifyPortalContent`` · all submissions as CSV (same
    ``from``/``to`` date filters). Columns: ``poll_id``, ``user``,
    ``created``, ``form_version`` followed by one column per discovered
    answer field.

``@@download-result``
    GET · ``cmf.ModifyPortalContent`` · a single submission in a selected
    export format. Parameters: ``poll_id`` and ``format`` (``text``, ``md``,
    ``html``, ``pdf``, ``csv``, ``xlsx``, ``xml``, ``docx``, ``json``).

``@@mail-result``
    POST · ``cmf.ModifyPortalContent`` · e-mails a single submission in the
    selected format. Parameters: ``poll_id`` and ``format``.

``@@post-result``
    POST · ``cmf.ModifyPortalContent`` · forwards a single submission to the
    survey's configured POST endpoint. Parameter: ``poll_id``.

Form version API
================

Form versions are snapshots of the survey schema; the latest version is the
active form. All endpoints require ``cmf.ModifyPortalContent``.

``@@view-version-json``
    GET · JSON of a specific version. Parameter: ``version_id``.

``@@download-version``
    GET · download a specific version as ``survey-form-<id8>.json``.
    Parameter: ``version_id``.

``@@upload-version``
    POST · imports a JSON file as a new version. File field: ``json_file``.
    Redirects to ``@@form-versions``.

``@@restore-version``
    POST · creates a **new** version from the content of an older version
    (the old version itself is preserved). Parameter: ``version_id``.
    Redirects to ``@@form-versions``.

``@@toggle-version-lock``
    POST · toggles the locked state of a version (locked versions cannot be
    edited). Parameter: ``version_id``. Redirects to ``@@form-versions``.

``@@delete-version``
    POST · deletes a version. Parameter: ``version_id``. Redirects to
    ``@@form-versions``.

``@@create-template-from-version``
    POST · creates a survey template from a version. Parameter:
    ``version_id``.

AI generator API
================

All AI endpoints require ``cmf.ModifyPortalContent``. They operate on the
survey's **temporary form storage** (the AI working copy), which is a
separate buffer next to the version history.

``@@ai-upload``
    POST · converts an uploaded document into a form draft. File field:
    ``document_file`` (e.g. a PDF). Stores the draft in the temp storage and
    redirects to ``@@ai``.

``@@ai-store-temp-version``
    POST · promotes the temp form draft to a real form version. Redirects to
    ``@@ai``.

``@@ai-copy-latest-to-temp``
    POST · copies the latest form version into the temp storage (starting
    point for AI edits). Redirects to ``@@ai``.

``@@ai-clear-temp-storage``
    POST · discards the temp form draft and its history. Redirects to
    ``@@ai``.

``@@ai-chat-refine``
    POST · chat-based refinement of the temp form. Form field:
    ``chat_prompt`` (the instruction). The result replaces the temp draft;
    redirects to ``@@ai``.

``@@ai-restore-history-step``
    POST · restores a previous temp-draft state. Parameter:
    ``history_index`` (0-based). Redirects to ``@@ai``.

``@@ai-delete-history-step``
    POST · deletes a temp-draft history entry. Parameter: ``history_index``.
    Redirects to ``@@ai``.

``@@ai-test``
    POST · site root · ``cmf.ManagePortal`` · connection test for the
    configured AI provider (used by the forms-settings AI panels). Sends a
    small probe request to the configured model and returns the result as
    JSON.

Chatbot API
===========

``@@chat-api``
    POST · ``cmf.ModifyPortalContent`` · the chatbot conversation endpoint.
    Accepts a JSON body with the keys ``message``, ``current_view``,
    ``survey_title``, ``user_role``, ``stream``, ``history``,
    ``survey_json``, ``top_k`` (form-encoded keys also accepted). Returns
    the chatbot answer as JSON; ``stream: true`` enables streaming.

``@@chatbot-stats``
    GET · ``cmf.ModifyPortalContent`` · chatbot usage statistics.

``@@chatbot-mgmt``
    POST · ``cmf.ManagePortal`` · chatbot management actions.

``@@chatbot-index-local``
    POST · ``cmf.ManagePortal`` · (re)builds the local documentation index
    used by the chatbot.

``@@chatbot-index-remote``
    POST · ``cmf.ManagePortal`` · fetches the remote documentation and
    rebuilds the index.

``@@chatbot-reset``
    POST · ``cmf.ManagePortal`` · resets the chatbot state/index.

Fillable PDF API
================

``@@fillable-pdf-upload``
    POST · ``cmf.ModifyPortalContent`` · stores a fillable PDF template.
    File field: ``pdf_file``. Redirects to ``@@fillable-pdf``.

``@@fillable-pdf-download``
    GET · ``cmf.ModifyPortalContent`` · downloads the stored PDF template.

``@@fillable-pdf-delete``
    POST · ``cmf.ModifyPortalContent`` · removes the PDF template. Redirects
    to ``@@fillable-pdf``.

``@@fillable-pdf-fill``
    POST · ``zope2.View`` · fills the PDF template with submitted form data
    (request form fields) and returns the filled PDF as a download. Requires
    PyMuPDF; returns an error message when no template is configured.

Access tokens
=============

``@@trusted-access-token``
    POST · ``cmf.ModifyPortalContent`` · issues a trusted access token for
    this survey. Response::

        {
          "isSuccess": true,
          "token": "…",
          "url": "https://example.org/demo/my-survey/@@viewer?access_token=…",
          "expires_at": "…"
        }

    The token is bound to the current form version and expires after the
    survey's "Trusted access token TTL" setting. Single-use tokens
    (``trusted-tokens`` access mode) are consumed by the first successful
    submission.

Direct DOM embedding API
========================

``@@embed-config``
    GET · ``zope2.View`` · public configuration JSON for the embed loader
    (used by external pages to obtain an embed token).

``@@embed-token``
    POST · ``cmf.ModifyPortalContent`` · issues a short-lived embed token
    for a specific origin. The token is single-use for submissions
    (replay is rejected) and expires after the survey's "Embed token TTL".

``@@embed-loader``
    GET · ``zope2.View`` · the JavaScript loader that external pages include
    to embed the survey via Direct DOM.

``@@embed-surveyjs``
    GET · ``zope2.View`` (any context) · serves the SurveyJS assets for
    embedded surveys.

Template endpoints
==================

``@@get-template-json``
    GET · ``zope2.View`` · returns the form JSON of a survey **template**
    (called on the template object). Used to start a new survey from a
    template.
