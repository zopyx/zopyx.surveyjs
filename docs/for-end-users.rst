=============
For End Users
=============

This track is for people who build and run surveys day to day using the UI.

Quick start
===========

1. **Create a survey** — in the forms overview use the add action and
   follow the creation wizard (``@@survey-add``): give the survey a title,
   choose the languages and the basic settings. The survey appears in the
   forms overview (``@@pfs``).

   .. image:: _static/screenshots/psf-survey-overview.png
      :align: center
      :alt: Forms overview listing the surveys

2. **Design the form** — open the survey and start the **editor**
   (``@@editor``). The SurveyJS Creator lets you drag question types onto
   the page, configure validation, layout and logic, and preview the result
   — everything is saved as JSON automatically.

   .. image:: _static/screenshots/survey-editor.png
      :align: center
      :alt: SurveyJS Creator editor

3. **Configure the survey** — in the survey's edit form set the actions
   (store, mail, notifications, POST — see :doc:`actions`), the form
   settings (validation, payload limit, access mode) and, if needed, the
   mail settings and embedding options (see :doc:`survey-options`).

4. **Publish and share** — make the survey visible to its audience and
   distribute the survey URL (``@@viewer``). For restricted surveys,
   generate trusted access links (see :doc:`security`); for external
   sites, see :doc:`embedding`.

   .. image:: _static/screenshots/survey-viewer.png
      :align: center
      :alt: Public survey viewer

5. **Review the results** — open ``@@results`` to search, inspect and
   export the submissions; use the dashboard for an overview
   (see :doc:`exports`).

   .. image:: _static/screenshots/survey-results.png
      :align: center
      :alt: Results listing

Everyday tasks
==============

* **Generate a form with AI** — describe the form in natural language in
  ``@@ai``, refine the draft in a chat loop and save it as a form version
  (see :doc:`ai`).

  .. image:: _static/screenshots/survey-ai-generator.png
     :align: center
     :alt: AI generator

* **Manage form versions** — every save creates a new version; preview,
  restore, lock or download versions in ``@@form-versions``.
* **Ask the chatbot** — questions about SurveyJS and the current survey are
  answered by ``@@chatbot`` (see :doc:`chatbot`).
* **Start from a template** — reuse a prepared form structure
  (see :doc:`templates`).

Reference
=========

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   overview

.. toctree::
   :maxdepth: 2
   :caption: Everyday Tasks

   usage
   actions
   views
   exports
   validation
   ai
   templates
