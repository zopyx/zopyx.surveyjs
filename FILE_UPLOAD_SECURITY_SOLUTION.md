# File Upload Security Solution
## Comprehensive Validation for AI Document Uploads

**Severity:** MEDIUM  
**CWE:** CWE-434 (Unrestricted Upload of File with Dangerous Type)  
**Status:** Needs Implementation

---

## Current Vulnerabilities

### 1. Extension-Based Validation Only
```python
# Current code (line 678-691)
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".odt", ".html", ".htm"}

# ❌ Only checks extension - easily bypassed
# Example: shell.php.pdf will pass extension check
```

### 2. No File Size Limits
```python
# Line 694-700
file_data = uploaded_file.read()  # ❌ Can read unlimited size!
size_bytes = len(file_data)  # Only checks AFTER reading into memory
```

### 3. No Magic Bytes Validation
```python
# No verification of actual file content
# User can upload .pdf with PHP code inside
```

### 4. No Content Structure Validation
```python
# PDF extracted without validation
has_form, form_data, has_form_error = self._extract_pdf_form_data(file_data)
# Malformed PDF can cause crashes or security issues
```

---

## Proposed Solution

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Upload Pipeline                       │
├─────────────────────────────────────────────────────────┤
│ 1. Size Check (before reading)                          │
│    ├── Content-Length header validation                 │
│    └── Stream reading with size limit                   │
├─────────────────────────────────────────────────────────┤
│ 2. Extension Check                                      │
│    ├── Whitelist validation                             │
│    └── Double extension detection                       │
├─────────────────────────────────────────────────────────┤
│ 3. Magic Bytes Validation                               │
│    ├── First 4KB signature check                        │
│    └── File type verification                           │
├─────────────────────────────────────────────────────────┤
│ 4. Content Structure Validation                         │
│    ├── PDF structure validation                         │
│    ├── ZIP bomb detection (DOCX/ODT)                    │
│    └── Malformed file rejection                         │
├─────────────────────────────────────────────────────────┤
│ 5. Sanitization                                         │
│    ├── Filename sanitization                            │
│    └── Path traversal prevention                        │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation

### Step 1: Create Validation Module

