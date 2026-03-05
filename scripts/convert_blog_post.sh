#!/bin/bash
#
# Convert BLOG_POST_CUSY_OUTPUT.md to PDF (via Typst) and reStructuredText
#
# Usage:
#   ./scripts/convert_blog_post.sh [output_dir]
#
# Requirements:
#   - pandoc (https://pandoc.org/)
#   - typst (for PDF generation, https://typst.app/)
#

set -euo pipefail

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Input file
INPUT_FILE="${PROJECT_ROOT}/BLOG_POST_CUSY_OUTPUT.md"

# Output directory (default to project root, or use first argument)
OUTPUT_DIR="${1:-${PROJECT_ROOT}}"
mkdir -p "${OUTPUT_DIR}"

# Output files
OUTPUT_PDF="${OUTPUT_DIR}/BLOG_POST_CUSY.pdf"
OUTPUT_RST="${OUTPUT_DIR}/BLOG_POST_CUSY.rst"

# Check if input file exists
if [[ ! -f "${INPUT_FILE}" ]]; then
    echo "Error: Input file not found: ${INPUT_FILE}" >&2
    exit 1
fi

# Check dependencies
check_command() {
    if ! command -v "$1" &>/dev/null; then
        echo "Error: Required command '$1' not found. Please install $2" >&2
        exit 1
    fi
}

echo "=== Blog Post Converter ==="
echo "Input:  ${INPUT_FILE}"
echo "Output: ${OUTPUT_DIR}"
echo ""

# Check for pandoc
check_command "pandoc" "pandoc (https://pandoc.org/installing.html)"

# Convert to reStructuredText
echo "→ Converting to reStructuredText..."
pandoc \
    --from markdown \
    --to rst \
    --output "${OUTPUT_RST}" \
    --wrap=none \
    --standalone \
    "${INPUT_FILE}"

echo "  ✓ Created: ${OUTPUT_RST}"

# Convert to PDF via Typst
echo ""
echo "→ Converting to PDF (via Typst)..."

# Check for typst
if command -v typst &>/dev/null; then
    pandoc \
        --from markdown \
        --to typst \
        --output "${OUTPUT_DIR}/.temp.typ" \
        --wrap=none \
        --standalone \
        "${INPUT_FILE}"
    
    # Compile with typst
    typst compile "${OUTPUT_DIR}/.temp.typ" "${OUTPUT_PDF}"
    rm -f "${OUTPUT_DIR}/.temp.typ"
    
    echo "  ✓ Created: ${OUTPUT_PDF}"
else
    echo "  ⚠ Warning: typst not found. Skipping PDF generation." >&2
    echo "    Install typst: https://typst.app/docs/install/" >&2
    
    # Fallback: try to generate PDF via other methods
    if command -v pdflatex &>/dev/null || command -v xelatex &>/dev/null; then
        echo "  → Falling back to LaTeX PDF generation..."
        pandoc \
            --from markdown \
            --to pdf \
            --output "${OUTPUT_PDF}" \
            --standalone \
            "${INPUT_FILE}" 2>/dev/null || {
            echo "  ✗ PDF generation failed. Install typst or LaTeX for PDF output." >&2
        }
    else
        echo "  ✗ No PDF backend available (install typst or LaTeX)" >&2
    fi
fi

echo ""
echo "=== Conversion complete ==="

# List output files
if [[ -f "${OUTPUT_RST}" ]]; then
    echo "  RST: ${OUTPUT_RST} ($(stat -c%s "${OUTPUT_RST}" 2>/dev/null || stat -f%z "${OUTPUT_RST}" 2>/dev/null || echo "?") bytes)"
fi
if [[ -f "${OUTPUT_PDF}" ]]; then
    echo "  PDF: ${OUTPUT_PDF} ($(stat -c%s "${OUTPUT_PDF}" 2>/dev/null || stat -f%z "${OUTPUT_PDF}" 2>/dev/null || echo "?") bytes)"
fi
