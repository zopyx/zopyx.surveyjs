#!/bin/bash
set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Project root is one level up from playwright-tests
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Initializing demo Plone site..."
"$PROJECT_ROOT/bin/instance" run "$PROJECT_ROOT/scripts/init_plone.py"

echo "Starting Plone instance in background..."
"$PROJECT_ROOT/bin/instance" start

echo "Waiting for Plone to be ready on http://localhost:8082/demo..."
until curl -fail http://localhost:8082/demo/en > /dev/null 2>&1; do
    echo -n "."
    sleep 1
done
echo "Plone is ready!"
