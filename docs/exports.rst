====================
Results and Exports
====================

Results are available via ``@@results2`` when the ``store`` action is enabled.
Each submission can be inspected, exported, emailed, or POSTed to an endpoint.

Export formats
==============

Supported formats include:

- Text (``.txt``)
- Markdown (``.md``)
- HTML (``.html``)
- PDF (``.pdf``)
- CSV (``.csv``)
- Excel (``.xlsx``)
- XML (``.xml``)
- Word (``.docx``)
- JSON (``.json``)

Exports can be downloaded for a single submission or for all submissions
(using JSON or CSV bulk export).

Mail exports
============

When the ``mail`` action is enabled:

- Attachments are generated in the selected formats.
- If no formats are selected, PDF is used as a default.
- The mail body supports ``{created}``, ``{creator}``, ``{formats}``.

Result detail view
==================

The result detail view (``@@result-detail``) renders a human-readable view of a
submission using the form schema to map labels to values.
