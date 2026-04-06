"""File validation module for SurveyJS file uploads.

This module provides comprehensive file validation including:
- File size validation
- File type detection using puremagic
- File structure validation for PDF and ZIP-based formats
- Filename sanitization
"""

import io
import logging
import zipfile
from pathlib import Path
from typing import BinaryIO, Optional, Tuple

import puremagic

# Configure logging
logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
CHUNK_SIZE = 8192

# MIME type to extension mapping for allowed file types
ALLOWED_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.oasis.opendocument.text": ".odt",
    "text/html": ".html",
}

MIN_CONFIDENCE = 0.7
MIN_CONFIDENCE_WITH_VALIDATION = 0.4  # Lower threshold for files with structure validation

# =============================================================================
# Exception Classes
# =============================================================================


class FileValidationError(Exception):
    """Base exception for file validation errors."""

    pass


class FileTooLargeError(FileValidationError):
    """Exception raised when a file exceeds the maximum allowed size."""

    def __init__(self, size: int, max_size: int) -> None:
        self.size = size
        self.max_size = max_size
        super().__init__(f"File size {size} bytes exceeds maximum of {max_size} bytes")


class InvalidFileTypeError(FileValidationError):
    """Exception raised when a file type is not in the allowed list."""

    def __init__(self, mime_type: str, extension: str) -> None:
        self.mime_type = mime_type
        self.extension = extension
        super().__init__(f"File type '{mime_type}' (extension: {extension}) is not allowed")


class MalformedFileError(FileValidationError):
    """Exception raised when a file fails structure validation."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"File structure validation failed: {reason}")


class ExtensionMismatchError(FileValidationError):
    """Exception raised when file extension doesn't match detected MIME type."""

    def __init__(self, declared_ext: str, detected_ext: str) -> None:
        self.declared_ext = declared_ext
        self.detected_ext = detected_ext
        super().__init__(
            f"Extension mismatch: declared '{declared_ext}' but detected '{detected_ext}'"
        )


# =============================================================================
# Validation Functions
# =============================================================================


def validate_file_size(uploaded_file: BinaryIO, max_size: int) -> int:
    """Validate file size by reading in chunks.

    Args:
        uploaded_file: File-like object to validate
        max_size: Maximum allowed size in bytes

    Returns:
        Total size of the file in bytes

    Raises:
        FileTooLargeError: If file exceeds max_size
        FileValidationError: If file cannot be read
    """
    total_size = 0
    chunk_num = 0

    try:
        while True:
            chunk = uploaded_file.read(CHUNK_SIZE)
            if not chunk:
                break

            total_size += len(chunk)
            chunk_num += 1

            if total_size > max_size:
                logger.warning(
                    f"File size exceeded limit at chunk {chunk_num}: "
                    f"{total_size} bytes > {max_size} bytes"
                )
                raise FileTooLargeError(total_size, max_size)

    except FileTooLargeError:
        raise
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        raise FileValidationError(f"Failed to read file: {e}") from e

    logger.debug(f"File size validated: {total_size} bytes in {chunk_num} chunks")
    return total_size


def detect_file_type(file_data: bytes) -> Tuple[str, str, float]:
    """Detect file type using puremagic.

    Args:
        file_data: Raw bytes of the file

    Returns:
        Tuple of (extension, mime_type, confidence)

    Raises:
        FileValidationError: If detection fails
    """
    try:
        matches = puremagic.magic_string(file_data)

        if not matches:
            logger.warning("puremagic returned no matches for file data")
            return ("", "application/octet-stream", 0.0)

        # Get the best match (first in list, sorted by confidence)
        best_match = matches[0]
        extension = best_match.extension
        mime_type = best_match.mime_type
        confidence = best_match.confidence

        logger.debug(
            f"File type detected: ext={extension}, mime={mime_type}, "
            f"confidence={confidence:.2f}"
        )

        return (extension, mime_type, confidence)

    except Exception as e:
        logger.error(f"Error detecting file type: {e}")
        raise FileValidationError(f"Failed to detect file type: {e}") from e


