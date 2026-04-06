# File Validation Library Research
## Comparison of Python Libraries for File Type Detection

**Research Date:** 2026-04-06

---

## Executive Summary

After researching available Python libraries for file validation, **`puremagic`** emerges as the best choice for this project due to:
- Pure Python (no C extensions or system dependencies)
- Cross-platform compatibility
- Active maintenance (supports Python 3.12+)
- Confidence scoring for matches
- Zero runtime dependencies

---

## Library Comparison

| Library | Pure Python | Dependencies | Speed | File Types | Confidence Score | Maintenance |
|---------|-------------|--------------|-------|------------|------------------|-------------|
| **puremagic** | ✅ Yes | None | Fast | ~1600+ | ✅ Yes | ⭐ Active |
| **filetype** | ✅ Yes | None | Fast | ~100+ | ❌ No | ⚠️ Moderate |
| **python-magic** | ❌ No | libmagic C lib | Medium | 5000+ | ❌ No | ⭐ Active |

---

## Detailed Analysis

### 1. puremagic ⭐ **RECOMMENDED**

**GitHub:** https://github.com/cdgriffith/puremagic  
**PyPI:** https://pypi.org/project/puremagic/  
**License:** MIT

#### Pros
- ✅ **Zero dependencies** - Pure Python implementation
- ✅ **Cross-platform** - Works on Windows, Linux, macOS without system libraries
- ✅ **Fast** - Faster than python-magic/libmagic
- ✅ **Confidence scoring** - Returns confidence levels for matches
- ✅ **Multiple matches** - Can return all possible file types with confidence
- ✅ **Active development** - Supports Python 3.12+, regular updates
- ✅ **Deep scan** - Content-aware analysis beyond simple magic numbers (v2.0+)

#### Cons
- ⚠️ Fewer file types than python-magic (~1600 vs ~5000)
- ⚠️ No multilingual comments in descriptions

#### Usage Example
```python
import puremagic

# Simple detection
ext = puremagic.from_file("document.pdf")
# Returns: '.pdf'

mime = puremagic.from_file("document.pdf", mime=True)
# Returns: 'application/pdf'

# Detailed analysis with confidence
matches = puremagic.magic_file("document.pdf")
# Returns: [
#   ['.pdf', 'application/pdf', 'PDF document', 0.9],
#   ['.pdf', '', 'PDF v1.4', 0.8]
# ]

# From bytes (for uploaded files)
with open("document.pdf", "rb") as f:
    header = f.read(4096)
    result = puremagic.magic_string(header)
```

#### Installation
```bash
pip install puremagic
```

---

### 2. filetype

**GitHub:** https://github.com/h2non/filetype.py  
**PyPI:** https://pypi.org/project/filetype/  
**License:** MIT

#### Pros
- ✅ Pure Python, no dependencies
- ✅ Fast and lightweight
- ✅ Simple API
- ✅ Only needs first 261 bytes

#### Cons
- ❌ **No confidence scoring** - Binary match/no match only
- ❌ **Fewer file types** - Limited set compared to puremagic
- ❌ Less active maintenance
- ❌ No detailed file information

#### Usage Example
```python
import filetype

kind = filetype.guess("document.pdf")
if kind is None:
    print("Unknown file type")
else:
    print(kind.extension)  # 'pdf'
    print(kind.mime)       # 'application/pdf'

# From bytes
kind = filetype.guess(header_bytes)
```

#### Installation
```bash
pip install filetype
```

---

### 3. python-magic

**GitHub:** https://github.com/ahupp/python-magic  
**PyPI:** https://pypi.org/project/python-magic/  
**License:** MIT

#### Pros
- ✅ Most comprehensive file type database (~5000 types)
- ✅ Uses system's libmagic (same as Unix `file` command)
- ✅ Well-established and widely used
- ✅ Detailed file descriptions

#### Cons
- ❌ **Requires libmagic C library** - System dependency
- ❌ **Installation complexity**:
  - Ubuntu/Debian: `apt-get install libmagic1`
  - macOS: `brew install libmagic`
  - Windows: Requires special handling
- ❌ Slower than pure Python alternatives
- ❌ No confidence scoring
- ❌ Deployment complications in containers

#### Usage Example
```python
import magic

# MIME type
mime = magic.from_file("document.pdf", mime=True)
# Returns: 'application/pdf'

# Human-readable description
desc = magic.from_file("document.pdf")
# Returns: 'PDF document, version 1.4'

# From buffer
mime = magic.from_buffer(header_bytes, mime=True)
```

#### Installation
```bash
# Ubuntu/Debian
sudo apt-get install libmagic1
pip install python-magic

# macOS
brew install libmagic
pip install python-magic

# Windows
pip install python-magic-bin  # Special package with DLLs
```

---

## Recommendation

### Primary Choice: `puremagic`

**Rationale:**

1. **Deployment Simplicity** - Zero system dependencies means easier deployment in:
   - Docker containers
   - Virtualenv/Pip environments
   - CI/CD pipelines
   - Shared hosting environments

2. **Cross-Platform** - Works identically on:
   - Development machines (macOS/Windows/Linux)
   - Production servers
   - CI runners

