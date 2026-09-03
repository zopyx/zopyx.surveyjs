import json
import logging

import plone.api
from plone.protect import CheckAuthenticator
from zope.annotation.interfaces import IAnnotations
from zope.component.hooks import getSite
from zope.event import notify
from zope.lifecycleevent import ObjectModifiedEvent

from .services import themes as themes_service
from .views import Views

logger = logging.getLogger(__name__)


class SurveyEditor(Views):
    """Dedicated browser view for @@editor."""

    @property
    def survey_languages(self):
        values = getattr(self.context, "survey_languages", None) or []
        if isinstance(values, (list, tuple, set)):
            return [str(v).strip() for v in values if str(v).strip()]
        return []

    @property
    def survey_languages_json(self):
        return json.dumps(self.survey_languages)

    @property
    def themes_choices(self):
        """Return list of {value, text} for available themes."""
        result = [{"value": "", "text": "No theme"}]
        try:
            site = getSite()
            if site is None:
                return result
            annotations = IAnnotations(site)
            themes = themes_service.list_themes(annotations)
            for t in themes:
                tid = t.get("id")
                if tid:
                    result.append({"value": tid, "text": t.get("name", "Unnamed")})
        except Exception:
            logger.exception("Failed to load themes choices")
        return result

    @property
    def themes_choices_json(self):
        return json.dumps(self.themes_choices)

    @property
    def current_theme_id(self):
        """Return the currently configured theme ID or empty string."""
        return getattr(self.context, "theme", None) or ""

    def __call__(self):
        if self.request.get("REQUEST_METHOD", "GET").upper() == "POST":
            CheckAuthenticator(self.request)
            action = (self.request.form.get("action") or "").strip()
            if action == "save_theme":
                return self._save_theme()
        # GET actions
        action = (self.request.get("action") or "").strip()
        if action == "get_theme_json":
            return self._get_theme_json()
        return self.index()

    def _save_theme(self):
        if not plone.api.user.has_permission("Modify portal content", obj=self.context):
            self.request.response.setStatus(403)
            return json.dumps({"success": False, "error": "Permission denied"})

        theme_id = (self.request.form.get("theme_id") or "").strip()
        setattr(self.context, "theme", theme_id or None)
        notify(ObjectModifiedEvent(self.context))
        self.context.reindexObject()
        import transaction
        transaction.commit()

        logger.info("Survey theme updated: %s -> %s", self.context.absolute_url(), theme_id)
        self.request.response.setHeader("Content-Type", "application/json")
        return json.dumps({"success": True, "theme_id": theme_id})

    def _get_theme_json(self):
        """Return theme JSON for a given theme_id (GET)."""
        theme_id = (self.request.get("theme_id") or "").strip()
        if not theme_id:
            return self.html_safe_json({})
        try:
            site = getSite()
            if site is None:
                return self.html_safe_json({})
            annotations = IAnnotations(site)
            theme = themes_service.get_theme(annotations, theme_id)
            if theme:
                return self.html_safe_json(theme.get("theme_json", {}))
        except Exception:
            logger.exception("Failed to get theme JSON")
        return self.html_safe_json({})