```python
# src/zopyx/surveyjs/file_validation.py

"""Secure file upload validation for AI document processing."""

import io
import struct
import zipfile
from pathlib import Path
from typing import BinaryIO, Optional, Tuple

# Maximum file size: 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024

# Chunk size for reading
CHUNK_SIZE = 8192

# File signatures (magic bytes)
FILE_SIGNATURES = {
    b"%PDF": ("application/pdf", ".pdf"),
    b"PK\x03\x04": ("application/zip", ".zip"),  # DOCX, ODT are ZIP-based
    b"<!DO": ("text/html", ".html"),
    b"<htm": ("text/html", ".html"),
    b"<HTM": ("text/html", ".html"),
    b"<?xm": ("application/xml", ".xml"),
}

# Allowed MIME types and their extensions
ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.oasis.opendocument.text": ".odt",
    "text/html": ".html",
    "application/zip": None,  # Special handling for DOCX/ODT
}


class FileValidationError(Exception):
    """Raised when file validation fails."""
    pass


class FileTooLargeError(FileValidationError):
    """Raised when file exceeds size limit."""
    pass


class InvalidFileTypeError(FileValidationError):
    """Raised when file type is not allowed."""
    pass


class MalformedFileError(FileValidationError):
    """Raised when file structure is invalid."""
    pass


def validate_file_size(uploaded_file, max_size: int = MAX_FILE_SIZE) -> int:
    """
    Validate file size before/during reading.
    
    Args:
        uploaded_file: The uploaded file object
        max_size: Maximum allowed size in bytes
        
    Returns:
        int: Actual file size
        
    Raises:
        FileTooLargeError: If file exceeds max size
    """
    # Check Content-Length header first (if available)
    content_length = getattr(uploaded_file, 'Content-Length', None)
    if content_length is None:
        # Try common attribute names
        content_length = (
            getattr(uploaded_file, 'content_length', None) or
            getattr(uploaded_file, 'size', None)
        )
    
    if content_length and int(content_length) > max_size:
        raise FileTooLargeError(
            f"File too large: {int(content_length)} bytes. "
            f"Maximum allowed: {max_size} bytes ({max_size // 1024 // 1024}MB)"
        )
    
    # Read with size limit
    chunks = []
    total_size = 0
    
    while True:
        chunk = uploaded_file.read(CHUNK_SIZE)
        if not chunk:
            break
        
        total_size += len(chunk)
        if total_size > max_size:
            raise FileTooLargeError(
                f"File too large. Maximum allowed: {max_size} bytes ({max_size // 1024 // 1024}MB)"
            )
        chunks.append(chunk)
    
    # Reset file pointer for subsequent reads
    uploaded_file.seek(0)
    
    return total_size


def detect_mime_type(file_data: bytes) -> Tuple[str, Optional[str]]:
    """
    Detect MIME type from file magic bytes.
    
    Args:
        file_data: First few KB of file content
        
    Returns:
        Tuple of (mime_type, extension) or ("application/octet-stream", None)
    """
    # Check file signatures
    for signature, (mime_type, ext) in FILE_SIGNATURES.items():
        if file_data.startswith(signature):
            return mime_type, ext
    
    # Check for HTML (various starting patterns)
    header = file_data[:100].strip().lower()
    if header.startswith((b"<!doctype html", b"<html", b"<head", b"<body")):
        return "text/html", ".html"
    
    # Check if it's plain text
    try:
        file_data.decode('utf-8')
        if b'<' in file_data[:1000] and b'>' in file_data[:1000]:
            # Contains HTML-like tags
            return "text/html", ".html"
    except UnicodeDecodeError:
        pass
    
    return "application/octet-stream", None


def validate_pdf_structure(file_data: bytes) -> bool:
    """
    Validate PDF file structure.
    
    Args:
        file_data: PDF file content
        
    Returns:
        bool: True if valid PDF structure
        
    Raises:
        MalformedFileError: If PDF is malformed
    """
    # Check PDF header
    if not file_data.startswith(b"%PDF-"):
        raise MalformedFileError("Invalid PDF: Missing PDF header signature")
    
    # Check PDF version (1.0 through 2.0)
    header = file_data[:8].decode('latin-1', errors='ignore')
    if not any(header.startswith(f"%PDF-{v}") for v in ['1.', '2.']):
        raise MalformedFileError(f"Invalid PDF: Unknown PDF version in header: {header}")
    
    # Check for EOF marker (basic validation)
    if b"%%EOF" not in file_data[-1024:]:  # Check last 1KB
        raise MalformedFileError("Invalid PDF: Missing EOF marker")
    
    # Check for startxref
    if b"startxref" not in file_data:
        raise MalformedFileError("Invalid PDF: Missing startxref marker")
    
    return True


def validate_zip_structure(file_data: bytes, max_compression_ratio: int = 100) -> Tuple[bool, str]:
    """
    Validate ZIP-based files (DOCX, ODT) for zip bombs and structure.
    
    Args:
        file_data: ZIP file content
        max_compression_ratio: Maximum allowed compression ratio
        
    Returns:
        Tuple of (is_valid, file_type)
        
    Raises:
        MalformedFileError: If ZIP is malformed or is a zip bomb
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_data)) as zf:
            # Check for zip bomb (compression ratio)
            total_uncompressed = sum(info.file_size for info in zf.infolist())
            total_compressed = sum(info.compress_size for info in zf.infolist())
            
            if total_compressed == 0:
                raise MalformedFileError("Invalid ZIP: Zero compressed size")
            
            ratio = total_uncompressed / total_compressed
            if ratio > max_compression_ratio:
                raise MalformedFileError(
                    f"ZIP bomb detected: compression ratio {ratio:.1f}x exceeds limit of {max_compression_ratio}x"
                )
            
            # Check total extracted size
            if total_uncompressed > MAX_FILE_SIZE * 10:  # Allow 10x for internal XML
                raise MalformedFileError(
                    f"ZIP content too large: {total_uncompressed} bytes uncompressed"
                )
            
            # Check for DOCX structure
            docx_files = {'[Content_Types].xml', 'word/document.xml'}
            odt_files = {'mimetype', 'content.xml'}
            
            zip_files = set(zf.namelist())
            
            if docx_files.issubset(zip_files):
                # Additional DOCX validation
                try:
                    with zf.open('[Content_Types].xml') as ct:
                        content = ct.read(10000)
                        if b'wordprocessingml.document' in content:
                            return True, "docx"
                except Exception:
                    pass
                return True, "docx"  # Assume DOCX if structure matches
            
            if odt_files.issubset(zip_files):
                # Additional ODT validation
                try:
                    with zf.open('mimetype') as mt:
                        mime = mt.read().decode('utf-8', errors='ignore')
                        if 'opendocument.text' in mime:
                            return True, "odt"
                except Exception:
                    pass
                return True, "odt"  # Assume ODT if structure matches
            
            # Neither DOCX nor ODT
            raise MalformedFileError(
                "ZIP file is not a valid DOCX or ODT document"
            )
            
    except zipfile.BadZipFile:
        raise MalformedFileError("Invalid ZIP file structure")


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and malicious names.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove path components
    filename = Path(filename).name
    
    # Remove null bytes
    filename = filename.replace('\x00', '')
    
    # Remove control characters
    filename = ''.join(char for char in filename if ord(char) >= 32)
    
    # Limit length
    if len(filename) > 255:
        name, ext = Path(filename).stem, Path(filename).suffix
        filename = name[:255 - len(ext)] + ext
    
    # Ensure it doesn't start with . (hidden file)
    if filename.startswith('.'):
        filename = 'upload' + filename
    
    return filename


def validate_upload(
    uploaded_file,
    max_size: int = MAX_FILE_SIZE,
    allowed_extensions: Optional[set] = None
) -> Tuple[bytes, str, str]:
    """
    Complete upload validation pipeline.
    
    Args:
        uploaded_file: The uploaded file object
        max_size: Maximum allowed file size
        allowed_extensions: Set of allowed extensions (default: pdf, docx, odt, html)
        
    Returns:
        Tuple of (file_data, sanitized_filename, detected_extension)
        
    Raises:
        FileValidationError: If validation fails
    """
    if allowed_extensions is None:
        allowed_extensions = {".pdf", ".docx", ".odt", ".html", ".htm"}
    
    # 1. Validate and read with size limit
    size = validate_file_size(uploaded_file, max_size)
    
    # Reset and read full content
    uploaded_file.seek(0)
    file_data = uploaded_file.read()
    
    if not file_data:
        raise FileValidationError("Empty file uploaded")
    
    # 2. Sanitize filename
    original_filename = getattr(uploaded_file, 'filename', 'unknown')
    filename = sanitize_filename(original_filename)
    
    # 3. Check extension
    claimed_ext = Path(filename).suffix.lower()
    if claimed_ext not in allowed_extensions:
        raise InvalidFileTypeError(
            f"File extension '{claimed_ext}' not allowed. "
            f"Allowed: {', '.join(sorted(allowed_extensions))}"
        )
    
    # 4. Detect MIME type from magic bytes
    detected_mime, detected_ext = detect_mime_type(file_data[:4096])
    
    # 5. Validate based on detected type
    if detected_mime == "application/pdf":
        validate_pdf_structure(file_data)
        final_ext = ".pdf"
        
    elif detected_mime == "application/zip":
        is_valid, zip_type = validate_zip_structure(file_data)
        if zip_type == "docx":
            final_ext = ".docx"
        elif zip_type == "odt":
            final_ext = ".odt"
        else:
            raise InvalidFileTypeError("ZIP file is not a valid DOCX or ODT")
            
    elif detected_mime == "text/html":
        final_ext = ".html"
        
    else:
        raise InvalidFileTypeError(
            f"File type '{detected_mime}' not allowed or could not be verified"
        )
    
    # 6. Verify extension matches detected type
    if claimed_ext != final_ext:
        # Allow .htm vs .html mismatch
        if not (claimed_ext in {".html", ".htm"} and final_ext == ".html"):
            raise InvalidFileTypeError(
                f"File extension mismatch: claims '{claimed_ext}' but detected '{final_ext}'"
            )
    
    return file_data, filename, final_ext
```

