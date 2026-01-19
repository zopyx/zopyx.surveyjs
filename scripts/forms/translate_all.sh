#!/usr/bin/env bash
set -euo pipefail

# Translate *_it|pt|fr|es.{json,html} files in place using uvx llm.

lang_from_suffix() {
  case "$1" in
    it) echo "Italian" ;;
    pt) echo "Portuguese" ;;
    fr) echo "French" ;;
    es) echo "Spanish" ;;
    *) return 1 ;;
  esac
}

shopt -s nullglob
for file in *_it.json *_it.html *_pt.json *_pt.html *_fr.json *_fr.html *_es.json *_es.html; do
  base="${file%.*}"
  suffix="${base##*_}"
  lang="$(lang_from_suffix "$suffix")"

  tmp="${file}.tmp"
  cat "$file" | uvx llm -s "translate to ${lang}" > "$tmp"
  mv "$tmp" "$file"
  echo "Translated $file -> $lang"

done
