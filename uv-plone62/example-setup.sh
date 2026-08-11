#!/usr/bin/env bash
#
# ============================================================================
#  EXAMPLE: Plone 6.2 + zopyx.surveyjs with uv only (no buildout)
# ============================================================================
#  A readable, step-by-step example script. It does exactly what the
#  README describes, with every step explained. Copy it, adapt the
#  variables at the top, and run it.
#
#  For a more hardened/automated variant see: uv-plone62-setup.sh
#
#  Verified against:
#    - Plone 6.2.1 (pip meta-package)
#    - Python 3.13
#    - zopyx.surveyjs 1.0a4 + privacyforms.theme/ai/pdf (git)
# ============================================================================

set -euo pipefail          # fail fast, no silent errors

# ---------------------------------------------------------------------------
# 0. Configuration - adjust to taste
# ---------------------------------------------------------------------------
WORKDIR="${1:-./plone62-demo}"   # where the venv + instance will live
SITE_ID="${SITE_ID:-Plone}"      # id of the Plone site to create
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-adminpw}"
PORT="${PORT:-8080}"

PYTHON_VERSION="3.13"            # Plone>=3.10, zopyx.surveyjs >=3.12,<3.14
PLONE_VERSION="6.2.1"            # or "6.2" for latest 6.2.x
DISTRIBUTION="classic"           # Plone 6.2: "classic" or "volto"

# zopyx.surveyjs checkout root. Resolved from THIS script's location so it
# works regardless of the current working directory; override with PACKAGE_DIR.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="${PACKAGE_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

BASE_URL="http://127.0.0.1:${PORT}"
AUTH=(-u "${ADMIN_USER}:${ADMIN_PASS}")           # curl auth args
JSON_HDR=(-H "Content-Type: application/json" -H "Accept: application/json")

# ---------------------------------------------------------------------------
# 1. Working directory + virtualenv
# ---------------------------------------------------------------------------
echo "==> [1/8] Creating ${WORKDIR} and uv venv (Python ${PYTHON_VERSION})"
mkdir -p "${WORKDIR}"
cd "${WORKDIR}"
uv venv --python "${PYTHON_VERSION}" .venv

# ---------------------------------------------------------------------------
# 2. Plone itself - the pip "Plone" meta-package, no buildout at all
# ---------------------------------------------------------------------------
echo "==> [2/8] Installing Plone ${PLONE_VERSION} via uv"
uv pip install --python .venv/bin/python "Plone==${PLONE_VERSION}"

# ---------------------------------------------------------------------------
# 3. The add-on + its sibling packages.
#    zopyx.surveyjs imports privacyforms_ai / privacyforms.pdf at ZCML
#    load time, so the three privacyforms.* repos MUST be installed too
#    (buildout used to fetch them via auto-checkout).
# ---------------------------------------------------------------------------
echo "==> [3/8] Installing zopyx.surveyjs (editable) + privacyforms siblings"
echo "    (package dir: ${PACKAGE_DIR})"
if [[ ! -f "${PACKAGE_DIR}/setup.py" && ! -f "${PACKAGE_DIR}/pyproject.toml" ]]; then
    echo "ERROR: ${PACKAGE_DIR} is not the zopyx.surveyjs checkout" >&2
    echo "       (no setup.py/pyproject.toml). Set PACKAGE_DIR to the repo root." >&2
    exit 1
fi
uv pip install --python .venv/bin/python -e "${PACKAGE_DIR}"
uv pip install --python .venv/bin/python \
    "privacyforms.theme @ git+https://github.com/zopyx/privacyforms.theme.git" \
    "privacyforms.ai @ git+https://github.com/zopyx/privacyforms.ai.git" \
    "privacyforms.pdf @ git+https://github.com/zopyx/privacyforms.pdf.git"

