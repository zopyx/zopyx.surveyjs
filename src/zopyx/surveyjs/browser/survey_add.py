from copy import deepcopy
from datetime import datetime
import logging
import re
from typing import Any

import orjson
import plone.api
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from .. import _
from ..permissions import AddSurvey
from ..utils import ensure_timezone_aware

logger = logging.getLogger(__name__)


SURVEY_ADD_DEFAULT_NOTIFICATION_BODY = (
    "Hello,\n\n"
    'A new form submission was received for "{title}".\n'
    "You can review the submitted data here:\n"
    "{detail_url}\n\n"
    "Regards,\n"
    "Privacy Forms Studio\n"
)

SURVEY_ADD_DEFAULTS: dict[str, Any] = {
    "title": "",
    "description": "",
    "effective": "",
    "expires": "",
    "actions": ["store"],
    "post_endpoint_url": "",
    "use_global_mail_settings": True,
    "email_sender": "",
    "email_subject": "",
    "email_to": "",
    "email_cc": "",
    "email_bcc": "",
    "email_formats": [],
    "email_body": "",
    "email_notification_subject": "Form submitted ({title})",
    "email_notification_body": SURVEY_ADD_DEFAULT_NOTIFICATION_BODY,
    "force_server_side_validation": True,
    "max_payload_size_mb": 1,
    "survey_languages": [],
    "access_mode": "public",
    "trusted_access_ttl_hours": 168,
    "embedding_mode": "none",
}


