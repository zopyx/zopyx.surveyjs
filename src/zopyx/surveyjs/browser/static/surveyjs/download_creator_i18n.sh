#!/bin/bash
# Script to download SurveyJS Creator i18n files locally
# In v3, a combined survey-creator-core.i18n.min.js is also available.
# Usage: ./download_creator_i18n.sh [language-name]
# Example: ./download_creator_i18n.sh german

CREATOR_VERSION="3.0.0"
BASE_URL="https://unpkg.com/survey-creator-core@${CREATOR_VERSION}/i18n"

if [ -z "$1" ]; then
  echo "Downloading commonly used creator i18n files..."
  languages=(arabic bulgarian burmese catalan croatian czech danish dutch english finnish french german greek haitian-creole hebrew hungarian indonesian italian japanese korean malay mongolian norwegian persian polish portuguese romanian russian simplified-chinese slovak slovenian spanish swedish tajik thai traditional-chinese turkish)

else
  echo "Downloading: $1"
  languages=("$1")
fi

for lang in "${languages[@]}"; do
  echo "Downloading ${lang}.js..."
  curl -sL "${BASE_URL}/${lang}.js" -o "survey-creator-i18n-${lang}.js"
  size=$(wc -c < "survey-creator-i18n-${lang}.js")
  if [ "$size" -lt 1000 ]; then
    echo "  ⚠ Warning: ${lang}.js seems too small (${size} bytes), may not exist"
    cat "survey-creator-i18n-${lang}.js"
    rm "survey-creator-i18n-${lang}.js"
  else
    echo "  ✓ Downloaded ${lang}.js (${size} bytes)"
  fi
done

echo ""
echo "Available languages on unpkg:"
curl -sL "https://unpkg.com/browse/survey-creator-core@${CREATOR_VERSION}/i18n/" | grep -oP '(?<=files/i18n/)[^.]*(?=\.js)' | sort -u | grep -v "\.min$"
