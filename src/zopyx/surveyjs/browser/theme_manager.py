"""Theme manager view — list, create, delete, upload, download themes."""

import json
import logging

from plone.protect import CheckAuthenticator
from zope.annotation.interfaces import IAnnotations
from zope.component.hooks import getSite

from .services import themes as themes_service
from .views import Views

logger = logging.getLogger(__name__)


class ThemeManagerView(Views):
    """Browser view for listing and managing themes on the site root."""

    def __call__(self):
        if self.request.get("REQUEST_METHOD", "GET").upper() == "POST":
            CheckAuthenticator(self.request)
            action = (self.request.form.get("action") or "").strip()
            if action == "create":
                return self._create_theme()
            elif action == "delete":
                return self._delete_theme()
            elif action == "upload":
                return self._upload_theme()
        # GET actions: download
        action = (self.request.get("action") or "").strip()
        if action == "download":
            return self._download_theme()
        return self.index()

    @property
    def _annotations(self):
        return IAnnotations(getSite())

    @property
    def themes(self):
        """Return list of themes for the template."""
        raw = themes_service.list_themes(self._annotations)
        result = []
        for t in raw:
            created = t.get("created")
            modified = t.get("modified")
            result.append(dict(
                id=t.get("id"),
                name=t.get("name", "Unnamed"),
                created=created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
                modified=modified.isoformat() if hasattr(modified, "isoformat") else str(modified or ""),
                theme_json=t.get("theme_json", {}),
                version_count=len(t.get("versions", {})),
            ))
        return result

    @property
    def portal_url(self):
        return getSite().absolute_url()

    def _create_theme(self):
        name = (self.request.form.get("name") or "").strip()
        if not name:
            self.request.response.setStatus(400)
            return json.dumps({"success": False, "error": "Name is required"})
        user = self._current_user()
        theme = themes_service.create_theme(self._annotations, name, user_id=user)
        import transaction
        transaction.commit()
        logger.info("Theme created: %s (%s)", name, theme["id"])
        self.request.response.setHeader("Content-Type", "application/json")
        return json.dumps({"success": True, "theme_id": theme["id"]})

    def _delete_theme(self):
        theme_id = (self.request.form.get("theme_id") or "").strip()
        if not theme_id:
            self.request.response.setStatus(400)
            return json.dumps({"success": False, "error": "theme_id is required"})
        ok = themes_service.delete_theme(self._annotations, theme_id)
        import transaction
        transaction.commit()
        if ok:
            logger.info("Theme deleted: %s", theme_id)
        self.request.response.setHeader("Content-Type", "application/json")
        return json.dumps({"success": ok})

    def _upload_theme(self):
        uploaded = self.request.form.get("theme_file") or self.request.get("theme_file")
        name = (self.request.form.get("name") or "").strip()
        if not uploaded:
            self.request.response.setStatus(400)
            return json.dumps({"success": False, "error": "No file uploaded"})
        try:
            if hasattr(uploaded, "read"):
                raw = uploaded.read()
            else:
                raw = uploaded
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            theme_json = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.request.response.setStatus(400)
            return json.dumps({"success": False, "error": f"Invalid JSON: {exc}"})
        if not isinstance(theme_json, dict) or "themeName" not in theme_json:
            self.request.response.setStatus(400)
            return json.dumps({"success": False, "error": "Invalid theme JSON: missing 'themeName' property"})
        if not name:
            name = theme_json.get("themeName", "Imported Theme")
        user = self._current_user()
        theme = themes_service.create_theme(self._annotations, name, theme_json, user_id=user)
        import transaction
        transaction.commit()
        logger.info("Theme uploaded: %s (%s)", name, theme["id"])
        self.request.response.setHeader("Content-Type", "application/json")
        return json.dumps({"success": True, "theme_id": theme["id"]})

    def _download_theme(self):
        theme_id = self.request.get("theme_id") or (self.request.form.get("theme_id") or "").strip()
        theme = themes_service.get_theme(self._annotations, theme_id)
        if theme is None:
            self.request.response.setStatus(404)
            return json.dumps({"success": False, "error": "Theme not found"})
        filename = f"{theme['name']}.json".replace(" ", "_")
        self.request.response.setHeader("Content-Type", "application/json")
        self.request.response.setHeader(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        return json.dumps(theme.get("theme_json", {}), indent=2)

    def _current_user(self):
        try:
            import plone.api
            return plone.api.user.get_current().getId()
        except Exception:
            return "admin"