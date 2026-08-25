import base64
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
        self.assertIn(
            context.exception.code,
            {"invalid_file", "invalid_data_url", "disallowed_mime_type"},
        )

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
        self.assertEqual(context.exception.code, "invalid_image_content")

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


if __name__ == "__main__":
    unittest.main()
