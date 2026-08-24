=====
Views
=====

Views are the user-facing pages of the SurveyJS integration. They are
accessed by appending the view name to the object URL, e.g.
``/my-survey/@@viewer`` or ``/@@forms-settings`` for site-root views.

The machine-readable HTTP interfaces (JSON endpoints, downloads, submission
API) are documented separately in :doc:`endpoints`.

Survey rendering (public)
=========================

.. list-table::
   :header-rows: 1

   * - View
     - Permission
     - Purpose
   * - ``@@view-main``
     - ``zope2.View``
     - Landing page with navigation to the survey tools.
   * - ``@@viewer``
     - ``zope2.View``
     - Public survey rendering and submission (also available for survey
       templates). Enforces the survey's access mode (public / trusted) and
       issues the authenticity token used by ``@@save-poll``.
   * - ``@@viewer-embed``
     - ``zope2.View``
     - Embed-friendly viewer for iframes. Returns HTTP 403 when embedding is
       not allowed for this survey; otherwise removes ``X-Frame-Options`` and
       sets ``Content-Security-Policy: frame-ancestors *``.
   * - ``@@feature-disabled``
     - ``zope2.View``
     - Placeholder page shown when a requested feature is disabled via the
       global "Features enabled" setting.
   * - ``@@survey-actions``
     - ``zope2.View``
     - Renders the survey actions menu (used by the UI).
   * - ``@@survey-assets``
     - ``zope2.View``
     - Renders the JavaScript/CSS asset includes for the survey screens.
   * - ``@@pfs``
     - ``zope2.View``
     - Forms overview listing all surveys (folder view).
   * - ``@@root-redirect``
     - ``zope2.View``
     - Redirects the site root to the forms overview (site root).

Survey editing & management
===========================

.. list-table::
   :header-rows: 1

   * - View
     - Permission
     - Purpose
   * - ``@@survey-add``
     - ``zopyx.surveyjs.AddSurvey``
     - Survey creation wizard (form-based).
   * - ``@@editor``
     - ``cmf.ModifyPortalContent``
     - SurveyJS Creator visual editor.
   * - ``@@survey-metadata``
     - ``cmf.ModifyPortalContent``
     - Metadata editing screen for a survey.
   * - ``@@result-detail``
     - ``cmf.ModifyPortalContent``
     - Detailed HTML view of a single submission.
   * - ``@@form-versions``
     - ``cmf.ModifyPortalContent``
     - Form version management (preview, restore, download, lock, upload).
   * - ``@@embedded-demo``
     - ``cmf.ManagePortal``
     - Manager-only demo page showing iframe embedding.

Results & analytics
===================

.. list-table::
   :header-rows: 1

   * - View
     - Permission
     - Purpose
   * - ``@@results``
     - ``cmf.ModifyPortalContent``
     - Results listing with search, filtering and export controls.
   * - ``@@dashboard``
     - ``cmf.ModifyPortalContent``
     - Results dashboard with statistics.
   * - ``@@pdf-generator``
     - ``cmf.ManagePortal``
     - PDF export generator screen.
   * - ``@@survey-monitor``
     - ``cmf.ManagePortal``
     - Site-wide submission monitor (site root).

AI, chatbot & PDF
=================

.. list-table::
   :header-rows: 1

   * - View
     - Permission
     - Purpose
   * - ``@@ai``
     - ``cmf.ModifyPortalContent``
     - AI form generator UI (prompt, document upload, temp form history).
   * - ``@@chatbot``
     - ``cmf.ModifyPortalContent``
     - Chatbot UI for survey-related questions.
   * - ``@@fillable-pdf``
     - ``cmf.ModifyPortalContent``
     - Fillable PDF management screen (upload/download template, fill).
   * - ``@@embed-direct-demo``
     - ``cmf.ModifyPortalContent``
     - Demo page for Direct DOM embedding.

Administration
==============

.. list-table::
   :header-rows: 1

   * - View
     - Permission
     - Purpose
   * - ``@@forms-settings``
     - ``cmf.ManagePortal``
     - Global Forms control panel (site root).
   * - ``@@token-store``
     - ``cmf.ManagePortal``
     - Trusted access token management (generate, import, CSV export).
   * - ``@@llm-models``
     - ``cmf.ManagePortal``
     - Lists the available LLM models for the AI provider (site root).
   * - ``@@survey-overview``
     - ``cmf.ManagePortal``
     - Overview page listing surveys (management view).
   * - ``@@survey-templates-overview``
     - ``cmf.ManagePortal``
     - Overview page listing survey templates.
   * - ``@@demo-content``
     - ``cmf.ManagePortal``
     - Creates the demo content (site root).
