from copy import deepcopy
import logging
from typing import Any

import orjson
import plone.api
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from .. import _
from .survey_add import SURVEY_ADD_DEFAULTS, SurveyAddView

logger = logging.getLogger(__name__)


class SurveyMetadata(SurveyAddView):
    """Survey settings editor based on the add wizard."""

    index = ViewPageTemplateFile("survey_metadata.pt")

    @property
    def _survey_actions_view(self):
        return self.context.restrictedTraverse("@@survey-actions")

    @property
    def can_manage_portal_content(self):
        return self._survey_actions_view.can_manage_portal_content

    @property
    def pdf_form_available(self):
        return self._survey_actions_view.pdf_form_available

    @property
    def is_manager(self):
        return self._survey_actions_view.is_manager

    @property
    def survey_status_label(self):
        return self._survey_actions_view.survey_status_label

    @property
    def survey_effective_display(self):
        return self._survey_actions_view.survey_effective_display

    @property
    def survey_expires_display(self):
        return self._survey_actions_view.survey_expires_display

    @property
    def survey_results_count(self):
        return self._survey_actions_view.survey_results_count

    def feature_enabled(self, feature_name):
        return self._survey_actions_view.feature_enabled(feature_name)

    def __call__(self):
        if not self.can_edit:
            self.request.response.setStatus(403)
            return _("You are not allowed to edit this survey.")

        self._normalize_dublincore_dates(self.context)

        if self.request.get("REQUEST_METHOD", "GET").upper() == "POST":
            return self.handle_submit()
        return self.index()

    @property
    def can_edit(self) -> bool:
        return plone.api.user.has_permission("Modify portal content", obj=self.context)

    @property
    def form_values(self) -> dict[str, Any]:
        if not self._form_values:
            data = deepcopy(SURVEY_ADD_DEFAULTS)
            data.update(self._extract_context_values())
            self._form_values = data
        return self._form_values

    def _extract_context_values(self) -> dict[str, Any]:
        survey = self.context
        force_validation = getattr(survey, "force_server_side_validation", True)
        max_payload = getattr(survey, "max_payload_size_mb", 1)
        survey_languages = list(getattr(survey, "survey_languages", []) or [])
        access_mode = getattr(survey, "access_mode", "public") or "public"
        ttl = getattr(survey, "trusted_access_ttl_hours", 168)
        embedding_mode = getattr(survey, "embedding_mode", "none") or "none"

        return {
            "title": getattr(survey, "title", "") or "",
            "description": getattr(survey, "description", "") or "",
            "effective": self._format_datetime_value(self._get_effective_value(survey)),
            "expires": self._format_datetime_value(self._get_expires_value(survey)),
            "actions": list(getattr(survey, "actions", []) or []),
            "post_endpoint_url": getattr(survey, "post_endpoint_url", None) or "",
            "use_global_mail_settings": bool(
                getattr(survey, "use_global_mail_settings", True)
            ),
            "email_sender": getattr(survey, "email_sender", None) or "",
            "email_subject": getattr(survey, "email_subject", None) or "",
            "email_to": getattr(survey, "email_to", None) or "",
            "email_cc": "\n".join(getattr(survey, "email_cc", []) or []),
            "email_bcc": "\n".join(getattr(survey, "email_bcc", []) or []),
            "email_formats": list(getattr(survey, "email_formats", []) or []),
            "email_body": getattr(survey, "email_body", None) or "",
            "email_notification_subject": getattr(
                survey, "email_notification_subject", None
            )
            or "",
            "email_notification_body": getattr(survey, "email_notification_body", None)
            or "",
            "force_server_side_validation": True
            if force_validation is None
            else bool(force_validation),
            "max_payload_size_mb": max_payload or 1,
            "survey_languages": survey_languages,
            "access_mode": access_mode,
            "trusted_access_ttl_hours": ttl or 168,
            "embedding_mode": embedding_mode,
        }

    def _extract_form_data(self) -> tuple[dict[str, Any], list[str]]:
        data = deepcopy(SURVEY_ADD_DEFAULTS)
        data.update(self._extract_context_values())
        errors: list[str] = []
        form = self.request.form
        payload = form.get("payload")
        if payload:
            try:
                payload_data = orjson.loads(payload)
            except orjson.JSONDecodeError:
                errors.append(_("We could not read the submitted form data."))
            else:
                for key in data:
                    if key in payload_data:
                        data[key] = payload_data[key]
                if "effective" not in payload_data:
                    data["effective"] = None
                if "expires" not in payload_data:
                    data["expires"] = None
        else:
            data["title"] = (form.get("title") or "").strip()
            data["description"] = (form.get("description") or "").strip()
            data["effective"] = None
            data["expires"] = None
        return data, errors

    def handle_submit(self):
        data, extraction_errors = self._extract_form_data()
        self._form_values = data
        self._errors = list(extraction_errors)

        title = (data.get("title") or "").strip()
        if not title:
            self._errors.append(_("Please provide a title for your survey."))

        actions = self._ensure_list(data.get("actions"))
        if not actions:
            self._errors.append(_("Select at least one submission handling option."))

        if self._errors:
            self.request.response.setStatus(400)
            return self.index()

        try:
            updates = self._build_survey_fields(data)
            for key, value in updates.items():
                setattr(self.context, key, value)
            self._apply_effective_expires(self.context, data)
            self.context.reindexObject()
        except Exception:
            logger.exception("Survey update failed: context=%s", self.context)
            self._errors.append(
                _("We could not update the survey at the moment. Please try again.")
            )
            self.request.response.setStatus(500)
            return self.index()

        plone.api.portal.show_message(
            _("Survey updated."),
            request=self.request,
            type="info",
        )
        return self.request.response.redirect(self.context.absolute_url())