# ---------------------------------------------------------------------------
# 4. Zope WSGI instance.
#    IMPORTANT: -u avoids the interactive getpass prompt (which reads from
#    the TTY and would hang this script). Do NOT add <productdistributions>
#    to zope.conf - that directive is gone in Zope 6.
# ---------------------------------------------------------------------------
echo "==> [4/8] Creating Zope instance (admin user: ${ADMIN_USER})"
.venv/bin/mkwsgiinstance -d instance -u "${ADMIN_USER}:${ADMIN_PASS}"

# ---------------------------------------------------------------------------
# 5. Start the WSGI server in the background
# ---------------------------------------------------------------------------
echo "==> [5/8] Starting Plone (background, log: instance/var/runwsgi.log)"
.venv/bin/runwsgi instance/etc/zope.ini > instance/var/runwsgi.log 2>&1 &
RUNWSGI_PID=$!

# ---------------------------------------------------------------------------
# 6. Wait until Plone answers (first boot takes ~20-30s)
# ---------------------------------------------------------------------------
echo "==> [6/8] Waiting for Plone to become ready (first boot can take 2-5 min)"
READY=0
for i in $(seq 1 180); do
    if curl -s --max-time 2 -o /dev/null "${BASE_URL}/" 2>/dev/null; then
        echo "    ready after ~${i}s"
        READY=1
        break
    fi
    if ! kill -0 "${RUNWSGI_PID}" 2>/dev/null; then
        echo "ERROR: runwsgi exited early - see ${WORKDIR}/instance/var/runwsgi.log"
        exit 1
    fi
    # progress marker every 15s
    if (( i % 15 == 0 )); then
        echo "    ... still waiting (${i}s) - check ${WORKDIR}/instance/var/runwsgi.log"
        # If the port is taken by another process, say so instead of hanging.
        if lsof -i ":${PORT}" > /dev/null 2>&1; then
            echo "WARNING: something else already listens on :${PORT}:"
            lsof -i ":${PORT}" | tail -n +2 | head -3
        fi
    fi
    sleep 1
done
if [[ "${READY}" != "1" ]]; then
    echo "ERROR: Plone did not become ready within 180s" >&2
    echo "       see ${WORKDIR}/instance/var/runwsgi.log" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 7. Create the Plone site via the REST API (@sites service).
#    The browser wizard (@@ploneAddSite) is a JS SPA and its hidden field
#    is form.submitted:boolean - use the REST endpoint instead; it runs in
#    a real request context and handles CSRF itself.
# ---------------------------------------------------------------------------
echo "==> [7/8] Creating Plone site '${SITE_ID}' (distribution: ${DISTRIBUTION})"
curl -s "${AUTH[@]}" -X POST "${BASE_URL}/++api++/@sites/${DISTRIBUTION}" \
    "${JSON_HDR[@]}" \
    -d "{\"site_id\": \"${SITE_ID}\", \"title\": \"${SITE_ID}\", \
          \"description\": \"\", \"default_language\": \"en\", \
          \"portal_timezone\": \"UTC\"}"
echo

# ---------------------------------------------------------------------------
# 8. Install the add-on into the site (HTTP 204 = success)
# ---------------------------------------------------------------------------
echo "==> [8/8] Installing zopyx.surveyjs add-on"
curl -s "${AUTH[@]}" -X POST \
    -H "Accept: application/json" \
    "${BASE_URL}/${SITE_ID}/@addons/zopyx.surveyjs/install" \
    -o /dev/null -w "    add-on install: HTTP %{http_code}\n"

# ---------------------------------------------------------------------------
# Done - summary
# ---------------------------------------------------------------------------
echo
echo "============================================================"
echo " Plone 6.2 is up and running:"
echo "   Site : ${BASE_URL}/${SITE_ID}"
echo "   ZMI  : ${BASE_URL}/manage"
echo "   User : ${ADMIN_USER} / ${ADMIN_PASS}"
echo "   PID  : ${RUNWSGI_PID}   (log: ${WORKDIR}/instance/var/runwsgi.log)"
echo "   Stop : kill ${RUNWSGI_PID}"
echo "============================================================"