### Step 2: Modify AIView to Use Validation

```python
# In src/zopyx/surveyjs/browser/ai.py

# Add import at top
from ..file_validation import (
    validate_upload,
    FileValidationError,
    FileTooLargeError,
    InvalidFileTypeError,
    MalformedFileError,
)

class AIView(Views):
    # ... existing constants ...
    
    # Add size limit constant
    MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
    
    def upload_document(self):
        """Handle document upload with comprehensive security validation."""
        uploaded_file = self.request.form.get("document_file")
        if not uploaded_file:
            return self._redirect_ai("No file uploaded. Please upload a file.", "error")
        
        try:
            # Comprehensive validation
            file_data, filename, extension = validate_upload(
                uploaded_file,
                max_size=self.MAX_UPLOAD_SIZE,
                allowed_extensions=self.ALLOWED_UPLOAD_EXTENSIONS
            )
            
            logger.info(
                "File upload validated: filename=%s, size=%d, type=%s",
                filename, len(file_data), extension
            )
            
        except FileTooLargeError as e:
            logger.warning("File upload rejected: too large - %s", str(e))
            return self._redirect_ai(
                f"File too large. Maximum size is {self.MAX_UPLOAD_SIZE // 1024 // 1024}MB.",
                "error"
            )
            
        except InvalidFileTypeError as e:
            logger.warning("File upload rejected: invalid type - %s", str(e))
            return self._redirect_ai(str(e), "error")
            
        except MalformedFileError as e:
            logger.warning("File upload rejected: malformed file - %s", str(e))
            return self._redirect_ai(
                f"The uploaded file appears to be corrupted or invalid: {e}",
                "error"
            )
            
        except FileValidationError as e:
            logger.warning("File upload rejected: validation failed - %s", str(e))
            return self._redirect_ai(str(e), "error")
        
        # Continue with existing logic...
        has_form = None
        form_data = None
        has_form_error = None
        if extension == ".pdf":
            has_form, form_data, has_form_error = self._extract_pdf_form_data(file_data)
        
        # ... rest of method unchanged ...
```

