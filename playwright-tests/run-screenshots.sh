#!/bin/bash
#
# Run Playwright screenshot automation
# 
# Usage:
#   ./run-screenshots.sh              # Run all screenshots
#   ./run-screenshots.sh survey       # Run only survey screenshots
#   ./run-screenshots.sh psf          # Run only PSF screenshots
#   ./run-screenshots.sh cp           # Run only control panel screenshots
#   ./run-screenshots.sh headed       # Run with visible browser
#

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
PLONE_URL="${PLONE_URL:-http://localhost:8082/demo}"
PLONE_ADMIN_USER="${PLONE_ADMIN_USER:-admin2}"
PLONE_ADMIN_PASS="${PLONE_ADMIN_PASS:-2admin}"
SCREENSHOT_DIR="${SCREENSHOT_DIR:-./screenshots/output}"

export PLONE_URL
export PLONE_ADMIN_USER
export PLONE_ADMIN_PASS
export SCREENSHOT_DIR

echo -e "${GREEN}Playwright Screenshot Automation${NC}"
echo "================================"
echo ""
echo "Configuration:"
echo "  PLONE_URL:      $PLONE_URL"
echo "  PLONE_USER:     $PLONE_ADMIN_USER"
echo "  SCREENSHOT_DIR: $SCREENSHOT_DIR"
echo ""

# Check if Plone is running
echo -e "${YELLOW}Checking if Plone is running at $PLONE_URL...${NC}"
if ! curl -s --max-time 5 "$PLONE_URL" > /dev/null 2>&1; then
    echo -e "${RED}Error: Plone is not running at $PLONE_URL${NC}"
    echo "Please start Plone first:"
    echo "  ./start_plone_for_tests.sh"
    exit 1
fi
echo -e "${GREEN}Plone is running.${NC}"
echo ""

# Parse arguments
CATEGORY="${1:-all}"
HEADED=""

if [ "$CATEGORY" = "headed" ]; then
    HEADED="--headed"
    CATEGORY="${2:-all}"
fi

# Track exit code
EXIT_CODE=0

# Determine which tests to run
case "$CATEGORY" in
    survey)
        echo -e "${YELLOW}Running survey screenshots...${NC}"
        npx playwright test screenshots/survey-screenshots.spec.ts --config=screenshot.config.ts $HEADED
        EXIT_CODE=$?
        ;;
    psf)
        echo -e "${YELLOW}Running PSF screenshots...${NC}"
        npx playwright test screenshots/psf-screenshots.spec.ts --config=screenshot.config.ts $HEADED
        EXIT_CODE=$?
        ;;
    cp|controlpanel)
        echo -e "${YELLOW}Running control panel screenshots...${NC}"
        npx playwright test screenshots/controlpanel-screenshots.spec.ts --config=screenshot.config.ts $HEADED
        EXIT_CODE=$?
        ;;
    all|*)
        echo -e "${YELLOW}Running all screenshots...${NC}"
        npx playwright test --config=screenshot.config.ts $HEADED
        EXIT_CODE=$?
        ;;
esac

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Screenshots complete!${NC}"
else
    echo -e "${RED}Some tests failed!${NC}"
    echo ""
    echo -e "${YELLOW}Error artifacts location:${NC}"
    echo "  Screenshots: $SCREENSHOT_DIR/test-results/"
    echo "  Videos:      $SCREENSHOT_DIR/test-results/"
    echo ""
    echo -e "${BLUE}Tip: Screenshots and videos are automatically captured on test failures.${NC}"
fi
echo "Output directory: $(realpath "$SCREENSHOT_DIR" 2>/dev/null || echo "$SCREENSHOT_DIR")"
echo ""
echo "View report:"
echo "  npx playwright show-report $(realpath "$SCREENSHOT_DIR" 2>/dev/null || echo "$SCREENSHOT_DIR")/report"

exit $EXIT_CODE
