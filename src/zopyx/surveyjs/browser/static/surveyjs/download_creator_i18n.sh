#!/bin/bash
# Script to download SurveyJS Creator i18n files locally
# Usage: ./download_creator_i18n.sh [language-name]
# Example: ./download_creator_i18n.sh german

CREATOR_VERSION="latest"
BASE_URL="https://unpkg.com/survey-creator-core@${CREATOR_VERSION}/i18n"

if [ -z "$1" ]; then
  echo "Downloading commonly used creator i18n files..."
  languages=(german french spanish italian dutch portuguese polish russian japanese simplified-chinese)
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
curl -sL "https://unpkg.com/browse/survey-creator-core@latest/i18n/" | grep -oP '(?<=files/i18n/)[^.]*(?=\.js)' | sort -u | grep -v "\.min$"
