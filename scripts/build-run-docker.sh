#!/bin/bash

cd /home/privacyforms/zopyx.surveyjs

make build
make stop
make run-detached
