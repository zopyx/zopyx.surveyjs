#!/usr/bin/env bash
#
# Install a Plone 6.2 site with zopyx.surveyjs using ONLY uv (no buildout).
#
# Verified end-to-end against:
#   - Plone 6.2.1 (pip distribution)
#   - Python 3.13
#   - zopyx.surveyjs 1.0a4 + privacyforms.theme/ai/pdf from git
#
# Usage:
#   ./uv-plone62-setup.sh [WORKDIR]
#   WORKDIR defaults to ./plone62-uv
#
set -euo pipefail

WORKDIR="${1:-./plone62-uv}"
SITE_ID="${SITE_ID:-Plone}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-adminpw}"
PORT="${PORT:-8080}"
BASE_URL="http://127.0.0.1:${PORT}"

PYTHON_VERSION="3.13"
PLONE_VERSION="6.2.1"   # pip meta-package version (or use Plone==6.2 for latest 6.2.x)
DISTRIBUTION="classic"  # Plone 6.2 distributions: classic | volto

echo "==> Creating workdir ${WORKDIR}"
mkdir -p "${WORKDIR}"
cd "${WORKDIR}"

echo "==> Creating uv venv (Python ${PYTHON_VERSION})"
uv venv --python "${PYTHON_VERSION}" .venv

echo "==> Installing Plone ${PLONE_VERSION} via uv (no buildout)"
uv pip install --python .venv/bin/python "Plone==${PLONE_VERSION}"

echo "==> Installing zopyx.surveyjs (editable) and its privacyforms siblings"
uv pip install --python .venv/bin/python -e ../src
uv pip install --python .venv/bin/python \
    "privacyforms.theme @ git+https://github.com/zopyx/privacyforms.theme.git" \
    "privacyforms.ai @ git+https://github.com/zopyx/privacyforms.ai.git" \
    "privacyforms.pdf @ git+https://github.com/zopyx/privacyforms.pdf.git"

echo "==> Creating Zope WSGI instance"
.venv/bin/mkwsgiinstance -d instance -u "${ADMIN_USER}:${ADMIN_PASS}"

echo "==> Starting Plone (background)"
.venv/bin/runwsgi instance/etc/zope.ini > instance/var/runwsgi.log 2>&1 &
RUNWSGI_PID=$!

echo "==> Waiting for Plone to become ready"
for i in $(seq 1 120); do
    if curl -s --max-time 5 "${BASE_URL}/" > /dev/null 2>&1; then
        echo "    ready after ${i}s"
        break
    fi
    if ! kill -0 "${RUNWSGI_PID}" 2>/dev/null; then
        echo "ERROR: runwsgi exited early; see ${WORKDIR}/instance/var/runwsgi.log"
        exit 1
    fi
    sleep 1
done

echo "==> Creating Plone site '${SITE_ID}' (distribution: ${DISTRIBUTION})"
curl -s -u "${ADMIN_USER}:${ADMIN_PASS}" \
    -X POST "${BASE_URL}/++api++/@sites/${DISTRIBUTION}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d "{\"site_id\": \"${SITE_ID}\", \"title\": \"${SITE_ID}\", \"description\": \"\", \"default_language\": \"en\", \"portal_timezone\": \"UTC\"}"

echo
echo "==> Installing zopyx.surveyjs add-on"
curl -s -u "${ADMIN_USER}:${ADMIN_PASS}" \
    -X POST -H "Accept: application/json" \
    "${BASE_URL}/${SITE_ID}/@addons/zopyx.surveyjs/install" \
    -o /dev/null -w "    addon install: HTTP %{http_code}\n"

echo
echo "==> Done."
echo "    Site:    ${BASE_URL}/${SITE_ID}"
echo "    ZMI:     ${BASE_URL}/manage"
echo "    User:    ${ADMIN_USER} / ${ADMIN_PASS}"
echo "    Server:  PID ${RUNWSGI_PID} (log: ${WORKDIR}/instance/var/runwsgi.log)"
echo "    Stop:    kill ${RUNWSGI_PID}"
