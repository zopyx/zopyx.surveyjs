#!/bin/bash
#
# Run Playwright screenshot automation with automatic Plone management
# 
# This script checks if Plone is running. If not, it starts Plone in background,
# runs the tests, and then stops Plone. If Plone is already running, it leaves
# it running after tests complete.
#
# Usage:
#   ./run-screenshots-with-plone.sh              # Run all screenshots
#   ./run-screenshots-with-plone.sh survey       # Run only survey screenshots
#   ./run-screenshots-with-plone.sh psf          # Run only PSF screenshots
#   ./run-screenshots-with-plone.sh cp           # Run only control panel screenshots
#   ./run-screenshots-with-plone.sh headed       # Run with visible browser
#

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to script directory so relative paths work
cd "$SCRIPT_DIR"

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

echo -e "${GREEN}Playwright Screenshot Automation with Plone Management${NC}"
echo "========================================================="
echo ""
echo "Configuration:"
echo "  PLONE_URL:      $PLONE_URL"
echo "  PLONE_USER:     $PLONE_ADMIN_USER"
echo "  SCREENSHOT_DIR: $SCREENSHOT_DIR"
echo ""

# Check if Plone is already running
echo -e "${YELLOW}Checking if Plone is running at $PLONE_URL...${NC}"
PLONE_WAS_RUNNING=false
if curl -s --max-time 5 "$PLONE_URL" > /dev/null 2>&1; then
    echo -e "${GREEN}Plone is already running.${NC}"
    PLONE_WAS_RUNNING=true
else
    echo -e "${YELLOW}Plone is not running. Starting in background...${NC}"
    
    # Start Plone using the existing script
    if [ -f "./start_plone_for_tests.sh" ]; then
        ./start_plone_for_tests.sh
    else
        echo -e "${RED}Error: start_plone_for_tests.sh not found${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}Plone started successfully.${NC}"
fi
echo ""

# Function to stop Plone if we started it
cleanup() {
    if [ "$PLONE_WAS_RUNNING" = false ]; then
        echo ""
        echo -e "${YELLOW}Stopping Plone (was started by this script)...${NC}"
        if [ -f "./stop_plone_for_tests.sh" ]; then
            ./stop_plone_for_tests.sh || true
        fi
        echo -e "${GREEN}Plone stopped.${NC}"
    else
        echo ""
        echo -e "${BLUE}Plone was already running before tests - leaving it running.${NC}"
    fi
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Now run the actual screenshot tests
echo -e "${YELLOW}Running screenshot tests...${NC}"
echo ""

# Parse arguments and pass to run-screenshots.sh
CATEGORY="${1:-all}"

./run-screenshots.sh "$CATEGORY"

echo ""
echo -e "${GREEN}All done!${NC}"
