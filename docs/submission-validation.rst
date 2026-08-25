Submission validation
=====================

New SurveyJS submissions are validated and normalized in
``zopyx.surveyjs.data_validation.data_validation`` before event dispatch,
storage, notification mail, or configured external POST processing.

Response contract
-----------------

Rejected submissions return JSON with::

    {"isSuccess": false, "error": "<code>", "field": "<optional-field>"}

The ``field`` member is omitted when the error is not associated with a
specific submission field. Validation failures are logged to the
``zopyx.surveyjs.audit`` logger with ``reason``, ``field``, ``origin`` and
``remote_addr`` fields.

Validation error codes
----------------------

``payload_not_object``
    The decoded submission is not a JSON object.
``invalid_form_schema``
    The form schema is not an object.
``unknown_field``
    The submission contains a field not present in the schema or a valid
    SurveyJS comment suffix.
``missing_required``
    A required question is absent or has an empty value. ``False`` and ``0``
    are valid values.
``invalid_comment_prefix``
    ``commentPrefix`` is missing, empty, or not a string.
``invalid_comment_length`` / ``comment_too_long``
    A comment limit is invalid or the submitted comment exceeds it.
``control_character``
    A string contains a disallowed control character.
``dangerous_url``
    A dangerous URL scheme or unsafe non-file data URL was submitted.
``html_markup``
    Dangerous markup tags or event-handler attributes were submitted.
``invalid_value``
    A generic value has an unsupported type.
``invalid_file`` / ``too_many_files``
    File data has the wrong shape or exceeds the configured file count.
``unsafe_filename``
    The filename contains unsafe characters, is too long, or cannot be safely
    normalized to NFC Unicode.
``disallowed_mime_type``
    The declared MIME type is not on the allowlist. SVG and
    ``application/octet-stream`` are rejected.
``invalid_data_url`` / ``mime_mismatch``
    File content is not a valid data URL or does not match its declared MIME
    type.
``invalid_base64`` / ``file_too_large``
    File data is not valid Base64 or exceeds the configured byte limit.
``invalid_file_content``
    Magic bytes or text encoding do not match the declared file type.

File handling
-------------

The validator accepts only the documented MIME allowlist, validates magic
bytes for binary formats, rejects SVG, canonicalizes Base64 data URLs, and
returns a new normalized object without mutating the request payload. Filenames
are Unicode-aware and normalized to NFC before storage.

The validator has no ``application/octet-stream`` escape hatch: the MIME type
is unconditionally rejected. Per-request file limits are derived from the
configured submission payload limit in ``save_poll``.
