"""PDF theme editor view — standalone SurveyJS Creator with only the Theme tab."""

import json
import logging
import os

from plone.protect import CheckAuthenticator
from .views import Views

logger = logging.getLogger(__name__)


class PDFThemeEditorView(Views):
    """Standalone browser view that renders the SurveyJS Creator with only
    the Theme tab enabled. Supports import and export of theme JSON."""

    def __call__(self):
        if self.request.get("REQUEST_METHOD", "GET").upper() == "POST":
            CheckAuthenticator(self.request)
            return self._export_theme_json()
        return self.index()

    def _export_theme_json(self):
        """Write the submitted theme JSON to /tmp/theme.json."""
        try:
            raw = self.request.form.get("themeJson", "")
            if not raw:
                theme_json = {}
            else:
                theme_json = json.loads(raw)
            print(f"PDFThemeEditor received theme JSON: {json.dumps(theme_json, indent=2)}")
            tmp_path = "/tmp/theme.json"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(theme_json, f, indent=2)
            logger.info("Theme exported to %s (%d bytes)", tmp_path, len(raw))
            self.request.response.setHeader("Content-Type", "application/json")
            return json.dumps({"success": True, "path": tmp_path})
        except Exception as exc:
            logger.exception("Theme export failed")
            self.request.response.setStatus(500)
            self.request.response.setHeader("Content-Type", "application/json")
            return json.dumps({"success": False, "error": str(exc)})