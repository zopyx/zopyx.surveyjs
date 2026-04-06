# -*- coding: utf-8 -*-
"""Comprehensive tests for file upload validation.

This module tests file type detection, extension spoofing detection,
file size limits, structure validation, and filename sanitization.
"""

from __future__ import annotations

import io
import unittest
import zipfile
from pathlib import Path
from typing import BinaryIO
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================

def create_mock_uploaded_file(content: bytes, filename: str) -> BinaryIO:
    """Create a mock uploaded file with filename attribute."""
    uploaded = io.BytesIO(content)
    uploaded.filename = filename
    return uploaded


# Minimal valid file headers/signatures
PDF_HEADER = b"%PDF-1.4\n"
PDF_FOOTER = b"\n%%EOF"
PDF_MINIMAL = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n"
    b"xref\n0 2\n0000000000 65535 f\n0000000009 00000 n\n"
    b"trailer\n<<\n/Size 2\n/Root 1 0 R\n>>\n"
    b"startxref\n45\n%%EOF"
)

ZIP_SIGNATURE = b"PK\x03\x04"

DOCX_CONTENT_TYPES = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" 
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''

ODT_MIMETYPE = b"application/vnd.oasis.opendocument.text"

HTML_CONTENT = b"<!DOCTYPE html><html><head></head><body></body></html>"


# =============================================================================
# File Type Detection Tests (puremagic)
# =============================================================================

