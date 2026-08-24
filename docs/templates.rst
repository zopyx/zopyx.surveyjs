=========
Templates
=========

Survey templates are prepared SurveyJS form definitions that can be reused
as the starting point for new surveys. A template is its own content type
(``SurveyTemplate``): a Survey item plus a required **Template JSON** field
holding the SurveyJS form definition.

Templates are useful whenever several surveys share the same structure —
a standardized intake form, an event registration, a feedback sheet — so
authors start from a reviewed baseline instead of rebuilding the form every
time.

Creating a template
===================

From a survey version
---------------------

In the version management screen (``@@form-versions``) of a survey,
**create-template-from-version** stores the form JSON of a selected version
as a new template. The form data is copied verbatim; later changes to the
survey's form do not affect the template.

Manually
--------

A template can also be created like any Plone content item of type
``SurveyTemplate``: add the item, paste a SurveyJS JSON definition into the
**Template JSON** field and save. The field is validated — it must contain a
valid JSON object — and the content type inherits the full survey schema, so
all per-survey settings (actions, mail, form settings) can be preconfigured
on the template.

Using a template
================

* **Viewer**: the template can be previewed like a survey (``@@viewer`` is
  registered for templates as well); ``@@get-template-json`` returns the
  template's form JSON.
* **Starting a new survey**: copy the template's form JSON into a new
  survey (via the editor or the AI workspace) and adapt it. The template
  itself stays untouched.
* **Overview**: ``@@survey-templates-overview`` (Manager) lists all
  templates.

Endpoints
=========

* ``@@get-template-json`` — GET · ``zope2.View`` · the template's form JSON
  (called on the template object).
* ``@@create-template-from-version`` — POST ·
  ``cmf.ModifyPortalContent`` · parameters ``version_id`` (the survey form
  version to copy) and ``template_title``; requires permission to add
  templates in the target location.

See :doc:`endpoints` for the full API reference.