def validate_pdf_structure(file_data: bytes) -> bool:
    """Validate PDF file structure.

    Checks for:
    - PDF header (starts with %PDF)
    - Version number
    - EOF marker (%%EOF)

    Args:
        file_data: Raw bytes of the PDF file

    Returns:
        True if valid PDF structure

    Raises:
        MalformedFileError: If PDF structure is invalid
    """
    try:
        # Check PDF header
        if not file_data.startswith(b"%PDF"):
            logger.warning("PDF validation failed: missing PDF header")
            raise MalformedFileError("Missing PDF header (file must start with %PDF)")

        # Check version (format: %PDF-x.y)
        header = file_data[:8].decode("ascii", errors="replace")
        # Format: %PDF-x.y where x and y are digits
        # Positions: 0-3=%PDF, 4=-, 5=x, 6=., 7=y
        if len(header) < 8 or header[4] != '-' or not header[5].isdigit() or header[6] != '.' or not header[7].isdigit():
            logger.warning(f"PDF validation failed: invalid version header: {header}")
            raise MalformedFileError("Invalid PDF version header")

        # Check EOF marker
        if b"%%EOF" not in file_data:
            logger.warning("PDF validation failed: missing EOF marker")
            raise MalformedFileError("Missing PDF EOF marker (%%EOF)")

        logger.debug("PDF structure validated successfully")
        return True

    except MalformedFileError:
        raise
    except Exception as e:
        logger.error(f"Error validating PDF structure: {e}")
        raise MalformedFileError(f"PDF validation error: {e}") from e


def validate_zip_structure(file_data: bytes) -> Tuple[bool, str]:
    """Validate ZIP file structure and detect if it's a DOCX or ODT.

    Checks for:
    - Valid ZIP format
    - ZIP bomb detection (compression ratio limit)
    - DOCX structure (word/document.xml)
    - ODT structure (content.xml)

    Args:
        file_data: Raw bytes of the ZIP file

    Returns:
        Tuple of (is_valid, file_type) where file_type is 'docx', 'odt', or 'unknown'

    Raises:
        MalformedFileError: If ZIP is corrupted or is a ZIP bomb
    """
    try:
        zip_buffer = io.BytesIO(file_data)

        with zipfile.ZipFile(zip_buffer, "r") as zf:
            # Check for ZIP bombs (compression ratio check)
            total_uncompressed = 0
            total_compressed = 0
            max_ratio = 100  # Maximum 100:1 compression ratio

            for info in zf.infolist():
                total_uncompressed += info.file_size
                total_compressed += info.compress_size

            if total_compressed > 0:
                ratio = total_uncompressed / total_compressed
                if ratio > max_ratio:
                    logger.warning(
                        f"ZIP bomb detected: compression ratio {ratio:.1f}:1 "
                        f"(max {max_ratio}:1)"
                    )
                    raise MalformedFileError(
                        f"ZIP bomb detected (compression ratio {ratio:.1f}:1 exceeds limit)"
                    )

            # Check file size sanity
            max_file_size = MAX_FILE_SIZE * 10  # Allow 10x expansion
            for info in zf.infolist():
                if info.file_size > max_file_size:
                    logger.warning(
                        f"ZIP contains oversized file: {info.filename} "
                        f"({info.file_size} bytes)"
                    )
                    raise MalformedFileError(
                        f"ZIP contains oversized file: {info.filename}"
                    )

            # Get list of files in the archive
            file_list = zf.namelist()

            # Check for DOCX structure
            if "word/document.xml" in file_list:
                logger.debug("ZIP structure validated as DOCX")
                return (True, "docx")

            # Check for ODT structure
            if "content.xml" in file_list:
                logger.debug("ZIP structure validated as ODT")
                return (True, "odt")

            # Valid ZIP but not DOCX or ODT
            logger.debug("ZIP structure valid but not DOCX or ODT")
            return (True, "unknown")

    except zipfile.BadZipFile as e:
        logger.warning(f"Invalid ZIP file: {e}")
        raise MalformedFileError(f"Invalid ZIP file: {e}") from e
    except MalformedFileError:
        raise
    except Exception as e:
        logger.error(f"Error validating ZIP structure: {e}")
        raise MalformedFileError(f"ZIP validation error: {e}") from e


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal and other attacks.

    Performs the following sanitization:
    - Remove path components (keep only basename)
    - Remove null bytes
    - Remove control characters
    - Limit to 255 characters

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed_file"

    # Remove path components (prevent path traversal)
    sanitized = Path(filename).name

    # Remove null bytes
    sanitized = sanitized.replace("\x00", "")

    # Remove control characters (except tab, newline, etc. which shouldn't be in filenames)
    sanitized = "".join(char for char in sanitized if ord(char) >= 32 or char in "\t\n\r")

    # Limit to 255 characters (common filesystem limit)
    if len(sanitized) > 255:
        # Preserve extension when truncating
        name_part = Path(sanitized).stem
        ext_part = Path(sanitized).suffix
        max_name_len = 255 - len(ext_part)
        sanitized = name_part[:max_name_len] + ext_part
        logger.debug(f"Filename truncated to 255 characters: {sanitized}")

    # If sanitized is empty, provide a default
    if not sanitized or sanitized == ".":
        sanitized = "unnamed_file"

    logger.debug(f"Filename sanitized: '{filename}' -> '{sanitized}'")
    return sanitized


