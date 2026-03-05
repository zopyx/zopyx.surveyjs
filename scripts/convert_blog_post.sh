#!/bin/bash
#
# Convert BLOG_POST_CUSY_OUTPUT.md to PDF (via Typst) and reStructuredText
#
# Usage:
#   ./scripts/convert_blog_post.sh [input_file] [output_dir]
#
# Arguments:
#   input_file  - Input markdown file (default: BLOG_POST_CUSY_OUTPUT.md)
#   output_dir  - Output directory (default: same as input file directory)
#
# Requirements:
#   - pandoc (https://pandoc.org/)
#   - typst (for PDF generation, https://typst.app/)
#

set -euo pipefail

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default input file
DEFAULT_INPUT="${PROJECT_ROOT}/BLOG_POST_CUSY_OUTPUT.md"

# Parse arguments
INPUT_FILE="${1:-${DEFAULT_INPUT}}"

# If first arg is a directory (not a file), treat it as output_dir
if [[ $# -gt 0 ]] && [[ -d "$1" ]]; then
    INPUT_FILE="${DEFAULT_INPUT}"
    OUTPUT_DIR="$1"
elif [[ -n "${2:-}" ]]; then
    OUTPUT_DIR="$2"
else
    # Default output directory is the directory containing the input file
    OUTPUT_DIR="$(dirname "${INPUT_FILE}")"
fi

# Resolve to absolute paths
INPUT_FILE="$(cd "$(dirname "${INPUT_FILE}")" && pwd)/$(basename "${INPUT_FILE}")"
OUTPUT_DIR="$(mkdir -p "${OUTPUT_DIR}" && cd "${OUTPUT_DIR}" && pwd)"

# Derive output filenames from input filename (without extension)
BASENAME="$(basename "${INPUT_FILE}" .md)"
BASENAME="$(basename "${BASENAME}" .markdown)"
OUTPUT_PDF="${OUTPUT_DIR}/${BASENAME}.pdf"
OUTPUT_RST="${OUTPUT_DIR}/${BASENAME}.rst"

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
        --output "${OUTPUT_DIR}/.temp_${BASENAME}.typ" \
        --wrap=none \
        --standalone \
        "${INPUT_FILE}"
    
    # Compile with typst
    typst compile "${OUTPUT_DIR}/.temp_${BASENAME}.typ" "${OUTPUT_PDF}"
    rm -f "${OUTPUT_DIR}/.temp_${BASENAME}.typ"
    
    echo "  ✓ Created: ${OUTPUT_PDF}"
else
    echo "  ⚠ Warning: typst not found. Skipping PDF generation." >&2
    echo "    Install typst: https://typst.app/docs/install/" >&2
    
    # Fallback: try to generate PDF via LaTeX
    if command -v pdflatex &>/dev/null || command -v xelatex &>/dev/null; then
        echo "  → Falling back to LaTeX PDF generation..."
        pandoc \
            --from markdown \
            --to pdf \
            --output "${OUTPUT_PDF}" \
            --standalone \
            "${INPUT_FILE}" 2>/dev/null && {
            echo "  ✓ Created: ${OUTPUT_PDF}"
        } || {
            echo "  ✗ PDF generation failed." >&2
        }
    else
        echo "  ✗ No PDF backend available (install typst or LaTeX)" >&2
    fi
fi

echo ""
echo "=== Conversion complete ==="

# List output files with sizes
if [[ -f "${OUTPUT_RST}" ]]; then
    SIZE=$(stat -c%s "${OUTPUT_RST}" 2>/dev/null || stat -f%z "${OUTPUT_RST}" 2>/dev/null || echo "?")
    echo "  RST: ${OUTPUT_RST} (${SIZE} bytes)"
fi
if [[ -f "${OUTPUT_PDF}" ]]; then
    SIZE=$(stat -c%s "${OUTPUT_PDF}" 2>/dev/null || stat -f%z "${OUTPUT_PDF}" 2>/dev/null || echo "?")
    echo "  PDF: ${OUTPUT_PDF} (${SIZE} bytes)"
fi
