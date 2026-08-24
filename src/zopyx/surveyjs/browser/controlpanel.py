# -*- coding: utf-8 -*-
"""Control panel for Forms settings using SurveyJS."""

import concurrent.futures
import logging
from typing import Any
from urllib.request import Request, urlopen

import orjson
import plone.api
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone.registry.interfaces import IRegistry
from zope.component import getUtility
from zope.schema.interfaces import IVocabularyFactory

from ..interfaces import IFormsSettings
from ..utils import html_safe_json
from ..permissions import ManagePortal
from .services.ai import PROVIDERS
from .services.ai import PROVIDER_FIELDS
from .services.ai import build_llm_model
from .services.ai import is_configured
from .services.http import json_error
from .services.http import json_response
from .services.http import parse_json_body

logger = logging.getLogger(__name__)

# Fields stored as None (not empty string) when unset; "" is invalid for
# URI fields and for the ai_model Choice against a populated vocabulary.
_EMPTY_IS_NONE_FIELDS = ("ai_model", "ollama_url", "custom_api_url")
# API key fields: keep-masked on save (empty submission keeps stored value)
_API_KEY_FIELDS = ("ai_api_key", "custom_api_key")


class FormsSettingsView(BrowserView):
    """Forms Settings control panel using SurveyJS."""

    index = ViewPageTemplateFile("forms_settings.pt")

    @staticmethod
    def html_safe_json(value):
        return html_safe_json(value)

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
        return html_safe_json(self.form_values)

    def _get_ai_model_choices(self) -> list[dict[str, str]]:
        """Load available AI model choices from the vocabulary."""
        try:
            factory = getUtility(IVocabularyFactory, "zopyx.surveyjs.AIModels")
            vocabulary = factory(self.context)
        except Exception:
            logger.exception("Failed to load AI models vocabulary")
            return []
        choices = [
            {"value": term.value, "text": term.title}
            for term in vocabulary
            if term.value
        ]
        if not choices:
            logger.warning("AI models vocabulary returned no choices")
        return choices

    def _load_registry_values(self) -> dict[str, Any]:
        """Load current values from registry."""
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)

        # Convert email_cc and email_bcc from list to newline-separated string
        email_cc = getattr(settings, "email_cc", None) or []
        email_bcc = getattr(settings, "email_bcc", None) or []
        email_formats = getattr(settings, "email_formats", None) or set()
        features_enabled = getattr(settings, "features_enabled", None) or []

        values = {
            "surveyjs_license_key": getattr(settings, "surveyjs_license_key", "") or "",
            "features_enabled": list(features_enabled),
            "ai_provider": self._effective_ai_provider(settings),
            "ai_model": getattr(settings, "ai_model", "") or "",
            "ai_api_key": getattr(settings, "ai_api_key", "") or "",
            "ollama_url": getattr(settings, "ollama_url", "") or "",
            "ollama_model": getattr(settings, "ollama_model", "") or "",
            "custom_llm_name": getattr(settings, "custom_llm_name", "") or "",
            "custom_api_url": getattr(settings, "custom_api_url", "") or "",
            "custom_api_key": getattr(settings, "custom_api_key", "") or "",
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
        ai_model_choices = self._get_ai_model_choices()
        if ai_model_choices:
            values["__ai_model_choices"] = ai_model_choices
        return values

    def _effective_ai_provider(self, settings) -> str:
        """Return the AI provider mode for the settings form.

        Uses the stored ``ai_provider`` when valid; otherwise derives it
        from legacy populated fields (ollama URL wins over a configured
        model, matching the previous resolver precedence).
        """
        provider = getattr(settings, "ai_provider", None)
        if provider in PROVIDERS:
            return provider
        if getattr(settings, "ollama_url", None):
            return "ollama"
        if getattr(settings, "custom_api_url", None):
            return "custom"
        return "installed"

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

        # Validate AI provider group completeness (mutually exclusive modes)
        provider = data.get("ai_provider", "installed")
        if provider == "custom":
            missing = [
                field
                for field in ("custom_llm_name", "custom_api_url", "custom_api_key")
                if not (data.get(field, "") or "").strip()
            ]
            if missing:
                errors.append(
                    "Custom LLM configuration requires LLM Name, LLM API URL "
                    "and API key."
                )
        elif provider == "ollama":
            if not (data.get("ollama_url", "") or "").strip():
                errors.append("Ollama configuration requires an Ollama URL.")

        return errors

    def _save_to_registry(self, data: dict[str, Any]) -> None:
        """Save settings to registry."""
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)

        # Helper to set registry values
        def set_value(name: str, value: Any) -> None:
            if not hasattr(settings, name):
                return
            try:
                setattr(settings, name, value)
            except AttributeError:
                # Record not registered yet (e.g. install upgraded without
                # re-importing the registry profile step): create it from the
                # schema field so saving the settings never fails.
                from plone.registry.interfaces import IPersistentField
                from plone.registry.record import Record

                field = IPersistentField(IFormsSettings[name])
                record = Record(field, value)
                registry.records[f"{IFormsSettings.__identifier__}.{name}"] = record

        # General settings
        set_value("surveyjs_license_key", data.get("surveyjs_license_key", "").strip())

        features = data.get("features_enabled", [])
        set_value("features_enabled", list(features) if features else [])

        # AI settings
        provider = data.get("ai_provider", "installed")
        if provider not in PROVIDERS:
            provider = "installed"
        set_value("ai_provider", provider)

        # The three provider groups are mutually exclusive: fields of
        # non-active groups are always cleared, so a saved configuration
        # can never mix providers. API keys of the active group are
        # keep-masked (empty submission keeps the stored value).
        for group, fields in PROVIDER_FIELDS.items():
            active = group == provider
            for field in fields:
                raw = data.get(field, "")
                value = raw.strip() if isinstance(raw, str) else raw
                if not active:
                    set_value(field, None if field in _EMPTY_IS_NONE_FIELDS else "")
                    continue
                if field in _API_KEY_FIELDS:
                    if value:
                        set_value(field, value)
                    continue
                if field in _EMPTY_IS_NONE_FIELDS:
                    set_value(field, value if value else None)
                else:
                    set_value(field, value if value else "")
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


