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

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default configuration
PLONE_URL="${PLONE_URL:-http://localhost:8082/demo}"
PLONE_ADMIN_USER="${PLONE_ADMIN_USER:-admin}"
PLONE_ADMIN_PASS="${PLONE_ADMIN_PASS:-admin}"
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

# Determine which tests to run
case "$CATEGORY" in
    survey)
        echo -e "${YELLOW}Running survey screenshots...${NC}"
        npx playwright test screenshots/survey-screenshots.spec.ts --config=screenshot.config.ts $HEADED
        ;;
    psf)
        echo -e "${YELLOW}Running PSF screenshots...${NC}"
        npx playwright test screenshots/psf-screenshots.spec.ts --config=screenshot.config.ts $HEADED
        ;;
    cp|controlpanel)
        echo -e "${YELLOW}Running control panel screenshots...${NC}"
        npx playwright test screenshots/controlpanel-screenshots.spec.ts --config=screenshot.config.ts $HEADED
        ;;
    all|*)
        echo -e "${YELLOW}Running all screenshots...${NC}"
        npx playwright test --config=screenshot.config.ts $HEADED
        ;;
esac

echo ""
echo -e "${GREEN}Screenshots complete!${NC}"
echo "Output directory: $(realpath "$SCREENSHOT_DIR" 2>/dev/null || echo "$SCREENSHOT_DIR")"
echo ""
echo "View report:"
echo "  npx playwright show-report $(realpath "$SCREENSHOT_DIR" 2>/dev/null || echo "$SCREENSHOT_DIR")/report"
