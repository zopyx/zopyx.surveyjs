import base64
import unicodedata
import unittest

from zopyx.surveyjs.data_validation.data_validation import (
    DEFAULT_MAX_FILE_BYTES,
    SubmissionValidationError,
    validate_and_normalize_submission,
)


TEXT_FORM = {
    "pages": [{"elements": [{"type": "text", "name": "q1"}]}],
}

FILE_FORM = {
    "pages": [
        {
            "elements": [
                {"type": "file", "name": "upload"},
                {"type": "text", "name": "comment"},
            ]
        }
    ],
}


def data_url(mime: str, content: bytes = b"payload") -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime};base64,{encoded}"


class SubmissionValidationTests(unittest.TestCase):
    def test_accepts_json_object_with_known_text_field(self) -> None:
        result = validate_and_normalize_submission(TEXT_FORM, {"q1": "answer"})
        self.assertEqual(result, {"q1": "answer"})

    def test_returns_a_copy_instead_of_mutating_input(self) -> None:
        payload = {"q1": {"nested": ["value"]}}
        result = validate_and_normalize_submission(TEXT_FORM, payload)
        self.assertIsNot(result, payload)
        self.assertIsNot(result["q1"], payload["q1"])

    def test_rejects_non_object_payload(self) -> None:
        for payload in (None, [], "text", 1):
            with self.subTest(payload=payload):
                with self.assertRaises(SubmissionValidationError) as context:
                    validate_and_normalize_submission(TEXT_FORM, payload)
                self.assertEqual(context.exception.code, "payload_not_object")

    def test_rejects_unknown_top_level_field(self) -> None:
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(TEXT_FORM, {"unknown": "value"})
        self.assertEqual(context.exception.code, "unknown_field")

    def test_rejects_nul_and_control_characters(self) -> None:
        for value in ("bad\x00value", "bad\x1fvalue", "bad\x0bvalue"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(SubmissionValidationError) as context:
                    validate_and_normalize_submission(TEXT_FORM, {"q1": value})
                self.assertEqual(context.exception.code, "control_character")

    def test_rejects_dangerous_url_scheme_in_any_value(self) -> None:
        for value in (
            "javascript:alert(1)",
            "vbscript:msgbox(1)",
            "data:text/html;base64,PHNjcmlwdD4=",
        ):
            with self.subTest(value=value):
                with self.assertRaises(SubmissionValidationError) as context:
                    validate_and_normalize_submission(TEXT_FORM, {"q1": value})
                self.assertEqual(context.exception.code, "dangerous_url")

    def test_rejects_script_markup_in_submission_values(self) -> None:
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(
                TEXT_FORM, {"q1": '<script>alert("x")</script>'}
            )
        self.assertEqual(context.exception.code, "html_markup")

    def test_accepts_safe_text_containing_angle_brackets(self) -> None:
        result = validate_and_normalize_submission(TEXT_FORM, {"q1": "2 < 3"})
        self.assertEqual(result["q1"], "2 < 3")

    def test_rejects_dangerous_markup_tags_and_event_handlers(self) -> None:
        for value in (
            "<img src=x onerror=alert(1)>",
            "<svg onload=alert(1)>",
            "<iframe src=x>",
            "<object data=x>",
            "<embed src=x>",
        ):
            with self.subTest(value=value):
                with self.assertRaises(SubmissionValidationError) as context:
                    validate_and_normalize_submission(TEXT_FORM, {"q1": value})
                self.assertEqual(context.exception.code, "html_markup")

    def test_accepts_valid_png_file_and_canonicalizes_it(self) -> None:
        png = b"\x89PNG\r\n\x1a\n" + b"payload"
        payload = {
            "upload": [
                {
                    "name": "photo.png",
                    "type": "image/png",
                    "content": data_url("image/png", png),
                }
            ]
        }
        result = validate_and_normalize_submission(FILE_FORM, payload)
        self.assertEqual(result["upload"][0]["name"], "photo.png")
        self.assertEqual(result["upload"][0]["type"], "image/png")
        self.assertEqual(result["upload"][0]["content"], data_url("image/png", png))

    def test_rejects_file_field_with_wrong_shape(self) -> None:
        for value in ("text", {}, ["text"], [{"name": "x.png"}]):
            with self.subTest(value=value):
                with self.assertRaises(SubmissionValidationError) as context:
                    validate_and_normalize_submission(FILE_FORM, {"upload": value})
                self.assertEqual(context.exception.code, "invalid_file")

    def test_rejects_non_data_file_content(self) -> None:
        payload = {
            "upload": [
                {"name": "photo.png", "type": "image/png", "content": "https://x"}
            ]
        }
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(FILE_FORM, payload)
        self.assertEqual(context.exception.code, "invalid_data_url")

    def test_rejects_svg_file(self) -> None:
        payload = {
            "upload": [
                {
                    "name": "evil.svg",
                    "type": "image/svg+xml",
                    "content": data_url("image/svg+xml", b"<svg />"),
                }
            ]
        }
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(FILE_FORM, payload)
        self.assertEqual(context.exception.code, "disallowed_mime_type")

    def test_rejects_attribute_injection_in_data_url(self) -> None:
        payload = {
            "upload": [
                {
                    "name": "photo.png",
                    "type": 'image/png" onerror="alert(1)',
                    "content": 'data:image/png;base64,AAAA" onerror="alert(1)',
                }
            ]
        }
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(FILE_FORM, payload)
        self.assertEqual(context.exception.code, "disallowed_mime_type")

    def test_rejects_invalid_base64(self) -> None:
        payload = {
            "upload": [
                {
                    "name": "photo.png",
                    "type": "image/png",
                    "content": "data:image/png;base64,A",
                }
            ]
        }
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(FILE_FORM, payload)
        self.assertEqual(context.exception.code, "invalid_base64")

    def test_rejects_image_with_mismatched_magic_bytes(self) -> None:
        payload = {
            "upload": [
                {
                    "name": "photo.png",
                    "type": "image/png",
                    "content": data_url("image/png", b"not-a-png"),
                }
            ]
        }
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(FILE_FORM, payload)
        self.assertEqual(context.exception.code, "invalid_file_content")

    def test_rejects_unsafe_filename(self) -> None:
        payload = {
            "upload": [
                {
                    "name": 'x" onerror="alert(1).png',
                    "type": "image/png",
                    "content": data_url(
                        "image/png", b"\x89PNG\r\n\x1a\ncontent"
                    ),
                }
            ]
        }
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(FILE_FORM, payload)
        self.assertEqual(context.exception.code, "unsafe_filename")

    def test_rejects_oversized_file(self) -> None:
        content = b"\x89PNG\r\n\x1a\n" + b"x" * DEFAULT_MAX_FILE_BYTES
        payload = {
            "upload": [
                {
                    "name": "large.png",
                    "type": "image/png",
                    "content": data_url("image/png", content),
                }
            ]
        }
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(FILE_FORM, payload)
        self.assertEqual(context.exception.code, "file_too_large")

    def test_rejects_too_many_files(self) -> None:
        payload = {
            "upload": [
                {
                    "name": f"photo-{index}.png",
                    "type": "image/png",
                    "content": data_url(
                        "image/png", b"\x89PNG\r\n\x1a\ncontent"
                    ),
                }
                for index in range(11)
            ]
        }
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(FILE_FORM, payload, max_files=10)
        self.assertEqual(context.exception.code, "too_many_files")

    def test_accepts_non_image_file_with_allowed_mime_type(self) -> None:
        payload = {
            "upload": [
                {
                    "name": "document.pdf",
                    "type": "application/pdf",
                    "content": data_url("application/pdf", b"%PDF-test"),
                }
            ]
        }
        result = validate_and_normalize_submission(FILE_FORM, payload)
        self.assertEqual(result["upload"][0]["type"], "application/pdf")

    def test_rejects_file_with_mismatched_declared_type(self) -> None:
        payload = {
            "upload": [
                {
                    "name": "photo.png",
                    "type": "image/jpeg",
                    "content": data_url(
                        "image/png", b"\x89PNG\r\n\x1a\ncontent"
                    ),
                }
            ]
        }
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(FILE_FORM, payload)
        self.assertEqual(context.exception.code, "mime_mismatch")

    def test_collects_nested_schema_file_fields(self) -> None:
        form = {
            "pages": [
                {
                    "elements": [
                        {
                            "type": "panel",
                            "name": "panel",
                            "elements": [{"type": "file", "name": "upload"}],
                        }
                    ]
                }
            ]
        }
        payload = {
            "upload": [
                {
                    "name": "photo.png",
                    "type": "image/png",
                    "content": data_url(
                        "image/png", b"\x89PNG\r\n\x1a\ncontent"
                    ),
                }
            ]
        }
        result = validate_and_normalize_submission(form, payload)
        self.assertIn("upload", result)

    def test_missing_required_check_is_disabled_by_default(self) -> None:
        form = {"pages": [{"elements": [{"type": "text", "name": "q1", "isRequired": True}]}]}
        result = validate_and_normalize_submission(form, {})
        self.assertEqual(result, {})

    def test_rejects_missing_required_text_field_when_enabled(self) -> None:
        form = {"pages": [{"elements": [{"type": "text", "name": "q1", "isRequired": True}]}]}
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(form, {}, enforce_required_fields=True)
        self.assertEqual(context.exception.code, "missing_required")
        self.assertEqual(context.exception.field, "q1")

    def test_rejects_empty_required_values_but_accepts_false(self) -> None:
        form = {
            "pages": [{"elements": [
                {"type": "text", "name": "q1", "isRequired": True},
                {"type": "boolean", "name": "q2", "isRequired": True},
            ]}]
        }
        for value in ("", [], None):
            with self.subTest(value=value):
                with self.assertRaises(SubmissionValidationError):
                    validate_and_normalize_submission(
                        form,
                        {"q1": value, "q2": False},
                        enforce_required_fields=True,
                    )
        result = validate_and_normalize_submission(form, {"q1": "answer", "q2": False})
        self.assertFalse(result["q2"])

    def test_optional_field_may_be_omitted(self) -> None:
        result = validate_and_normalize_submission(TEXT_FORM, {})
        self.assertEqual(result, {})

    def test_accepts_default_and_custom_comment_prefix(self) -> None:
        result = validate_and_normalize_submission(
            TEXT_FORM, {"q1": "answer", "q1-Comment": "note"}
        )
        self.assertEqual(result["q1-Comment"], "note")
        custom = {**TEXT_FORM, "commentPrefix": "_comment"}
        result = validate_and_normalize_submission(
            custom, {"q1": "answer", "q1_comment": "note"}
        )
        self.assertEqual(result["q1_comment"], "note")

    def test_rejects_orphan_and_unsafe_comments(self) -> None:
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(TEXT_FORM, {"nosuch-Comment": "note"})
        self.assertEqual(context.exception.code, "unknown_field")
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(
                TEXT_FORM, {"q1": "answer", "q1-Comment": "<script>x</script>"}
            )
        self.assertEqual(context.exception.code, "html_markup")

    def test_enforces_comment_length(self) -> None:
        form = {**TEXT_FORM, "maxCommentLength": 3}
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(form, {"q1": "answer", "q1-Comment": "long"})
        self.assertEqual(context.exception.code, "comment_too_long")

    def test_rejects_octet_stream(self) -> None:
        payload = {"upload": [{
            "name": "x.bin", "type": "application/octet-stream",
            "content": data_url("application/octet-stream", b"binary"),
        }]}
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(FILE_FORM, payload)
        self.assertEqual(context.exception.code, "disallowed_mime_type")

    def test_normalizes_nfd_unicode_filename_to_nfc(self) -> None:
        nfd_name = unicodedata.normalize("NFD", "Müller.pdf")
        payload = {"upload": [{
            "name": nfd_name,
            "type": "application/pdf",
            "content": data_url("application/pdf", b"%PDF-1.7"),
        }]}
        result = validate_and_normalize_submission(FILE_FORM, payload)
        self.assertEqual(result["upload"][0]["name"], "Müller.pdf")
        self.assertEqual(
            result["upload"][0]["name"], unicodedata.normalize("NFC", nfd_name)
        )

    def test_rejects_filename_with_only_combining_marks(self) -> None:
        payload = {"upload": [{
            "name": "\u0308.pdf",
            "type": "application/pdf",
            "content": data_url("application/pdf", b"%PDF-1.7"),
        }]}
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(FILE_FORM, payload)
        self.assertEqual(context.exception.code, "unsafe_filename")

    def test_question_comment_limit_overrides_schema_limit(self) -> None:
        form = {
            **TEXT_FORM,
            "maxCommentLength": 10,
            "pages": [{"elements": [{
                "type": "text", "name": "q1", "maxCommentLength": 3,
            }]}],
        }
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(form, {"q1": "answer", "q1-Comment": "long"})
        self.assertEqual(context.exception.code, "comment_too_long")

    def test_rejects_boolean_comment_length(self) -> None:
        form = {**TEXT_FORM, "maxCommentLength": True}
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(form, {"q1": "answer", "q1-Comment": "x"})
        self.assertEqual(context.exception.code, "invalid_comment_length")

    def test_checks_magic_bytes_for_signed_non_images(self) -> None:
        signed = {
            "application/msword": ("x.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1payload"),
            "application/pdf": ("x.pdf", b"%PDF-1.7"),
            "application/rtf": ("x.rtf", b"{\\rtf1"),
            "application/vnd.ms-excel": ("x.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1payload"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (
                "x.xlsx", b"PK\x03\x04payload"
            ),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
                "x.docx", b"PK\x03\x04payload"
            ),
            "application/zip": ("x.zip", b"PK\x03\x04payload"),
        }
        for mime, (name, content) in signed.items():
            with self.subTest(mime=mime):
                result = validate_and_normalize_submission(
                    FILE_FORM,
                    {"upload": [{"name": name, "type": mime, "content": data_url(mime, content)}]},
                )
                self.assertEqual(result["upload"][0]["type"], mime)
                with self.assertRaises(SubmissionValidationError) as context:
                    validate_and_normalize_submission(
                        FILE_FORM,
                        {"upload": [{"name": name, "type": mime, "content": data_url(mime, b"spoof")} ]},
                    )
                self.assertEqual(context.exception.code, "invalid_file_content")

    def test_rejects_truncated_png_signatures(self) -> None:
        for length in range(1, 8):
            with self.subTest(length=length):
                payload = {
                    "upload": [{
                        "name": "x.png",
                        "type": "image/png",
                        "content": data_url("image/png", b"\x89PNG\r\n\x1a\n"[:length]),
                    }]
                }
                with self.assertRaises(SubmissionValidationError) as context:
                    validate_and_normalize_submission(FILE_FORM, payload)
                self.assertEqual(context.exception.code, "invalid_file_content")

    def test_rejects_url_whitespace_bypass_and_allows_safe_lookalike(self) -> None:
        for value in (" javascript:alert(1)", "\tjavascript:alert(1)", "java\nscript:alert(1)", "VBSCRIPT:msgbox(1)"):
            with self.subTest(value=value):
                with self.assertRaises(SubmissionValidationError) as context:
                    validate_and_normalize_submission(TEXT_FORM, {"q1": value})
                self.assertEqual(context.exception.code, "dangerous_url")
        result = validate_and_normalize_submission(TEXT_FORM, {"q1": "javascript is a language"})
        self.assertEqual(result["q1"], "javascript is a language")

    def test_accepts_unicode_filenames_and_rejects_paths(self) -> None:
        content = data_url("application/pdf", b"%PDF-test")
        for name in ("Müller.pdf", "文件.pdf", "résumé (final).pdf"):
            with self.subTest(name=name):
                result = validate_and_normalize_submission(
                    FILE_FORM, {"upload": [{"name": name, "type": "application/pdf", "content": content}]}
                )
                self.assertEqual(result["upload"][0]["name"], name)
        for name in ("../etc/passwd", 'x"onerror=.pdf', "a/b.pdf", "a\x00.pdf", "a" * 129 + ".pdf"):
            with self.subTest(name=name):
                with self.assertRaises(SubmissionValidationError) as context:
                    validate_and_normalize_submission(
                        FILE_FORM, {"upload": [{"name": name, "type": "application/pdf", "content": content}]}
                    )
                self.assertEqual(context.exception.code, "unsafe_filename")

    def test_rejects_data_urls_in_generic_fields_except_safe_signature_images(self) -> None:
        with self.assertRaises(SubmissionValidationError) as context:
            validate_and_normalize_submission(TEXT_FORM, {"q1": "data:image/svg+xml;base64,PHN2Zz4="})
        self.assertEqual(context.exception.code, "dangerous_url")
        safe = data_url("image/png", b"signature")
        result = validate_and_normalize_submission(TEXT_FORM, {"q1": safe})
        self.assertEqual(result["q1"], safe)

    def test_accepts_forward_compatible_file_metadata(self) -> None:
        result = validate_and_normalize_submission(
            FILE_FORM,
            {"upload": [{"name": "x.pdf", "type": "application/pdf", "content": data_url("application/pdf", b"%PDF-test"), "fileSize": 9}]},
        )
        self.assertNotIn("fileSize", result["upload"][0])


if __name__ == "__main__":
    unittest.main()