### Step 3: Add Registry Configuration

```python
# In interfaces.py, add to IFormsSettings:

fieldset(
    "file_upload",
    label="File Upload Security",
    fields=(
        "max_upload_size_mb",
        "upload_allowed_extensions",
    ),
)

max_upload_size_mb = schema.Int(
    title="Maximum upload size (MB)",
    description="Maximum file size allowed for AI document uploads.",
    required=False,
    default=50,
    min=1,
    max=500,
)

upload_allowed_extensions = schema.List(
    title="Allowed file extensions",
    description="File extensions allowed for upload (include the dot, e.g., .pdf).",
    value_type=schema.TextLine(),
    required=False,
    default=[".pdf", ".docx", ".odt", ".html"],
)
```

---

## Security Benefits

| Check | Prevents | Example Attack |
|-------|----------|----------------|
| **Size Limit** | DoS via large uploads | 10GB file causing memory exhaustion |
| **Magic Bytes** | Extension spoofing | shell.php.pdf appearing as PDF |
| **PDF Validation** | Malformed PDF exploits | Crash attacks, parser vulnerabilities |
| **ZIP Validation** | Zip bombs | 42.zip-style compression attacks |
| **Filename Sanitization** | Path traversal | ../../../etc/passwd uploads |

---

## Testing

```python
# tests/test_file_validation.py

import unittest
from io import BytesIO
from zopyx.surveyjs.file_validation import (
    validate_upload,
    FileTooLargeError,
    InvalidFileTypeError,
    MalformedFileError,
    detect_mime_type,
    validate_pdf_structure,
    validate_zip_structure,
    sanitize_filename,
)


class TestFileValidation(unittest.TestCase):
    """Test file upload security validation."""
    
    def test_valid_pdf(self):
        """Valid PDF passes validation."""
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\nxref\n0 2\n0000000000 65535 f\n0000000009 00000 n\ntrailer\n<<\n/Size 2\n/Root 1 0 R\n>>\nstartxref\n45\n%%EOF"
        
        uploaded = BytesIO(pdf_content)
        uploaded.filename = "test.pdf"
        
        data, name, ext = validate_upload(uploaded)
        self.assertEqual(ext, ".pdf")
    
    def test_extension_spoofing_blocked(self):
        """PHP file with PDF extension is blocked."""
        php_in_pdf = b"%PDF-1.4 fake header\n<?php system($_GET['cmd']); ?>"
        
        uploaded = BytesIO(php_in_pdf)
        uploaded.filename = "shell.php.pdf"
        
        with self.assertRaises(InvalidFileTypeError):
            validate_upload(uploaded)
    
    def test_file_too_large(self):
        """Files exceeding size limit are rejected."""
        uploaded = BytesIO(b"x" * (100 * 1024 * 1024))  # 100MB
        uploaded.filename = "large.pdf"
        
        with self.assertRaises(FileTooLargeError):
            validate_upload(uploaded, max_size=50 * 1024 * 1024)
    
    def test_zip_bomb_detected(self):
        """Zip bombs are detected and rejected."""
        # Create a highly compressed ZIP
        import zipfile
        import io
        
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 100MB of zeros compressed to tiny size
            zf.writestr("content.xml", b"0" * (100 * 1024 * 1024))
        
        buffer.seek(0)
        buffer.filename = "bomb.odt"
        
        with self.assertRaises(MalformedFileError):
            validate_upload(buffer)
    
    def test_path_traversal_prevented(self):
        """Path traversal in filename is sanitized."""
        malicious = "../../../etc/passwd.pdf"
        sanitized = sanitize_filename(malicious)
        self.assertEqual(sanitized, "passwd.pdf")
    
    def test_malformed_pdf_rejected(self):
        """Malformed PDFs are rejected."""
        fake_pdf = b"Not a real PDF file content"
        
        uploaded = BytesIO(fake_pdf)
        uploaded.filename = "fake.pdf"
        
        with self.assertRaises(InvalidFileTypeError):
            validate_upload(uploaded)
```

---

## Deployment Checklist

- [ ] Add `file_validation.py` module
- [ ] Modify `ai.py` to use validation
- [ ] Add registry settings for configuration
- [ ] Run tests: `make test`
- [ ] Configure max upload size in Site Setup
- [ ] Monitor logs for blocked uploads
- [ ] Document allowed file types for users

---

**Want me to implement this solution?**