class AITestView(BrowserView):
    """JSON endpoint that pings the currently configured AI provider.

    The forms-settings AI panels post the *current form values* (possibly
    unsaved) of one provider mode to ``@@ai-test``. The view validates the
    configuration, runs a provider-appropriate API action and returns
    ``{"ok": bool, "message": str}``.

    - installed: resolves the model via privacyforms_ai and sends a trivial
      prompt.
    - custom: resolves the model against the OpenAI-compatible endpoint and
      sends a trivial prompt.
    - ollama: queries the server's ``/api/tags`` endpoint (reachability and
      model list); a named model is checked for presence.
    """

    TEST_TIMEOUT = 25

    def __call__(self):
        payload = parse_json_body(self.request)
        if not isinstance(payload, dict):
            return json_error(
                self.request.response,
                400,
                "invalid-payload",
                "We could not read the submitted test data.",
            )
        result = self.run_test(payload)
        return json_response(self.request.response, result)

    def run_test(self, payload: dict) -> dict:
        """Run the provider test in a worker thread bounded by a timeout.

        On timeout the worker keeps running in the background; the client
        gets a clean timeout message instead of a hanging request.
        """
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(self._test_provider, payload)
            try:
                return future.result(timeout=self.TEST_TIMEOUT)
            except concurrent.futures.TimeoutError:
                return {
                    "ok": False,
                    "message": "Test timed out after %d seconds." % self.TEST_TIMEOUT,
                }
            except Exception as exc:
                return {"ok": False, "message": "Test failed: %s" % exc}
        finally:
            pool.shutdown(wait=False)

    def _fill_masked_api_key(self, payload: dict) -> None:
        """Fall back to the stored registry key like the save keep-mask."""
        if payload.get("api_key"):
            return
        provider = payload.get("provider")
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        field = "ai_api_key" if provider == "installed" else "custom_api_key"
        stored = getattr(settings, field, "") or ""
        if stored:
            payload["api_key"] = stored

    def _test_provider(self, payload: dict) -> dict:
        provider = payload.get("provider")
        if provider == "ollama":
            return self._test_ollama(payload)
        if provider in ("installed", "custom"):
            self._fill_masked_api_key(payload)
            settings = {
                "provider": provider,
                "model_name": (payload.get("model_name") or "").strip() or None,
                "api_key": (payload.get("api_key") or "").strip() or None,
                "api_url": (payload.get("api_url") or "").strip() or None,
            }
            if not is_configured(settings):
                if provider == "installed":
                    message = "AI model is required."
                else:
                    message = (
                        "Custom LLM configuration requires LLM Name, "
                        "LLM API URL and API key."
                    )
                return {"ok": False, "message": message}
            try:
                text = self._test_model(settings)
            except Exception as exc:
                return {
                    "ok": False,
                    "message": "Model '%s' failed: %s" % (settings["model_name"], exc),
                }
            snippet = (text or "").strip()[:120]
            return {
                "ok": True,
                "message": "Model '%s' responded: %s"
                % (settings["model_name"], snippet or "(empty response)"),
            }
        return {"ok": False, "message": "Unknown provider: %s" % provider}

    def _test_model(self, settings: dict) -> str:
        """Resolve the model and send a trivial prompt via privacyforms_ai."""
        model = build_llm_model(settings)
        from privacyforms_ai import AI

        response = AI.send_prompt(model, "Reply with exactly: OK")
        return AI.extract_response_text(response)

    def _test_ollama(self, payload: dict) -> dict:
        api_url = (payload.get("api_url") or "").strip()
        if not api_url:
            return {"ok": False, "message": "Ollama URL is required."}
        try:
            request = Request(api_url.rstrip("/") + "/api/tags", method="GET")
            with urlopen(request, timeout=10) as response:
                data = orjson.loads(response.read())
        except Exception as exc:
            return {
                "ok": False,
                "message": "Ollama server not reachable: %s" % exc,
            }

        models = sorted(
            {
                str(model.get("name"))
                for model in data.get("models", [])
                if isinstance(model, dict) and model.get("name")
            }
        )
        message = "Ollama server reachable at %s." % api_url
        if models:
            shown = ", ".join(models[:8])
            if len(models) > 8:
                shown += ", ..."
            message += " %d model(s) available: %s." % (len(models), shown)
        else:
            message += " No models found on the server."
        model_name = (payload.get("model_name") or "").strip()
        if model_name and not any(
            m == model_name or m.startswith(model_name + ":") for m in models
        ):
            message += " Warning: model '%s' was not found on the server." % model_name
        return {"ok": True, "message": message}


# Keep old class for backward compatibility during transition
class FormsSettingsEditForm:
    """Deprecated: Use FormsSettingsView instead."""

    pass


class FormsSettingsControlPanel:
    """Deprecated: Use FormsSettingsView instead."""

    pass
