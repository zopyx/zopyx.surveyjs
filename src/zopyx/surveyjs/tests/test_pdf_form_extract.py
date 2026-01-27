from __future__ import annotations

import json
import os
import shutil
import unittest
from unittest import mock

from zopyx.surveyjs.pdf_form_extract import PDFFormExtractor


class PDFFormExtractorTests(unittest.TestCase):
    def test_check_pdfcpu_raises_when_missing(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                PDFFormExtractor.check_pdfcpu()
        self.assertEqual(str(ctx.exception), "pdfcpu binary not found in PATH")

    def test_check_pdfcpu_returns_path(self) -> None:
        pdfcpu_path = shutil.which("pdfcpu")
        if not pdfcpu_path:
            raise unittest.SkipTest("pdfcpu is not available in PATH")
        self.assertEqual(PDFFormExtractor.check_pdfcpu(), pdfcpu_path)

    def test_extract_returns_json_string(self) -> None:
        if not shutil.which("pdfcpu"):
            raise unittest.SkipTest("pdfcpu is not available in PATH")
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
        )
        sample_pdf = os.path.join(repo_root, "FilledForm.pdf")
        extractor = PDFFormExtractor(sample_pdf)
        json_payload = extractor.extract()
        self.assertIsInstance(json_payload, str)
        self.assertTrue(json_payload.strip())
        parsed = json.loads(json_payload)
        self.assertIsInstance(parsed, (dict, list))