class SurveyAddView(BrowserView):
    """Minimal SurveyJS-inspired creator for quickly starting new surveys."""

    index = ViewPageTemplateFile("survey_add.pt")

    def __init__(self, context, request):
        super().__init__(context, request)
        self._errors: list[str] = []
        self._form_values: dict[str, Any] = {}

    def __call__(self):
        if not self.can_add:
            self.request.response.setStatus(403)
            return _("You are not allowed to add surveys here.")

        if self.request.get("REQUEST_METHOD", "GET").upper() == "POST":
            return self.handle_submit()
        return self.index()

    @property
    def can_add(self) -> bool:
        return plone.api.user.has_permission(AddSurvey, obj=self.context)

    @property
    def form_values(self) -> dict[str, Any]:
        if not self._form_values:
            self._form_values = deepcopy(SURVEY_ADD_DEFAULTS)
        return self._form_values

    @property
    def initial_data_json(self) -> str:
        payload = deepcopy(self.form_values)
        payload["__survey_languages_choices"] = self._survey_languages_choices()
        return orjson.dumps(payload).decode("utf-8")

    @property
    def errors(self) -> list[str]:
        return self._errors

    def _survey_languages_choices(self) -> list[dict[str, str]]:
        try:
            from ..content.survey import survey_languages_vocabulary
        except Exception:
            return []

        choices: list[dict[str, str]] = []
        for term in survey_languages_vocabulary:
            value = getattr(term, "value", None)
            if not value:
                continue
            title = getattr(term, "title", None) or str(value)
            choices.append({"value": str(value), "text": str(title)})
        return choices

    def handle_submit(self):
        data, extraction_errors = self._extract_form_data()
        self._form_values = data
        self._errors = list(extraction_errors)
        logger.info(
            "Survey add save: use_global_mail_settings=%r",
            data.get("use_global_mail_settings"),
        )

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
            survey = plone.api.content.create(**self._build_create_kwargs(data))
            self._apply_effective_expires(survey, data)
        except Exception:
            logger.exception("Survey creation failed: context=%s", self.context)
            self._errors.append(
                _("We could not create the survey at the moment. Please try again.")
            )
            self.request.response.setStatus(500)
            return self.index()

        plone.api.portal.show_message(
            _("Survey created. Let's build it!"),
            request=self.request,
            type="info",
        )
        editor_url = f"{survey.absolute_url()}/@@editor"
        return self.request.response.redirect(editor_url)

    def _extract_form_data(self) -> tuple[dict[str, Any], list[str]]:
        data = deepcopy(SURVEY_ADD_DEFAULTS)
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

    def _build_survey_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        actions = self._ensure_list(data.get("actions")) or ["store"]
        email_formats = self._ensure_list(data.get("email_formats"))
        email_cc = self._split_lines(data.get("email_cc"))
        email_bcc = self._split_lines(data.get("email_bcc"))
        max_payload = self._coerce_int(data.get("max_payload_size_mb"), 1)
        survey_languages = self._ensure_list(data.get("survey_languages"))
        ttl = self._coerce_int(data.get("trusted_access_ttl_hours"), 168)
        force_validation = bool(data.get("force_server_side_validation", True))

        return {
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "actions": set(actions),
            "post_endpoint_url": data.get("post_endpoint_url") or None,
            "use_global_mail_settings": bool(
                data.get("use_global_mail_settings", True)
            ),
            "email_sender": data.get("email_sender") or None,
            "email_subject": data.get("email_subject") or None,
            "email_to": data.get("email_to") or None,
            "email_cc": email_cc,
            "email_bcc": email_bcc,
            "email_formats": set(email_formats),
            "email_body": data.get("email_body") or None,
            "email_notification_subject": data.get("email_notification_subject") or "",
            "email_notification_body": data.get("email_notification_body") or "",
            "force_server_side_validation": force_validation,
            "max_payload_size_mb": max_payload,
            "survey_languages": survey_languages,
            "access_mode": data.get("access_mode") or "public",
            "trusted_access_ttl_hours": ttl,
            "embedding_mode": data.get("embedding_mode") or "none",
        }

    def _build_create_kwargs(self, data: dict[str, Any]) -> dict[str, Any]:
        payload = self._build_survey_fields(data)
        payload.update({"container": self.context, "type": "Survey"})
        return payload

    def _ensure_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            if not value:
                return []
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value if str(item).strip()]
        return [str(value)]

    def _split_lines(self, value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            parts = value
        else:
            parts = re.split(r"[\n,]+", str(value))
        return [part.strip() for part in parts if part and part.strip()]

    def _coerce_int(self, value: Any, default: int) -> int:
        try:
            candidate = int(value)
        except (TypeError, ValueError):
            return default
        if candidate < 1:
            return default
        return candidate

    def _parse_datetime_value(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return ensure_timezone_aware(value)
        text = str(value).strip()
        if not text:
            return None
        text = text.replace(" ", "T")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        if len(text) == 10:
            text = f"{text}T00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return ensure_timezone_aware(parsed)

    def _format_datetime_value(self, value: Any) -> str:
        if callable(value):
            value = value()
        if value is None:
            return ""
        if isinstance(value, str) and value.strip().lower() in {"none", "null"}:
            return ""
        if not value:
            return ""
        year = self._extract_datetime_year(value)
        if year is not None and (year < 1970 or year > 2100):
            return ""
        if hasattr(value, "ISO"):
            text = value.ISO()
        elif hasattr(value, "isoformat"):
            try:
                text = value.isoformat(timespec="minutes")
            except Exception:
                text = str(value)
        else:
            text = str(value)
        match = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})", text)
        if match:
            return f"{match.group(1)}T{match.group(2)}"
        return ""

    def _extract_datetime_year(self, value: Any) -> int | None:
        year_attr = getattr(value, "year", None)
        if year_attr is not None:
            try:
                return int(year_attr() if callable(year_attr) else year_attr)
            except Exception:
                pass
        if hasattr(value, "ISO"):
            try:
                text = value.ISO()
            except Exception:
                text = ""
        elif hasattr(value, "isoformat"):
            try:
                text = value.isoformat()
            except Exception:
                text = ""
        else:
            text = str(value)
        match = re.match(r"^(\d{4})-", text)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                return None
        return None

    def _get_effective_value(self, survey) -> Any:
        value = getattr(survey, "effective", None)
        return value() if callable(value) else value

    def _get_expires_value(self, survey) -> Any:
        value = getattr(survey, "expires", None)
        return value() if callable(value) else value

    def _apply_effective_expires(self, survey, data: dict[str, Any]) -> None:
        effective = self._parse_datetime_value(data.get("effective"))
        expires = self._parse_datetime_value(data.get("expires"))
        self._normalize_dublincore_dates(survey)
        survey.setEffectiveDate(effective)
        survey.setExpirationDate(expires)
        survey.reindexObject(idxs=["effective", "expires"])

    def _normalize_dublincore_dates(self, survey) -> None:
        for field_name, setter_name in (
            ("effective", "setEffectiveDate"),
            ("expires", "setExpirationDate"),
        ):
            value = getattr(survey, field_name, None)
            if callable(value):
                continue
            if hasattr(survey, field_name):
                try:
                    delattr(survey, field_name)
                except Exception:
                    pass
            if value:
                try:
                    getattr(survey, setter_name)(value)
                except Exception:
                    continue
