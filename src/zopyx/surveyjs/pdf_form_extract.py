from __future__ import annotations

"""PDF form extraction using the pdfcpu CLI.

This module wraps the pdfcpu command line tool to export PDF form data as JSON.
It provides a small OO wrapper plus a CLI entrypoint that writes the exported
JSON to a local file named ``out.json``.

Typical usage:

    extractor = PDFFormExtractor("/path/to/form.pdf")
    json_payload = extractor.extract()

CLI usage:

    python -m zopyx.surveyjs.pdf_form_extract /path/to/form.pdf
"""

import argparse
import os
import shutil
import subprocess
import tempfile


class PDFFormExtractor:
    def __init__(self, pdf_filename: str) -> None:
        """Initialize the extractor and verify the pdfcpu dependency."""
        self.check_pdfcpu()
        self.pdf_filename = pdf_filename

    @staticmethod
    def check_pdfcpu() -> str:
        """Return the pdfcpu binary path or raise if it is unavailable."""
        pdfcpu_path = shutil.which("pdfcpu")
        if not pdfcpu_path:
            raise RuntimeError("pdfcpu binary not found in PATH")
        return pdfcpu_path

    def extract(self) -> str:
        """Export PDF form data via pdfcpu and return the JSON string."""
        pdfcpu_path = self.check_pdfcpu()
        temp_handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        temp_handle.close()

        try:
            subprocess.run(
                [pdfcpu_path, "form", "export", self.pdf_filename, temp_handle.name],
                check=True,
                capture_output=True,
                text=True,
            )
            with open(temp_handle.name, "r", encoding="utf-8") as handle:
                return handle.read()
        finally:
            os.unlink(temp_handle.name)


def main() -> None:
    """CLI entrypoint that writes extracted JSON to out.json."""
    parser = argparse.ArgumentParser(description="PDF form extraction helper.")
    parser.add_argument("pdf_filename", help="Path to the PDF file.")
    args = parser.parse_args()

    extractor = PDFFormExtractor(args.pdf_filename)
    json_output = extractor.extract()
    with open("out.json", "w", encoding="utf-8") as handle:
        handle.write(json_output)
    print("Wrote out.json")


if __name__ == "__main__":
    main()
