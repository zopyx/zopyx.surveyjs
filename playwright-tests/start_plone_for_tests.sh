#!/bin/bash
set -e

echo "Ensuring Plone instance is built..."
../../bin/buildout

echo "Initializing demo Plone site..."
../../bin/instance run ../../scripts/init_plone.py

echo "Starting Plone instance in background..."
../../bin/instance start

echo "Waiting for Plone to be ready on http://localhost:8080/demo..."
until curl --output /dev/null --silent --head --fail http://localhost:8080/demo; do
    echo -n "."
    sleep 1
done
echo "Plone is ready!"
