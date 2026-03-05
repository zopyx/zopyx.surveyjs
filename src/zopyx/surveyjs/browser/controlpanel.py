# -*- coding: utf-8 -*-
"""Control panel for Forms settings using SurveyJS."""

import logging
from typing import Any

import orjson
import plone.api
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from ..interfaces import IFormsSettings
from ..permissions import ManagePortal

logger = logging.getLogger(__name__)


class FormsSettingsView(BrowserView):
    """Forms Settings control panel using SurveyJS."""

    index = ViewPageTemplateFile("forms_settings.pt")

    def __init__(self, context, request):
        super().__init__(context, request)
        self._errors: list[str] = []
        self._form_values: dict[str, Any] | None = None

    def __call__(self):
        if not self.can_manage:
            self.request.response.setStatus(403)
            return "You are not allowed to access this control panel."

        if self.request.get("REQUEST_METHOD", "GET").upper() == "POST":
            return self.handle_submit()
        return self.index()

    @property
    def can_manage(self) -> bool:
        return plone.api.user.has_permission(ManagePortal, obj=self.context)

    @property
    def errors(self) -> list[str]:
        return self._errors

    @property
    def form_values(self) -> dict[str, Any]:
        if self._form_values is None:
            self._form_values = self._load_registry_values()
        return self._form_values

    @property
    def initial_data_json(self) -> str:
        return orjson.dumps(self.form_values).decode("utf-8")

    def _load_registry_values(self) -> dict[str, Any]:
        """Load current values from registry."""
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)

        # Convert email_cc and email_bcc from list to newline-separated string
        email_cc = getattr(settings, "email_cc", None) or []
        email_bcc = getattr(settings, "email_bcc", None) or []
        email_formats = getattr(settings, "email_formats", None) or set()
        features_enabled = getattr(settings, "features_enabled", None) or []

        return {
            "surveyjs_license_key": getattr(settings, "surveyjs_license_key", "") or "",
            "features_enabled": list(features_enabled),
            "ai_model": getattr(settings, "ai_model", "") or "",
            "ai_api_key": getattr(settings, "ai_api_key", "") or "",
            "ollama_url": getattr(settings, "ollama_url", "") or "",
            "ai_prompt_before": getattr(settings, "ai_prompt_before", "") or "",
            "ai_prompt_default": getattr(settings, "ai_prompt_default", "") or "",
            "ai_prompt_after": getattr(settings, "ai_prompt_after", "") or "",
            "log_ip_addresses": bool(getattr(settings, "log_ip_addresses", False)),
            "log_user_agent": bool(getattr(settings, "log_user_agent", False)),
            "email_sender": getattr(settings, "email_sender", "") or "",
            "email_to": getattr(settings, "email_to", "") or "",
            "email_subject": getattr(settings, "email_subject", "") or "",
            "email_cc": "\n".join(email_cc) if isinstance(email_cc, list) else "",
            "email_bcc": "\n".join(email_bcc) if isinstance(email_bcc, list) else "",
            "email_formats": list(email_formats),
            "email_body": getattr(settings, "email_body", "") or "",
            "result_storage_backend": getattr(
                settings, "result_storage_backend", "zodb"
            )
            or "zodb",
            "database_uri": getattr(
                settings, "database_uri", "sqlite:///var/surveyjs-results.db"
            )
            or "sqlite:///var/surveyjs-results.db",
            "authenticity_token_enabled": bool(
                getattr(settings, "authenticity_token_enabled", True)
            ),
            "authenticity_token_secret": getattr(
                settings, "authenticity_token_secret", ""
            )
            or "",
            "authenticity_token_ttl_seconds": int(
                getattr(settings, "authenticity_token_ttl_seconds", 3600) or 3600
            ),
            "authenticity_token_issuer": getattr(
                settings, "authenticity_token_issuer", "privacyforms.studio"
            )
            or "privacyforms.studio",
            "authenticity_token_audience": getattr(
                settings, "authenticity_token_audience", "privacyforms.studio"
            )
            or "privacyforms.studio",
            "authenticity_token_cache_path": getattr(
                settings, "authenticity_token_cache_path", "var/token_cache.db"
            )
            or "var/token_cache.db",
            # Direct DOM Embedding settings
            "embed_direct_global_enabled": bool(
                getattr(settings, "embed_direct_global_enabled", False)
            ),
            "embed_direct_signing_key": getattr(
                settings, "embed_direct_signing_key", ""
            )
            or "",
            "embed_direct_max_origins": int(
                getattr(settings, "embed_direct_max_origins", 10) or 10
            ),
        }

    def _extract_form_data(self) -> tuple[dict[str, Any], list[str]]:
        """Extract form data from request."""
        errors: list[str] = []
        data: dict[str, Any] = {}
        form = self.request.form
        payload = form.get("payload")

        if payload:
            try:
                data = orjson.loads(payload)
            except orjson.JSONDecodeError:
                errors.append("We could not read the submitted form data.")

        return data, errors

    def _validate_data(self, data: dict[str, Any]) -> list[str]:
        """Validate form data."""
        errors: list[str] = []

        # Validate authenticity token TTL
        ttl = data.get("authenticity_token_ttl_seconds")
        if ttl is not None:
            try:
                ttl_int = int(ttl)
                if ttl_int < 60:
                    errors.append("Authenticity token TTL must be at least 60 seconds.")
            except (ValueError, TypeError):
                errors.append("Authenticity token TTL must be a valid number.")

        # Validate database URI when RDBMS is selected
        if data.get("result_storage_backend") == "rdbms":
            db_uri = data.get("database_uri", "").strip()
            if not db_uri:
                errors.append(
                    "Database URI is required when using relational database storage."
                )

        return errors

    def _save_to_registry(self, data: dict[str, Any]) -> None:
        """Save settings to registry."""
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)

        # Helper to set registry values
        def set_value(name: str, value: Any) -> None:
            if hasattr(settings, name):
                setattr(settings, name, value)

        # General settings
        set_value("surveyjs_license_key", data.get("surveyjs_license_key", "").strip())

        features = data.get("features_enabled", [])
        set_value("features_enabled", list(features) if features else [])

        # AI settings
        set_value("ai_model", data.get("ai_model", "").strip())
        api_key = data.get("ai_api_key", "")
        if api_key and api_key.strip():  # Only update if not empty
            set_value("ai_api_key", api_key.strip())
        # URI fields must be None (not empty string) when unset
        ollama_url = data.get("ollama_url", "").strip()
        set_value("ollama_url", ollama_url if ollama_url else None)
        set_value("ai_prompt_before", data.get("ai_prompt_before", ""))
        set_value("ai_prompt_default", data.get("ai_prompt_default", ""))
        set_value("ai_prompt_after", data.get("ai_prompt_after", ""))

        # Logging settings
        set_value("log_ip_addresses", bool(data.get("log_ip_addresses", False)))
        set_value("log_user_agent", bool(data.get("log_user_agent", False)))

        # Mail settings
        set_value("email_sender", data.get("email_sender", "").strip())
        set_value("email_to", data.get("email_to", "").strip())
        set_value("email_subject", data.get("email_subject", "").strip())

        # Convert CC/BCC from newline-separated to list
        email_cc_raw = data.get("email_cc", "")
        email_cc = [line.strip() for line in email_cc_raw.split("\n") if line.strip()]
        set_value("email_cc", email_cc)

        email_bcc_raw = data.get("email_bcc", "")
        email_bcc = [line.strip() for line in email_bcc_raw.split("\n") if line.strip()]
        set_value("email_bcc", email_bcc)

        email_formats = data.get("email_formats", [])
        set_value("email_formats", set(email_formats) if email_formats else set())

        set_value("email_body", data.get("email_body", ""))

        # Storage settings
        set_value("result_storage_backend", data.get("result_storage_backend", "zodb"))
        # URI fields must be None (not empty string) when unset
        db_uri = data.get("database_uri", "").strip()
        set_value("database_uri", db_uri if db_uri else None)

        # Security settings
        set_value(
            "authenticity_token_enabled",
            bool(data.get("authenticity_token_enabled", True)),
        )

        token_secret = data.get("authenticity_token_secret", "")
        if token_secret and token_secret.strip():  # Only update if not empty
            set_value("authenticity_token_secret", token_secret.strip())

        ttl = data.get("authenticity_token_ttl_seconds", 3600)
        try:
            set_value("authenticity_token_ttl_seconds", int(ttl))
        except (ValueError, TypeError):
            set_value("authenticity_token_ttl_seconds", 3600)

        set_value(
            "authenticity_token_issuer",
            data.get("authenticity_token_issuer", "privacyforms.studio").strip(),
        )
        set_value(
            "authenticity_token_audience",
            data.get("authenticity_token_audience", "privacyforms.studio").strip(),
        )
        set_value(
            "authenticity_token_cache_path",
            data.get("authenticity_token_cache_path", "var/token_cache.db").strip(),
        )

        # Direct DOM Embedding settings
        set_value(
            "embed_direct_global_enabled",
            bool(data.get("embed_direct_global_enabled", False)),
        )

        embed_signing_key = data.get("embed_direct_signing_key", "")
        if embed_signing_key and embed_signing_key.strip():  # Only update if not empty
            set_value("embed_direct_signing_key", embed_signing_key.strip())

        embed_max_origins = data.get("embed_direct_max_origins", 10)
        try:
            set_value("embed_direct_max_origins", int(embed_max_origins))
        except (ValueError, TypeError):
            set_value("embed_direct_max_origins", 10)

    def handle_submit(self):
        """Handle form submission."""
        data, extraction_errors = self._extract_form_data()

        if extraction_errors:
            self._errors = extraction_errors
            self.request.response.setStatus(400)
            return self.index()

        # Validate data
        validation_errors = self._validate_data(data)
        if validation_errors:
            self._errors = validation_errors
            self._form_values = data  # Preserve submitted values
            self.request.response.setStatus(400)
            return self.index()

        # Save to registry
        try:
            self._save_to_registry(data)
        except Exception:
            logger.exception("Failed to save forms settings to registry")
            self._errors.append("We could not save the settings. Please try again.")
            self._form_values = data
            self.request.response.setStatus(500)
            return self.index()

        plone.api.portal.show_message(
            "Settings saved successfully.",
            request=self.request,
            type="info",
        )

        # Redirect back to the control panel
        return self.request.response.redirect(self.request.ACTUAL_URL)


# Keep old class for backward compatibility during transition
class FormsSettingsEditForm:
    """Deprecated: Use FormsSettingsView instead."""

    pass


class FormsSettingsControlPanel:
    """Deprecated: Use FormsSettingsView instead."""

    pass
