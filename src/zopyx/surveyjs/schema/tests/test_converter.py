import json
import tempfile
from pathlib import Path
from typing import Any, List
import unittest
from unittest.mock import patch

from conver_result import (
    Attachment,
    SurveyConverter,
    parse_formats,
    slugify,
)


class SurveyConverterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)
        self.data_path = self.base / "data.json"
        self.form_path = self.base / "form.json"
        self.output_dir = self.base / "output"

        # 1x1 PNG
        pixel_png = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="
        )
        payload = [
            {
                "poll_id": "test-123",
                "result": {
                    "fileq": [{"name": "pixel.png", "type": "image/png", "content": pixel_png}],
                    "textq": "hello world",
                },
            }
        ]
        schema = {
            "pages": [
                {
                    "name": "page1",
                    "elements": [
                        {"type": "file", "name": "fileq", "title": "Upload"},
                        {"type": "text", "name": "textq", "title": "Text"},
                    ],
                }
            ]
        }
        self.data_path.write_text(json.dumps(payload), encoding="utf-8")
        self.form_path.write_text(json.dumps(schema), encoding="utf-8")
        self.converter = SurveyConverter(self.data_path, self.form_path, self.output_dir)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_parse_formats_validation(self) -> None:
        self.assertEqual(parse_formats("all"), {"text", "md", "html", "pdf", "csv", "xlsx", "xml", "docx", "json"})
        self.assertEqual(parse_formats("text,md"), {"text", "md"})
        with self.assertRaises(ValueError):
            parse_formats("text,unknown")

    def test_slugify(self) -> None:
        self.assertEqual(slugify("Hello World!"), "Hello_World")
        self.assertEqual(slugify(""), "sample")

    def test_inline_html_images(self) -> None:
        att = Attachment("pixel.png", b"\x89PNG", "image/png", field_label="Upload")
        html = '<img src="pixel.png">'
        updated = self.converter.inline_html_images(html, [att])
        self.assertIn("data:image/png;base64", updated)
        self.assertNotIn("pixel.png", updated)

    def test_run_generates_requested_formats(self) -> None:
        formats = {"text", "md", "html", "csv", "xlsx"}
        self.converter.run(formats)

        expected_files: List[str] = [
            "test-123.txt",
            "test-123.md",
            "test-123.html",
            "test-123.csv",
            "test-123.xlsx",
            "pixel.png",
        ]
        for name in expected_files:
            self.assertTrue((self.output_dir / name).exists(), f"Missing expected file {name}")

        html_content = (self.output_dir / "test-123.html").read_text(encoding="utf-8")
        self.assertIn("data:image/png;base64", html_content)

    @patch.dict(
        "os.environ",
        {"SURVEYJS_DATA_JSON": "/tmp/custom-data.json", "SURVEYJS_FORM_JSON": "/tmp/custom-form.json"},
    )
    def test_parse_args_supports_env_defaults(self) -> None:
        args = parse_args([])
        self.assertEqual(args.data, "/tmp/custom-data.json")
        self.assertEqual(args.form, "/tmp/custom-form.json")

    @patch("conver_result.smtplib.SMTP")
    def test_run_can_email_generated_files(self, smtp_mock: Any) -> None:
        formats = {"text"}
        self.converter.run(formats, email_recipient="recipient@example.com")

        smtp_mock.assert_called_once_with("localhost", 25)
        smtp_client = smtp_mock.return_value.__enter__.return_value
        smtp_client.send_message.assert_called_once()
        sent_msg = smtp_client.send_message.call_args[0][0]
        self.assertEqual(sent_msg["To"], "recipient@example.com")
        attachments = list(sent_msg.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), "test-123.txt")

    @patch("conver_result.smtplib.SMTP")
    def test_send_email_uses_env_configuration(self, smtp_mock: Any) -> None:
        attachment = self.output_dir / "dummy.txt"
        attachment.parent.mkdir(parents=True, exist_ok=True)
        attachment.write_text("hello", encoding="utf-8")

        env_file = self.base / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "SURVEY_SMTP_HOST=mail.example.com",
                    "SURVEY_SMTP_PORT=2525",
                    "SURVEY_SMTP_USERNAME=user",
                    "SURVEY_SMTP_PASSWORD=pass",
                    "SURVEY_SMTP_STARTTLS=true",
                    "SURVEY_EMAIL_SENDER=sender@example.com",
                ]
            ),
            encoding="utf-8",
        )

        with patch.dict("os.environ", {"SURVEY_DOTENV_PATH": str(env_file)}, clear=True):
            self.converter.send_email("recipient@example.com", [attachment], poll_id="poll42")

        smtp_mock.assert_called_once_with("mail.example.com", 2525)
        smtp_client = smtp_mock.return_value.__enter__.return_value
        smtp_client.starttls.assert_called_once()
        smtp_client.login.assert_called_once_with("user", "pass")
        sent_msg = smtp_client.send_message.call_args[0][0]
        self.assertEqual(sent_msg["From"], "sender@example.com")
        self.assertEqual(sent_msg["To"], "recipient@example.com")
        attachments = list(sent_msg.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), "dummy.txt")

    def test_load_dotenv_populates_env_defaults(self) -> None:
        env_file = self.base / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "SURVEYJS_DATA_JSON=/tmp/from-dotenv-data.json",
                    "SURVEYJS_FORM_JSON=/tmp/from-dotenv-form.json",
                    "SURVEY_SMTP_HOST=mail.example.com",
                    "SURVEY_SMTP_PORT=2525",
                    "SURVEY_EMAIL_RECIPIENT=fromenv@example.com",
                ]
            ),
            encoding="utf-8",
        )
        with patch.dict("os.environ", {"SURVEY_DOTENV_PATH": str(env_file)}, clear=True):
            args = parse_args([])
            self.assertEqual(args.data, "/tmp/from-dotenv-data.json")
            self.assertEqual(args.form, "/tmp/from-dotenv-form.json")
            self.assertEqual(args.email, "fromenv@example.com")
            # Ensure SMTP related values are loaded as well
            self.assertEqual(os.environ["SURVEY_SMTP_HOST"], "mail.example.com")
            self.assertEqual(os.environ["SURVEY_SMTP_PORT"], "2525")


if __name__ == "__main__":
    unittest.main()
