#!/bin/bash
set -e


echo "Initializing demo Plone site..."
../bin/instance run ../scripts/init_plone.py

echo "Starting Plone instance in background..."
../bin/instance start

echo "Waiting for Plone to be ready on http://localhost:8082/demo..."
until curl -fail http://localhost:8082/demo/en; do
    echo -n "."
    sleep 1
done
echo "Plone is ready!"