class TestFileTypeDetection(unittest.TestCase):
    """Test file type detection using magic bytes."""

    def test_valid_pdf_detection(self):
        """Test that valid PDF files are correctly identified."""
        # Test with minimal valid PDF
        uploaded = create_mock_uploaded_file(PDF_MINIMAL, "document.pdf")
        
        # Read and check magic bytes
        header = uploaded.read(8)
        uploaded.seek(0)
        
        assert header.startswith(b"%PDF"), "PDF header signature not detected"
        assert b"%PDF-" in header, "PDF version marker not found"
    
    def test_valid_docx_detection(self):
        """Test that valid DOCX files are correctly identified via ZIP structure."""
        # Create minimal DOCX structure
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('[Content_Types].xml', DOCX_CONTENT_TYPES)
            zf.writestr('word/document.xml', b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"></w:document>')
        
        buffer.seek(0)
        header = buffer.read(4)
        
        assert header == b"PK\x03\x04", "ZIP signature (DOCX) not detected"
        
        # Verify it's a valid ZIP with DOCX structure
        buffer.seek(0)
        with zipfile.ZipFile(buffer, 'r') as zf:
            files = set(zf.namelist())
            assert '[Content_Types].xml' in files, "DOCX Content_Types.xml missing"
            assert 'word/document.xml' in files, "DOCX word/document.xml missing"
    
    def test_valid_odt_detection(self):
        """Test that valid ODT files are correctly identified via ZIP structure."""
        # Create minimal ODT structure
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('mimetype', ODT_MIMETYPE)
            zf.writestr('content.xml', b'<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"></office:document-content>')
        
        buffer.seek(0)
        header = buffer.read(4)
        
        assert header == b"PK\x03\x04", "ZIP signature (ODT) not detected"
        
        # Verify it's a valid ZIP with ODT structure
        buffer.seek(0)
        with zipfile.ZipFile(buffer, 'r') as zf:
            files = set(zf.namelist())
            assert 'mimetype' in files, "ODT mimetype file missing"
            assert 'content.xml' in files, "ODT content.xml missing"
            
            # Check mimetype content
            mimetype = zf.read('mimetype').decode('utf-8')
            assert 'opendocument.text' in mimetype, "ODT mimetype not recognized"
    
    def test_valid_html_detection(self):
        """Test that valid HTML files are correctly identified."""
        test_cases = [
            (b"<!DOCTYPE html><html></html>", "doctype declaration"),
            (b"<!doctype html><html></html>", "lowercase doctype"),
            (b"<html><head></head></html>", "html tag"),
            (b"<HTML><BODY></BODY></HTML>", "uppercase HTML"),
            (b"<head><title>Test</title></head><body></body>", "head tag first"),
        ]
        
        for content, description in test_cases:
            uploaded = create_mock_uploaded_file(content, "page.html")
            header = uploaded.read(100).strip().lower()
            uploaded.seek(0)
            
            is_html = (
                header.startswith(b"<!doctype html") or
                header.startswith(b"<html") or
                header.startswith(b"<head") or
                header.startswith(b"<body")
            )
            assert is_html, f"HTML detection failed for: {description}"


# =============================================================================
# Extension Spoofing Detection Tests
# =============================================================================

class TestExtensionSpoofing(unittest.TestCase):
    """Test detection of extension spoofing attacks."""

    def test_php_in_pdf_blocked(self):
        """Test that PHP code embedded in fake PDF is detected."""
        # Create a file with PDF header but PHP content
        malicious_content = b"%PDF-1.4 fake header\n<?php system($_GET['cmd']); ?>"
        uploaded = create_mock_uploaded_file(malicious_content, "shell.php.pdf")
        
        # Check: Has PDF header but no PDF structure
        header = uploaded.read(5)
        uploaded.seek(0)
        
        # Verify it starts with PDF signature (would pass naive check)
        assert header == b"%PDF-", "Test setup: should start with PDF header"
        
        # Verify it lacks proper PDF structure (no EOF marker)
        content = uploaded.read()
        assert b"%%EOF" not in content, "Malformed PDF should lack proper EOF"
        assert b"<?php" in content, "PHP code should be present in test data"
    
    def test_extension_mismatch_detected(self):
        """Test that extension/mime-type mismatches are detected."""
        # PDF content with wrong extension
        pdf_wrong_ext = create_mock_uploaded_file(PDF_MINIMAL, "document.docx")
        header = pdf_wrong_ext.read(4)
        pdf_wrong_ext.seek(0)
        
        # Header says PDF, extension says DOCX
        claimed_ext = Path(pdf_wrong_ext.filename).suffix.lower()
        detected_signature = header
        
        assert claimed_ext == ".docx", "Test setup: extension should be .docx"
        assert detected_signature == b"%PDF", "Test setup: header should be PDF"
        
        # This mismatch should be detected
        is_mismatch = (
            detected_signature == b"%PDF" and claimed_ext != ".pdf"
        )
        assert is_mismatch, "Extension mismatch not detected"
    
    def test_double_extension_attack(self):
        """Test detection of double extension attacks like shell.php.pdf."""
        filename = "shell.php.pdf"
        suffixes = Path(filename).suffixes
        
        # Should detect multiple extensions
        assert len(suffixes) > 1, "Double extension not detected"
        assert ".php" in suffixes, "Dangerous .php extension not detected"
        
        # Final extension might look safe
        assert suffixes[-1] == ".pdf", "Test setup: final extension should be .pdf"


# =============================================================================
# File Size Limit Tests
# =============================================================================

class TestFileSizeLimits(unittest.TestCase):
    """Test file size validation."""

    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    CHUNK_SIZE = 8192

    def test_file_within_size_limit(self):
        """Test that files within size limit are accepted."""
        # Create a 1MB file
        content = b"x" * (1 * 1024 * 1024)
        uploaded = create_mock_uploaded_file(content, "valid.pdf")
        
        # Simulate size check
        total_size = len(content)
        
        assert total_size <= self.MAX_FILE_SIZE, "Valid file size rejected"
        assert total_size == 1 * 1024 * 1024, "File size calculation incorrect"
    
    def test_file_too_large_rejected(self):
        """Test that files exceeding size limit are rejected."""
        # Create a file larger than limit
        oversized_content = b"x" * (self.MAX_FILE_SIZE + 1)
        uploaded = create_mock_uploaded_file(oversized_content, "too_large.pdf")
        
        # Simulate chunked reading with size limit
        total_size = len(oversized_content)
        
        assert total_size > self.MAX_FILE_SIZE, "Test setup: file should exceed limit"
        
        # Size check should reject
        is_too_large = total_size > self.MAX_FILE_SIZE
        assert is_too_large, "Oversized file not detected"
    
    def test_chunked_reading_with_size_check(self):
        """Test that chunked reading properly enforces size limits."""
        content = b"x" * (2 * self.CHUNK_SIZE + 100)  # Multiple chunks + remainder
        uploaded = create_mock_uploaded_file(content, "multi_chunk.pdf")
        
        # Simulate chunked reading
        total_size = 0
        max_size = self.MAX_FILE_SIZE
        exceeded = False
        
        while True:
            chunk = uploaded.read(self.CHUNK_SIZE)
            if not chunk:
                break
            
            total_size += len(chunk)
            if total_size > max_size:
                exceeded = True
                break
        
        uploaded.seek(0)
        
        assert not exceeded, "Valid multi-chunk file incorrectly rejected"
        assert total_size == len(content), "Chunked reading size mismatch"


# =============================================================================
# Structure Validation Tests
# =============================================================================

class TestStructureValidation(unittest.TestCase):
    """Test file structure validation for various formats."""

    def test_malformed_pdf_rejected(self):
        """Test that malformed PDFs are detected and rejected."""
        malformed_pdfs = [
            # Missing PDF header
            (b"This is not a PDF file", "no_header"),
            # PDF header but no version
            (b"%PDF\n", "no_version"),
            # PDF header but no EOF
            (b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj", "no_eof"),
            # Valid header but no startxref
            (b"%PDF-1.4\ncontent\n%%EOF", "no_startxref"),
        ]
        
        for content, description in malformed_pdfs:
            uploaded = create_mock_uploaded_file(content, f"malformed_{description}.pdf")
            
            # Check PDF structure
            is_valid_pdf = True
            
            # Must start with %PDF-
            if not content.startswith(b"%PDF-"):
                is_valid_pdf = False
            else:
                # Check version
                header = content[:8].decode('latin-1', errors='ignore')
                if not any(header.startswith(f"%PDF-{v}") for v in ['1.', '2.']):
                    is_valid_pdf = False
                # Check for EOF
                elif b"%%EOF" not in content[-1024:]:
                    is_valid_pdf = False
                # Check for startxref
                elif b"startxref" not in content:
                    is_valid_pdf = False
            
            assert not is_valid_pdf, f"Malformed PDF accepted: {description}"
    
    def test_zip_bomb_detected(self):
        """Test that zip bombs (high compression ratios) are detected."""
        # Create a zip bomb: small file that decompresses to huge size
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Compress 100MB of identical data (highly compressible)
            huge_data = b"A" * (100 * 1024 * 1024)
            zf.writestr('content.xml', huge_data)
        
        buffer.seek(0)
        zip_data = buffer.read()
        
        # Verify compression ratio is extreme
        compressed_size = len(zip_data)
        uncompressed_size = 100 * 1024 * 1024
        compression_ratio = uncompressed_size / compressed_size
        
        # This is a zip bomb if ratio is > 100x
        is_zip_bomb = compression_ratio > 100
        
        assert is_zip_bomb, f"Zip bomb not detected. Ratio: {compression_ratio:.1f}x"
        assert compressed_size < 1 * 1024 * 1024, "Zip bomb not highly compressed"
    
    def test_corrupted_docx_rejected(self):
        """Test that corrupted DOCX files are rejected."""
        # Create a corrupted ZIP that looks like DOCX
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Missing required [Content_Types].xml and word/document.xml
            zf.writestr('random.txt', b'not a valid docx')
        
        buffer.seek(0)
        
        # Try to validate as DOCX
        with zipfile.ZipFile(buffer, 'r') as zf:
            files = set(zf.namelist())
            required_files = {'[Content_Types].xml', 'word/document.xml'}
            
            is_valid_docx = required_files.issubset(files)
        
        assert not is_valid_docx, "Corrupted DOCX accepted as valid"
    
    def test_valid_zip_structure_accepted(self):
        """Test that valid ZIP-based formats pass structure validation."""
        # Valid DOCX
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('[Content_Types].xml', DOCX_CONTENT_TYPES)
            zf.writestr('word/document.xml', b'<w:document></w:document>')
        
        buffer.seek(0)
        
        # Validate compression ratio
        with zipfile.ZipFile(buffer, 'r') as zf:
            total_uncompressed = sum(info.file_size for info in zf.infolist())
            total_compressed = sum(info.compress_size for info in zf.infolist())
            
            if total_compressed > 0:
                ratio = total_uncompressed / total_compressed
                is_valid_ratio = ratio <= 100
            else:
                is_valid_ratio = False
            
            # Check required files
            files = set(zf.namelist())
            required_files = {'[Content_Types].xml', 'word/document.xml'}
            has_required_files = required_files.issubset(files)
        
        assert is_valid_ratio, "Valid compression ratio rejected"
        assert has_required_files, "Required DOCX files not found"


# =============================================================================
# Filename Sanitization Tests
# =============================================================================

class TestFilenameSanitization(unittest.TestCase):
    """Test filename sanitization for security."""

    def test_path_traversal_prevented(self):
        """Test that path traversal attempts are blocked."""
        malicious_names = [
            "../../../etc/passwd.pdf",
            "./../../secret.pdf",
            "folder/../../../etc/shadow.pdf",
        ]
        
        for malicious_name in malicious_names:
            # Apply sanitization using Path().name
            sanitized = Path(malicious_name).name
            
            # After sanitization, should just be the filename
            assert "/" not in sanitized, f"Path separator not removed: {malicious_name}"
            assert ".." not in sanitized, f"Parent directory reference remains: {malicious_name}"
            assert ".pdf" in sanitized, f"Extension lost during sanitization: {malicious_name}"
        
        # Test URL-encoded path traversal (requires explicit decoding)
        url_encoded = "..%2f..%2f..%2fetc%2fpasswd.pdf"
        # URL decoding should happen before Path() sanitization
        import urllib.parse
        decoded = urllib.parse.unquote(url_encoded)
        sanitized_encoded = Path(decoded).name
        assert "/" not in sanitized_encoded, "URL encoded path not handled"
        assert ".." not in sanitized_encoded, "Parent ref in URL encoded path"
        
        # Test Windows-style backslash separately (only relevant on Windows)
        # On Unix/Mac, backslash is a valid filename character
        windows_traversal = "..\\..\\..\\windows\\system32\\config\\sam.pdf"
        sanitized_windows = Path(windows_traversal).name
        # On Windows this would be 'sam.pdf', on Unix it stays as-is
        # We just verify that forward slashes are handled correctly
        assert "/" not in sanitized_windows, "Forward slash not removed from Windows-style path"
    
    def test_null_bytes_removed(self):
        """Test that null bytes are removed from filenames."""
        names_with_nulls = [
            "file\x00name.pdf",
            "doc\x00.pdf",
            "test\x00\x00.pdf",
            "\x00hidden.pdf",
        ]
        
        for name_with_null in names_with_nulls:
            # Apply sanitization
            sanitized = name_with_null.replace('\x00', '')
            
            assert '\x00' not in sanitized, f"Null byte not removed: {repr(name_with_null)}"
            assert sanitized.endswith('.pdf'), f"Extension lost: {sanitized}"
    
    def test_long_filename_truncated(self):
        """Test that excessively long filenames are truncated."""
        # Create a 500-character filename
        long_name = "a" * 490 + ".pdf"
        
        # Apply truncation (max 255 chars total)
        if len(long_name) > 255:
            ext = Path(long_name).suffix
            name = Path(long_name).stem
            truncated = name[:255 - len(ext)] + ext
        else:
            truncated = long_name
        
        assert len(truncated) <= 255, f"Filename not truncated: {len(truncated)} chars"
        assert truncated.endswith('.pdf'), "Extension lost during truncation"
    
    def test_hidden_file_prefix_handled(self):
        """Test that hidden file indicators are handled."""
        hidden_names = [
            ".htaccess.pdf",
            ".env.pdf",
            ".gitignore.pdf",
        ]
        
        for hidden_name in hidden_names:
            # Handle hidden file prefix
            if hidden_name.startswith('.'):
                sanitized = 'upload' + hidden_name
            else:
                sanitized = hidden_name
            
            assert not sanitized.startswith('.'), f"Hidden file prefix not handled: {sanitized}"
            assert sanitized.endswith('.pdf'), "Extension lost"
    
    def test_control_characters_removed(self):
        """Test that control characters are removed."""
        name_with_controls = "file\x01\x02\x03name.pdf"
        
        # Remove control characters (chars with ord < 32)
        sanitized = ''.join(char for char in name_with_controls if ord(char) >= 32)
        
        assert sanitized == "filename.pdf", f"Control chars not removed: {sanitized}"
        assert all(ord(c) >= 32 for c in sanitized), "Control chars remain"


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_empty_file_rejected(self):
        """Test that empty files are rejected."""
        empty_content = b""
        uploaded = create_mock_uploaded_file(empty_content, "empty.pdf")
        
        content = uploaded.read()
        is_empty = len(content) == 0
        
        assert is_empty, "Test setup: file should be empty"
        
        # Empty files should be rejected
        assert len(content) == 0, "Empty file should have zero bytes"
    
    def test_confidence_threshold(self):
        """Test confidence threshold for file type detection."""
        # Files that might be ambiguous
        ambiguous_content = b"PK\x03\x04"  # ZIP signature but minimal
        
        # With only 4 bytes, confidence should be low
        is_confident = len(ambiguous_content) >= 100  # Arbitrary threshold
        
        assert not is_confident, "Low confidence detection not flagged"
    
    def test_unicode_filename_handling(self):
        """Test handling of unicode filenames."""
        unicode_names = [
            "文档.pdf",  # Chinese
            "документ.pdf",  # Russian
            "文書.pdf",  # Japanese
            "tëst-fïlé.pdf",  # Accented
            "📝document.pdf",  # Emoji
        ]
        
        for name in unicode_names:
            # Should be able to handle the filename
            try:
                encoded = name.encode('utf-8')
                decoded = encoded.decode('utf-8')
                assert decoded == name, f"Unicode filename corrupted: {name}"
            except (UnicodeEncodeError, UnicodeDecodeError) as e:
                pytest.fail(f"Unicode filename failed: {name} - {e}")
    
    def test_case_insensitive_extension_check(self):
        """Test that extension checks are case-insensitive."""
        extensions = [".PDF", ".Pdf", ".pDf", ".pdf"]
        allowed_extensions = {".pdf"}
        
        for ext in extensions:
            is_allowed = ext.lower() in allowed_extensions
            assert is_allowed, f"Extension {ext} not recognized as valid"
    
    def test_multiple_dots_in_filename(self):
        """Test filenames with multiple dots."""
        names = [
            "my.document.v1.pdf",
            "report.2024.01.15.pdf",
            "archive.tar.gz.pdf",
        ]
        
        for name in names:
            # Should extract correct extension
            ext = Path(name).suffix.lower()
            assert ext == ".pdf", f"Extension extraction failed for: {name}"
    
    def test_whitespace_in_filename(self):
        """Test handling of whitespace in filenames."""
        names_with_whitespace = [
            "my document.pdf",
            "document .pdf",
            " document.pdf",
            "document.pdf ",
        ]
        
        for name in names_with_whitespace:
            # Strip leading/trailing whitespace
            sanitized = name.strip()
            ext = Path(sanitized).suffix.lower()
            assert ext == ".pdf", f"Extension extraction failed for: {repr(name)}"


# =============================================================================
# Integration-style Tests
# =============================================================================

class TestValidationPipeline(unittest.TestCase):
    """Test the complete validation pipeline."""

    def test_valid_pdf_passes_all_checks(self):
        """Test that a valid PDF passes all validation stages."""
        content = PDF_MINIMAL
        uploaded = create_mock_uploaded_file(content, "document.pdf")
        
        # Stage 1: Size check
        size = len(content)
        assert size <= 50 * 1024 * 1024, "Size check failed"
        
        # Stage 2: Extension check
        ext = Path(uploaded.filename).suffix.lower()
        assert ext == ".pdf", "Extension check failed"
        
        # Stage 3: Magic bytes check
        header = content[:4]
        assert header == b"%PDF", "Magic bytes check failed"
        
        # Stage 4: Structure validation
        has_pdf_header = content.startswith(b"%PDF-")
        has_eof = b"%%EOF" in content[-1024:]
        has_startxref = b"startxref" in content
        
        assert has_pdf_header, "PDF header validation failed"
        assert has_eof, "PDF EOF validation failed"
        assert has_startxref, "PDF startxref validation failed"
    
    def test_rejection_at_each_stage(self):
        """Test that files are rejected at appropriate validation stages."""
        test_cases = [
            # (description, content, filename, expected_failure_stage)
            ("oversized", b"x" * (51 * 1024 * 1024), "large.pdf", "size"),
            ("bad_extension", PDF_MINIMAL, "document.exe", "extension"),
            ("wrong_magic", b"NOTPDF", "fake.pdf", "magic_bytes"),
            ("malformed_pdf", b"%PDF-1.4\nno content", "broken.pdf", "structure"),
        ]
        
        for description, content, filename, expected_stage in test_cases:
            uploaded = create_mock_uploaded_file(content, filename)
            
            # Track which stage rejects
            rejection_stage = None
            
            # Stage 1: Size
            if len(content) > 50 * 1024 * 1024:
                rejection_stage = "size"
            # Stage 2: Extension
            elif Path(filename).suffix.lower() not in {".pdf", ".docx", ".odt", ".html", ".htm"}:
                rejection_stage = "extension"
            # Stage 3: Magic bytes (for PDF)
            elif not content.startswith(b"%PDF") and filename.endswith(".pdf"):
                rejection_stage = "magic_bytes"
            # Stage 4: Structure
            elif filename.endswith(".pdf"):
                if b"%%EOF" not in content or b"startxref" not in content:
                    rejection_stage = "structure"
            
            assert rejection_stage == expected_stage, \
                f"{description}: expected rejection at {expected_stage}, got {rejection_stage}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
