from datetime import datetime, timezone

import plone.api
from zope.schema import getFieldsInOrder

from ..content.survey import ISurvey
from ..storage import get_result_storage
from .. import _
from ..utils import ensure_timezone_aware
from .views import Views


class SurveyOverview(Views):
    def survey_overview_entries(self):
        catalog = plone.api.portal.get_tool("portal_catalog")
        context_path = "/".join(self.context.getPhysicalPath())
        brains = catalog.searchResults(
            portal_type="Survey",
            path={"query": context_path, "depth": -1},
            sort_on="sortable_title",
        )
        storage = get_result_storage(self.context)
        access_labels = {
            "public": _("Public"),
            "trusted": _("Trusted access token"),
        }
        entries = []
        for brain in brains:
            obj = brain.getObject()
            access_mode = getattr(obj, "access_mode", "") or ""
            access_label = access_labels.get(access_mode, access_mode)
            language = obj.Language() or ""
            try:
                review_state = plone.api.content.get_state(obj)
            except Exception:
                review_state = brain.review_state or ""

            try:
                results_count = storage.count_results(obj)
            except Exception:
                results_count = 0
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
                label = self._translate_label(field.title) or name
                raw_value = self._survey_field_value_text(obj, name, field)
                value, value_full = self._compact_metadata_value(raw_value)
                metadata.append(
                    {
                        "label": label,
                        "value": value,
                        "value_full": value_full,
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
                    "title": brain.Title or "",
                    "description": brain.Description or "",
                    "url": brain.getURL(),
                    "review_state": review_state,
                    "effective": self._format_catalog_iso(brain.effective),
                    "expires": self._format_catalog_iso(brain.expires),
                    "results_count": results_count,
                    "access_mode": access_label,
                    "language": language,
                    "expires_future": expires_future,
                    "metadata": metadata,
                }
            )
        return entries