def validate_upload(
    uploaded_file: BinaryIO,
    max_size: int = MAX_FILE_SIZE,
    allowed_extensions: Optional[list[str]] = None,
) -> Tuple[bytes, str, str]:
    """Validate an uploaded file comprehensively.

    Performs the following validations:
    1. File size check (chunked reading)
    2. File type detection using puremagic
    3. Confidence threshold check
    4. Extension match validation
    5. Structure validation for PDF and ZIP-based formats

    Args:
        uploaded_file: File-like object to validate
        max_size: Maximum allowed file size in bytes (default: 50MB)
        allowed_extensions: List of allowed file extensions (default: from ALLOWED_TYPES)

    Returns:
        Tuple of (file_data, sanitized_filename, extension)

    Raises:
        FileTooLargeError: If file exceeds size limit
        InvalidFileTypeError: If file type not in allowed list
        ExtensionMismatchError: If extension doesn't match detected type
        MalformedFileError: If file structure is invalid
        FileValidationError: For other validation failures
    """
    if allowed_extensions is None:
        allowed_extensions = list(ALLOWED_TYPES.values())

    # Get original filename for sanitization
    original_filename = getattr(uploaded_file, "name", "unnamed_file")
    sanitized_filename = sanitize_filename(original_filename)

    # Get declared extension from filename
    declared_ext = Path(sanitized_filename).suffix.lower()

    logger.info(f"Starting validation for: {sanitized_filename}")

    # Step 1: Validate size and read file data
    try:
        size = validate_file_size(uploaded_file, max_size)
    except FileTooLargeError:
        raise
    except Exception as e:
        logger.error(f"Size validation failed: {e}")
        raise

    # Reset file pointer and read all data for type detection
    try:
        uploaded_file.seek(0)
        file_data = uploaded_file.read()
    except Exception as e:
        logger.error(f"Failed to read file data: {e}")
        raise FileValidationError(f"Failed to read file data: {e}") from e

    logger.debug(f"File data read: {len(file_data)} bytes")

    # Step 2: Detect file type
    detected_ext, mime_type, confidence = detect_file_type(file_data)

    # Ensure extension has leading dot for comparison
    if detected_ext and not detected_ext.startswith("."):
        detected_ext = "." + detected_ext

    # Step 3: Check confidence threshold with tiered approach
    # High confidence files (0.7+) are trusted
    # Medium confidence files (0.4+) can pass if extension matches and structure validates
    # Low confidence files (<0.4) are rejected
    if confidence < MIN_CONFIDENCE_WITH_VALIDATION:
        logger.warning(
            f"File type confidence too low: {confidence:.2f} (minimum: {MIN_CONFIDENCE_WITH_VALIDATION})"
        )
        raise InvalidFileTypeError(
            mime_type, f"{detected_ext} (low confidence: {confidence:.2f})"
        )
    
    # For medium confidence (0.4-0.7), require extension match for additional trust
    if confidence < MIN_CONFIDENCE:
        if declared_ext and declared_ext.lower() != detected_ext.lower():
            logger.warning(
                f"Medium confidence ({confidence:.2f}) but extension mismatch: "
                f"declared '{declared_ext}' vs detected '{detected_ext}'"
            )
            raise ExtensionMismatchError(declared_ext, detected_ext)
        logger.debug(
            f"Medium confidence ({confidence:.2f}) accepted with matching extension"
        )

    # Step 4: Check if file type is allowed
    if detected_ext.lower() not in [ext.lower() for ext in allowed_extensions]:
        logger.warning(
            f"File type not allowed: {detected_ext} (mime: {mime_type}). "
            f"Allowed: {allowed_extensions}"
        )
        raise InvalidFileTypeError(mime_type, detected_ext)

    # Step 5: Validate extension matches detected type
    if declared_ext and declared_ext.lower() != detected_ext.lower():
        # Allow some special cases (e.g., .docx vs .docx with different case)
        common_mappings = {
            ".doc": ".docx",  # Sometimes old .doc files are detected as docx
        }
        if common_mappings.get(declared_ext) != detected_ext.lower():
            logger.warning(
                f"Extension mismatch: declared '{declared_ext}' vs detected '{detected_ext}'"
            )
            raise ExtensionMismatchError(declared_ext, detected_ext)

    # Step 6: Structure validation for specific file types
    detected_ext_lower = detected_ext.lower()

    if detected_ext_lower == ".pdf":
        validate_pdf_structure(file_data)
    elif detected_ext_lower in (".docx", ".odt"):
        is_valid, file_type = validate_zip_structure(file_data)
        if not is_valid:
            raise MalformedFileError(f"Invalid {detected_ext} file structure")

        # Additional check: ensure detected type matches expected structure
        expected_type = "docx" if detected_ext_lower == ".docx" else "odt"
        if file_type != expected_type and file_type != "unknown":
            logger.warning(
                f"Structure mismatch: detected {detected_ext} but ZIP contains {file_type}"
            )
            raise MalformedFileError(
                f"File claims to be {detected_ext} but structure indicates {file_type}"
            )

    logger.info(
        f"File validation successful: {sanitized_filename} ({detected_ext}, "
        f"confidence: {confidence:.2f})"
    )

    return (file_data, sanitized_filename, detected_ext)


# =============================================================================
# Convenience Functions
# =============================================================================


def is_allowed_file_type(mime_type: str) -> bool:
    """Check if a MIME type is in the allowed list.

    Args:
        mime_type: MIME type to check

    Returns:
        True if the MIME type is allowed
    """
    return mime_type in ALLOWED_TYPES


def get_extension_for_mime_type(mime_type: str) -> Optional[str]:
    """Get the file extension for a MIME type.

    Args:
        mime_type: MIME type to look up

    Returns:
        File extension including the dot, or None if not found
    """
    return ALLOWED_TYPES.get(mime_type)


def get_mime_type_for_extension(extension: str) -> Optional[str]:
    """Get the MIME type for a file extension.

    Args:
        extension: File extension (with or without leading dot)

    Returns:
        MIME type, or None if not found
    """
    # Ensure extension has leading dot
    if not extension.startswith("."):
        extension = "." + extension

    for mime, ext in ALLOWED_TYPES.items():
        if ext.lower() == extension.lower():
            return mime

    return None
