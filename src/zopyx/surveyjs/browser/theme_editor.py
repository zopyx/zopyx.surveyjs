"""Theme editor view — edit, save version, restore, export themes."""

import json
import logging

from plone.protect import CheckAuthenticator
from zope.annotation.interfaces import IAnnotations
from zope.component.hooks import getSite

from .services import themes as themes_service
from .views import Views

logger = logging.getLogger(__name__)


class ThemeEditorView(Views):
    """Browser view for editing a theme with the SurveyJS Creator."""

    def __call__(self):
        theme_id = self._get_theme_id()
        if not theme_id:
            self.request.response.setStatus(400)
            return "Missing theme_id parameter"
        self._theme = themes_service.get_theme(self._annotations, theme_id)
        if self._theme is None:
            self.request.response.setStatus(404)
            return "Theme not found"

        if self.request.get("REQUEST_METHOD", "GET").upper() == "POST":
            CheckAuthenticator(self.request)
            action = (self.request.form.get("action") or "").strip()
            if action == "save_version":
                return self._save_version()
            elif action == "save_current":
                return self._save_current_version()
            elif action == "restore_version":
                return self._restore_version()
            elif action == "export_theme":
                return self._export_theme_json()
            elif action == "get_theme_data":
                return self._get_theme_data_json()
        return self.index()

    @property
    def _annotations(self):
        return IAnnotations(getSite())

    def _get_theme_id(self):
        return (self.request.get("theme_id") or "").strip()

    @property
    def theme_id(self):
        return self._get_theme_id()

    @property
    def theme_name(self):
        return self._theme.get("name", "Unnamed")

    @property
    def theme_json(self):
        return self._theme.get("theme_json", {})

    @property
    def versions_json(self):
        versions = themes_service.sorted_theme_versions(self._theme, reverse=True)
        result = []
        for number, v in enumerate(versions, start=len(versions)):
            created = v.get("created")
            result.append(dict(
                id=v.get("id"),
                number=number,
                created=created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
                user=v.get("user", ""),
            ))
        return json.dumps(result)

    def _get_theme_data_json(self):
        """Return the theme JSON for the JS editor."""
        self.request.response.setHeader("Content-Type", "application/json")
        return json.dumps(self._theme.get("theme_json", {}))

    def _save_current_version(self):
        """Overwrite the current version without adding a history entry."""
        try:
            raw = self.request.form.get("themeJson", "")
            if not raw:
                self.request.response.setStatus(400)
                return json.dumps({"success": False, "error": "No theme JSON provided"})
            theme_json = json.loads(raw)
            theme = themes_service.save_theme_current_version(
                self._annotations, self._theme["id"], theme_json, self._current_user()
            )
            if theme is None:
                self.request.response.setStatus(404)
                return json.dumps({"success": False, "error": "Theme has no current version"})
            import transaction
            transaction.commit()
            logger.info("Current theme version updated: %s", self._theme["id"])
            versions = themes_service.sorted_theme_versions(theme, reverse=True)
            versions_info = [dict(
                id=v["id"],
                created=v["created"].isoformat(),
                user=v["user"],
            ) for v in versions]
            self.request.response.setHeader("Content-Type", "application/json")
            return json.dumps({"success": True, "versions": versions_info})
        except Exception as exc:
            logger.exception("Current theme version update failed")
            self.request.response.setStatus(500)
            self.request.response.setHeader("Content-Type", "application/json")
            return json.dumps({"success": False, "error": str(exc)})

    def _save_version(self):
        try:
            raw = self.request.form.get("themeJson", "")
            if not raw:
                self.request.response.setStatus(400)
                return json.dumps({"success": False, "error": "No theme JSON provided"})
            theme_json = json.loads(raw)
            user = self._current_user()
            theme = themes_service.save_theme_version(
                self._annotations, self._theme["id"], theme_json, user
            )
            import transaction
            transaction.commit()
            logger.info("Theme version saved: %s", self._theme["id"])
            versions = themes_service.sorted_theme_versions(theme, reverse=True)
            versions_info = [dict(
                id=v["id"],
                created=v["created"].isoformat(),
                user=v["user"],
            ) for v in versions]
            self.request.response.setHeader("Content-Type", "application/json")
            return json.dumps({"success": True, "versions": versions_info})
        except Exception as exc:
            logger.exception("Theme save failed")
            self.request.response.setStatus(500)
            self.request.response.setHeader("Content-Type", "application/json")
            return json.dumps({"success": False, "error": str(exc)})

    def _restore_version(self):
        version_id = (self.request.form.get("version_id") or "").strip()
        if not version_id:
            self.request.response.setStatus(400)
            return json.dumps({"success": False, "error": "version_id is required"})
        theme = themes_service.restore_theme_version(
            self._annotations, self._theme["id"], version_id
        )
        if theme is None:
            self.request.response.setStatus(404)
            return json.dumps({"success": False, "error": "Version not found"})
        import transaction
        transaction.commit()
        logger.info("Theme restored to version %s: %s", version_id, self._theme["id"])
        self.request.response.setHeader("Content-Type", "application/json")
        return json.dumps({
            "success": True,
            "theme_json": theme.get("theme_json", {}),
        })

    def _export_theme_json(self):
        """Serve the current theme JSON as a file download."""
        try:
            raw = self.request.form.get("themeJson", "")
            theme_json = json.loads(raw) if raw else self.theme_json
            name = self._theme.get("name", "theme")
            filename = f"{name}.json".replace(" ", "_")
            payload = json.dumps(theme_json, indent=2)
            self.request.response.setHeader(
                "Content-Type", "application/json; charset=utf-8"
            )
            self.request.response.setHeader(
                "Content-Disposition",
                f'attachment; filename="{filename}"',
            )
            self.request.response.setHeader(
                "Content-Length", str(len(payload.encode("utf-8")))
            )
            logger.info("Theme export downloaded: %s (%s)", self._theme["id"], filename)
            return payload
        except Exception as exc:
            logger.exception("Theme export failed")
            self.request.response.setStatus(500)
            self.request.response.setHeader("Content-Type", "application/json")
            return json.dumps({"success": False, "error": str(exc)})

    def _current_user(self):
        try:
            import plone.api
            return plone.api.user.get_current().getId()
        except Exception:
            return "admin"
