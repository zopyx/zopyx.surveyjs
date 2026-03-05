#!/bin/bash
set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Project root is one level up from playwright-tests
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Stopping Plone instance..."
"$PROJECT_ROOT/bin/instance" stop
echo "Plone instance stopped."
