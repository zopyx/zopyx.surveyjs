Fillable PDF
============

The fillable PDF screen (``@@fillable-pdf``) manages the PDF-based
workflow of a survey: upload a fillable PDF template, fill it out in the
browser and download the completed PDF, or map the PDF's form fields to
the survey's JSON form. It is the bridge between paper-style PDF forms and
the online survey system.

.. image:: _static/screenshots/survey-fillable-pdf.png
   :align: center
   :alt: Fillable PDF screen

How to get here
---------------

* From the survey landing page, click **Fillable PDF**.
* Directly at ``/my-survey/@@fillable-pdf``.
* The ``fillable-pdf`` feature must be enabled globally (default: on).
* The same feature is configured in the survey settings (PDF Form /
  Fillable PDF fields, see :doc:`ui-survey-settings`).

What you see
------------

The page is organized into sections; the ones after the first only appear
once a template has been uploaded.

**Fillable PDF Template** (always visible)

  * **Without a template** — an info box ("No PDF template has been
    uploaded yet.") and the upload form: choose a ``.pdf`` file and click
    **Upload PDF Template**.
  * **With a template** — an info card showing the **file name** with
    download (⬇) and delete (🗑) buttons, the file **size** in KB and the
    number of **fields** extracted from the PDF.

**Fill PDF Form** (with template)

  A form to fill the PDF fields directly in the browser:

  * Fields are grouped by **page** (Page 1, Page 2, …).
  * Each row shows the field **name** (code style), a **type badge**
    (textfield, checkbox, …) and a **required** marker where applicable.
  * Input controls match the field type: text input, checkbox, dropdown
    (with the PDF's options) or a signature placeholder (signature
    fields are filled via the UI workflow).
  * **Download Filled PDF** submits the values and returns the completed
    PDF — the survey data is merged into the template.

**Form Fields** (with template)

  A reference table per page: **#**, **Field Name**, **Type**, **Options**,
  **Default Value**, **Properties** (Read-only / Required badges) and
  **In Form** — a ✓/✗ indicator showing whether the PDF field exists in
  the survey's JSON form. Fields without a JSON counterpart are the ones
  to watch: they will not be filled from survey data automatically.

**JSON Form Properties** (with template)

  A table of the fields defined in the current JSON form (from the editor
  or AI generation) with their type and input type — the counterpart of
  the PDF field list, useful for checking the mapping between PDF and
  form.

What you can do
---------------

Upload a template
~~~~~~~~~~~~~~~~~

1. In the **Fillable PDF Template** section, select a fillable PDF and
   click **Upload PDF Template**.
2. The page reloads and shows the template info card, the fill form and
   the field tables.
3. Check the **In Form** column: fields the survey form does not know are
   marked with ✗. Either add matching questions to the form (editor or AI
   generator) or fill those fields manually in the fill form.

Fill and download a PDF
~~~~~~~~~~~~~~~~~~~~~~~

1. In **Fill PDF Form**, enter the values per page (text, checkboxes,
   dropdowns; signature fields are handled via the UI workflow).
2. Click **Download Filled PDF** — the completed PDF is downloaded.
3. The filled PDF can be submitted or distributed like any document; for
   surveys with the fillable-PDF workflow, the submission is processed
   like a normal survey submission (see :doc:`actions`).

Manage the template
~~~~~~~~~~~~~~~~~~~

* **Download** (⬇) — fetch the current template for backup or reuse.
* **Delete** (🗑) — remove the template (a confirmation dialog appears);
  the page then offers the upload form again.

Tips & notes
------------

* Only real **fillable PDFs** work — the file must contain form fields.
  If the "Form Fields" section shows no fields, the PDF is not fillable.
* The **In Form** indicator is the key to automation: fields that exist
  in the JSON form can be pre-filled from survey data; the others must be
  entered manually.
* The feature is separate from the PDF export of submissions: the PDF
  generator (``@@pdf-generator``) and the export converters render survey
  data as PDF documents — see :doc:`exports`.

Related documentation
---------------------

* :doc:`survey-options` — the PDF Form / Fillable PDF fields in the
  survey settings.
* :doc:`exports` — PDF generation and the export formats.
* :doc:`endpoints` — the fillable-PDF endpoints (upload, download,
  delete, fill).