3. **Security** - Pure Python means:
   - No C extension vulnerabilities
   - No shared library injection risks
   - Audit-friendly code

4. **Confidence Scoring** - Critical for security decisions:
   ```python
   matches = puremagic.magic_file(uploaded_file)
   best_match = matches[0]  # Highest confidence
   if best_match.confidence < 0.8:
       reject_upload("Uncertain file type")
   ```

5. **Active Maintenance** - Regular updates, Python 3.12+ support

### Alternative: `filetype`

Consider if:
- You only need basic MIME type detection
- File set is limited to common types (images, videos, documents)
- Confidence scoring not needed

### Not Recommended: `python-magic`

Avoid because:
- System dependency complicates deployment
- No confidence scoring for uncertain matches
- Deployment issues in restricted environments

---

## Implementation with puremagic

```python
# src/zopyx/surveyjs/file_validation.py

import puremagic
from puremagic import PureMagicWithConfidence
import zipfile
import io
from pathlib import Path


class FileValidationError(Exception):
    """Base exception for file validation errors."""
    pass


class FileTypeMismatchError(FileValidationError):
    """File type doesn't match claimed extension."""
    pass


class UnsupportedFileTypeError(FileValidationError):
    """File type not in allowed list."""
    pass


def validate_file_type(
    file_data: bytes,
    claimed_extension: str,
    allowed_types: set = None,
    min_confidence: float = 0.7
) -> tuple[str, str]:
    """
    Validate file type using puremagic.
    
    Args:
        file_data: First few KB of file content
        claimed_extension: Extension from filename (e.g., '.pdf')
        allowed_types: Set of allowed MIME types
        min_confidence: Minimum confidence threshold (0.0-1.0)
        
    Returns:
        Tuple of (detected_extension, mime_type)
        
    Raises:
        FileTypeMismatchError: If detection confidence too low
        UnsupportedFileTypeError: If type not in allowed list
    """
    if allowed_types is None:
        allowed_types = {
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.oasis.opendocument.text',
            'text/html',
        }
    
    # Get all possible matches with confidence
    matches = puremagic.magic_string(file_data)
    
    if not matches:
        raise FileTypeMismatchError("Could not determine file type")
    
    # Get best match
    best = matches[0]
    
    # Check confidence threshold
    if best.confidence < min_confidence:
        raise FileTypeMismatchError(
            f"Uncertain file type (confidence: {best.confidence:.2f})"
        )
    
    # Verify claimed extension matches detected
    detected_ext = best.extension.lower()
    claimed = claimed_extension.lower()
    
    # Handle .htm vs .html equivalence
    if not (detected_ext == claimed or 
            (detected_ext == '.html' and claimed == '.htm')):
        raise FileTypeMismatchError(
            f"Extension mismatch: claims '{claimed}' but detected '{detected_ext}'"
        )
    
    # Check MIME type is allowed
    if best.mime_type not in allowed_types:
        raise UnsupportedFileTypeError(
            f"File type '{best.mime_type}' not allowed"
        )
    
    return detected_ext, best.mime_type


def is_valid_pdf(file_data: bytes) -> bool:
    """Additional PDF structure validation."""
    # puremagic will detect PDF, but we can add extra checks
    if not file_data.startswith(b'%PDF-'):
        return False
    
    # Check version
    header = file_data[:8].decode('latin-1', errors='ignore')
    if not any(header.startswith(f'%PDF-{v}') for v in ['1.', '2.']):
        return False
    
    # Check for EOF marker
    if b'%%EOF' not in file_data[-1024:]:
        return False
    
    return True


def is_valid_docx(file_data: bytes) -> bool:
    """Validate DOCX structure (ZIP with specific content)."""
    try:
        with zipfile.ZipFile(io.BytesIO(file_data)) as zf:
            required_files = {'[Content_Types].xml', 'word/document.xml'}
            return required_files.issubset(set(zf.namelist()))
    except zipfile.BadZipFile:
        return False
```

---

## Dependencies Comparison

### puremagic
```
puremagic==1.30
```
**Total dependencies:** 1 (itself)

### filetype
```
filetype==1.2.0
```
**Total dependencies:** 1 (itself)

### python-magic
```
# Ubuntu/Debian
apt-get install libmagic1  # System package!
pip install python-magic

# Or Windows
pip install python-magic-bin  # Includes DLLs
```
**Total dependencies:** System library + Python wrapper

---

## Conclusion

| Use Case | Recommendation |
|----------|---------------|
| **Production deployment** | `puremagic` - Zero system dependencies |
| **Security-critical** | `puremagic` - Confidence scoring for uncertain matches |
| **Simple projects** | `filetype` - Minimal API |
| **Comprehensive detection** | `python-magic` - If you can manage system deps |

**Final Recommendation:** Use **`puremagic`** for the zopyx.surveyjs project.

---

## References

- [puremagic GitHub](https://github.com/cdgriffith/puremagic)
- [filetype GitHub](https://github.com/h2non/filetype.py)
- [python-magic GitHub](https://github.com/ahupp/python-magic)
- [Python-Magic vs PureMagic Comparison](https://codecut.ai/python-magic-file-type-detection/)
