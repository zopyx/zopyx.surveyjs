===========
Development
===========

Developer notes
===============

- ``DEVELOP.rst`` contains developer workflow notes for buildout setups.
- The validator CLI and build targets are documented in
  ``docs/data-validation-cli.rst`` and ``docs/installation.rst``.
- Validation behaviour in the submission pipeline: ``docs/validation.rst``.
- Demo site setup and localization notes are maintained in this file.

Adding a new demo language (``scripts/init_plone.py``)
======================================================

To add a new language to the demo initializer, update both the init script and
the assets under ``scripts/forms``. The process is mostly copy-and-translate,
but the IDs and links must stay aligned.

1. Update language registry and trees
-------------------------------------

- ``configure_site_languages()``: add the language code to
  ``plone.available_languages`` and adjust the log message.
- ``language_trees``: add ``"<lang>": {"root": "...", "demos": "..."}``.

2. Extend welcome-page dictionaries
-----------------------------------

Add the language key to each dictionary (keys must match the language code):

- ``WELCOME_BANNERS``
- ``WELCOME_YOUTUBE``
- ``WELCOME_LINKS``
- ``WELCOME_HEADINGS``
- ``WELCOME_POWERED_BY_HEADINGS``
- ``WELCOME_DEMOS`` (labels + hrefs)
- ``WELCOME_TITLES``

Important: The demo links in ``WELCOME_DEMOS`` must match the IDs created later
in the script (e.g. ``<lang>/demos/event-registration-<lang>``).

3. Add translated form assets
-----------------------------

Create or update these files in ``scripts/forms``:

- ``welcome_<lang>.html``
- ``mental_health_intro_<lang>.html``
- ``full_demo_intro_<lang>.html``
- ``event_registration_<lang>.json``
- ``event_rsvp_<lang>.json``
- ``mental_health_<lang>.json``
- ``full_demo_<lang>.json``
- ``food_feedback_<lang>.json``
- ``order_form_<lang>.json``

Notes:

- JSON files must be valid JSON (no HTML comments).
- Set ``\"locale\": \"<lang>\"`` in each JSON form.
- Keep element ``name`` values unchanged; only translate user-facing strings.

4. Seed the new language demos
------------------------------

Add a language-specific demo block next to the existing language blocks:

- Load each ``*_ <lang>.json`` file via ``load_form_definition``.
- Call ``set_form_language`` and ``set_form_locale``.
- Load intro HTML for mental health and full demo.
- Call ``create_demo_survey`` with localized titles/descriptions and
  ``container=demos_by_language[\"<lang>\"]``.

5. Run the initializer
----------------------

Recreate the demo site to verify:

``bin/instance run scripts/init_plone.py``

Validate:

- Welcome page renders with the new language.
- All demo links resolve.
- Surveys show localized labels and button text.

Testing
=======

- The Plone tests run through the buildout test runner:
  ``bin/test -s zopyx.surveyjs`` (or ``make test``, which also runs the
  converter unit tests under coverage).
- The data-validation package has its own pytest suite under
  ``src/zopyx/surveyjs/data_validation/tests``.
