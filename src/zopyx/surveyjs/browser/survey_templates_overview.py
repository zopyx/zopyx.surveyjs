from datetime import datetime, timezone

import plone.api
from zope.schema import getFieldsInOrder

from ..content.survey import ISurvey
from ..utils import ensure_timezone_aware
from .views import Views


class SurveyTemplatesOverview(Views):
    def survey_templates_overview_entries(self):
        """Return a list of SurveyTemplate objects for the templates overview."""
        catalog = plone.api.portal.get_tool("portal_catalog")
        context_path = "/".join(self.context.getPhysicalPath())
        brains = catalog.searchResults(
            portal_type="SurveyTemplate",
            path={"query": context_path, "depth": -1},
            sort_on="sortable_title",
        )
        entries = []
        for brain in brains:
            obj = brain.getObject()
            language = obj.Language()
            try:
                review_state = plone.api.content.get_state(obj)
            except Exception:
                review_state = brain.review_state or ""
            actions = getattr(obj, "actions", set()) or set()
            has_mail = "mail" in actions
            has_post = "post" in actions
            email_fields = {
                "email_sender",
                "email_subject",
                "email_to",
                "email_cc",
                "email_bcc",
                "email_formats",
                "email_body",
            }
            post_fields = {"post_endpoint_url"}
            metadata = []
            for name, field in getFieldsInOrder(ISurvey):
                # Skip email fields if mail action not enabled
                if name in email_fields and not has_mail:
                    continue
                # Skip POST fields if post action not enabled
                if name in post_fields and not has_post:
                    continue
                # Skip template_json field as it's specific to templates and very large
                if name == "template_json":
                    continue
                label = self._translate_label(field.title) or name
                raw_value = self._survey_field_value_text(obj, name, field)
                value, value_full = self._compact_metadata_value(raw_value)
                metadata.append(
                    {
                        "label": label,
                        "value": value,
                    }
                )
            expires_value = brain.expires
            if callable(expires_value):
                expires_value = expires_value()
            try:
                expires_future = bool(
                    expires_value
                    and ensure_timezone_aware(expires_value)
                    > datetime.now(timezone.utc)
                )
            except Exception:
                expires_future = False
            entries.append(
                {
                    "uid": brain.UID,
                    "title": brain.Title or "",
                    "description": brain.Description or "",
                    "url": brain.getURL(),
                    "review_state": review_state,
                    "effective": self._format_catalog_iso(brain.effective),
                    "expires": self._format_catalog_iso(brain.expires),
                    "language": language,
                    "expires_future": expires_future,
                    "metadata": metadata,
                }
            )
        return entries
