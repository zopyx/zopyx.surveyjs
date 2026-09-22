# -*- coding: utf-8 -*-
"""Additional statement coverage for the forms-settings control panel
(``browser/controlpanel.py``) and the form-version management views
(``browser/survey_versions.py``).

Every test drives a real code path and asserts an observable result
(registry writes, annotations, audit calls, HTTP responses) -- there are no
assert-free smoke tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import re
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import orjson
import plone.api as api
from plone.app.testing import (
    TEST_USER_ID,
    TEST_USER_NAME,
    TEST_USER_PASSWORD,
    setRoles,
)
from zope.annotation.interfaces import IAnnotations

from zopyx.surveyjs.browser.controlpanel import AITestView, FormsSettingsView
from zopyx.surveyjs.browser.survey_versions import SurveyVersions
from zopyx.surveyjs.constants import FORM_VERSIONS_KEY
from zopyx.surveyjs.testing import (  # noqa: F401
    ZOPYX_SURVEYJS_FUNCTIONAL_TESTING,
    ZOPYX_SURVEYJS_INTEGRATION_TESTING,
)

CONTROL_PANEL = "zopyx.surveyjs.browser.controlpanel"
VERSIONS = "zopyx.surveyjs.browser.survey_versions"


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self) -> None:
        self.status = None
        self.headers = {}
        self.body = b""
        self.redirects: list[str] = []

    def setStatus(self, status) -> None:  # noqa: N802
        self.status = status

    def setHeader(self, key, value) -> None:  # noqa: N802
        self.headers[key] = value

    def write(self, data) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.body += data

    def redirect(self, url) -> None:
        self.redirects.append(url)
        self.status = 302
        return None


class _FakeRequest:
    """Minimal request: a form, a response and a request method."""

    def __init__(self, form=None, method: str = "GET") -> None:
        self.form = dict(form or {})
        self.response = _FakeResponse()
        self._method = method
        self.ACTUAL_URL = "http://nohost/plone/@@forms-settings"

    def get(self, key, default=None):
        if key == "REQUEST_METHOD":
            return self._method
        return default


class _RecordingSettings:
    """Minimal settings object that records assignments.

    Only the field names passed in ``known`` appear to exist so that the
    ``hasattr`` guard inside ``_save_to_registry`` can be exercised in both
    directions.
    """

    def __init__(self, known=()) -> None:
        object.__setattr__(self, "writes", [])
        object.__setattr__(self, "known", set(known))

    def __getattr__(self, name):
        if name in object.__getattribute__(self, "known"):
            return None
        raise AttributeError(name)

    def __setattr__(self, name, value) -> None:
        self.writes.append((name, value))


class _FakeUrlResponse:
    def __init__(self, payload) -> None:
        self._payload = payload

    def read(self):
        return orjson.dumps(self._payload)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _forms_settings_field_names() -> list:
    from zope.schema import getFieldsInOrder

    from zopyx.surveyjs.interfaces import IFormsSettings

    return [name for name, _field in getFieldsInOrder(IFormsSettings)]


def _recording_settings(known):
    settings = _RecordingSettings(known)
    registry = MagicMock()
    registry.forInterface.return_value = settings
    return registry, settings


def _writes(settings) -> dict:
    return dict(settings.writes)


# --------------------------------------------------------------------------
# controlpanel.FormsSettingsView.__call__ / access control
# --------------------------------------------------------------------------


class FormsSettingsAccessTests(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.request = _FakeRequest()
        self.view = FormsSettingsView(self.portal, self.request)
        self.assertTrue(self.view.can_manage, "manager must be able to manage")

    def tearDown(self) -> None:
        setRoles(self.portal, TEST_USER_ID, ["Manager"])

    def test_user_without_manage_portal_gets_403_message(self) -> None:
        setRoles(self.portal, TEST_USER_ID, [])
        self.assertFalse(self.view.can_manage, "role-less user must not manage")

        result = self.view()

        self.assertEqual(result, "You are not allowed to access this control panel.")
        self.assertEqual(self.request.response.status, 403)
        self.assertEqual(self.request.response.headers, {})

    def test_unauthorized_request_never_renders_or_saves(self) -> None:
        setRoles(self.portal, TEST_USER_ID, [])
        self.request.form = {
            "payload": orjson.dumps({"ai_provider": "ollama"}).decode()
        }
        self.request._method = "POST"

        with patch.object(FormsSettingsView, "handle_submit") as handle_submit:
            result = self.view()

        handle_submit.assert_not_called()
        self.assertEqual(result, "You are not allowed to access this control panel.")
        self.assertEqual(self.request.response.status, 403)


# --------------------------------------------------------------------------
# _get_ai_model_choices
# --------------------------------------------------------------------------


class FormsSettingsModelChoicesTests(unittest.TestCase):
    def _view(self) -> FormsSettingsView:
        view = FormsSettingsView.__new__(FormsSettingsView)
        view.context = MagicMock()
        return view

    def test_vocabulary_lookup_failure_returns_empty_choices(self) -> None:
        with (
            patch(
                f"{CONTROL_PANEL}.getUtility",
                side_effect=KeyError("unknown vocabulary"),
            ),
            patch(f"{CONTROL_PANEL}.logger") as logger,
        ):
            choices = self._view()._get_ai_model_choices()

        self.assertEqual(choices, [])
        logger.exception.assert_called_once_with("Failed to load AI models vocabulary")
        logger.warning.assert_not_called()

    def test_empty_vocabulary_warns_and_returns_no_choices(self) -> None:
        factory = MagicMock(return_value=[])
        with (
            patch(f"{CONTROL_PANEL}.getUtility", return_value=factory) as get_utility,
            patch(f"{CONTROL_PANEL}.logger") as logger,
        ):
            choices = self._view()._get_ai_model_choices()

        self.assertEqual(choices, [])
        get_utility.assert_called_once()
        logger.warning.assert_called_once_with(
            "AI models vocabulary returned no choices"
        )
        logger.exception.assert_not_called()


# --------------------------------------------------------------------------
# _validate_data
# --------------------------------------------------------------------------


class FormsSettingsValidateTests(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.view = FormsSettingsView(self.portal, _FakeRequest())

    def test_ttl_below_minimum_is_rejected(self) -> None:
        errors = self.view._validate_data({"authenticity_token_ttl_seconds": 30})
        self.assertEqual(
            errors, ["Authenticity token TTL must be at least 60 seconds."]
        )

    def test_ttl_minimum_boundary_is_accepted(self) -> None:
        self.assertEqual(
            self.view._validate_data({"authenticity_token_ttl_seconds": 60}), []
        )

    def test_non_numeric_ttl_is_rejected(self) -> None:
        errors = self.view._validate_data({"authenticity_token_ttl_seconds": "soon"})
        self.assertEqual(errors, ["Authenticity token TTL must be a valid number."])

    def test_rdbms_storage_requires_database_uri(self) -> None:
        errors = self.view._validate_data(
            {"result_storage_backend": "rdbms", "database_uri": "   "}
        )
        self.assertEqual(
            errors,
            ["Database URI is required when using relational database storage."],
        )

    def test_rdbms_storage_with_uri_is_accepted(self) -> None:
        self.assertEqual(
            self.view._validate_data(
                {
                    "result_storage_backend": "rdbms",
                    "database_uri": "sqlite:///var/surveyjs-results.db",
                }
            ),
            [],
        )

    def test_valid_kv_rdbms_uri_is_accepted(self) -> None:
        errors = self.view._validate_data(
            {
                "kv_cache_backend": "rdbms",
                "kv_cache_database_uri": "sqlite:///var/surveyjs-cache.db",
            }
        )
        self.assertEqual(errors, [])

    def test_unsupported_kv_rdbms_uri_is_reported(self) -> None:
        errors = self.view._validate_data(
            {
                "kv_cache_backend": "rdbms",
                "kv_cache_database_uri": "redis://example.com/0",
            }
        )
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("Invalid caching database URI: "))
        self.assertIn("unsupported KV database backend: 'redis'", errors[0])

    def test_malformed_kv_rdbms_uri_is_reported(self) -> None:
        errors = self.view._validate_data(
            {"kv_cache_backend": "rdbms", "kv_cache_database_uri": "://nope"}
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("Invalid caching database URI: ", errors[0])

    def test_negative_lock_timeout_is_rejected(self) -> None:
        errors = self.view._validate_data({"kv_cache_lock_timeout_seconds": -0.5})
        self.assertEqual(errors, ["Caching lock timeout cannot be negative."])

    def test_zero_lock_timeout_is_accepted(self) -> None:
        self.assertEqual(
            self.view._validate_data({"kv_cache_lock_timeout_seconds": 0}), []
        )

    def test_non_numeric_lock_timeout_is_rejected(self) -> None:
        errors = self.view._validate_data({"kv_cache_lock_timeout_seconds": "fast"})
        self.assertEqual(errors, ["Caching lock timeout must be a valid number."])

    def test_unknown_endpoint_validation_mode_is_rejected(self) -> None:
        errors = self.view._validate_data({"post_endpoint_validation_mode": "strict"})
        self.assertEqual(
            errors, ["POST endpoint validation must be public or allowlist."]
        )

    def test_allowlist_mode_requires_at_least_one_host(self) -> None:
        errors = self.view._validate_data(
            {
                "post_endpoint_validation_mode": "allowlist",
                "post_endpoint_allowlist": " \n  \n",
            }
        )
        self.assertEqual(
            errors,
            ["At least one POST endpoint hostname is required in allowlist mode."],
        )

    def test_allowlist_mode_with_host_is_accepted(self) -> None:
        self.assertEqual(
            self.view._validate_data(
                {
                    "post_endpoint_validation_mode": "allowlist",
                    "post_endpoint_allowlist": "example.com\n*.example.org",
                }
            ),
            [],
        )


# --------------------------------------------------------------------------
# _save_to_registry edge cases
# --------------------------------------------------------------------------


class FormsSettingsSaveEdgeCaseTests(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.view = FormsSettingsView(self.portal, _FakeRequest())
        self.field_names = _forms_settings_field_names()
        self.assertTrue(len(self.field_names) > 20)

    def _save(self, data, settings):
        registry = MagicMock()
        registry.forInterface.return_value = settings
        with patch(f"{CONTROL_PANEL}.getUtility", return_value=registry):
            self.view._save_to_registry(data)
        return settings

    def test_unknown_kv_backend_raises_and_stops_the_save(self) -> None:
        _registry, settings = _recording_settings(self.field_names)

        with self.assertRaises(ValueError) as caught:
            self._save({"kv_cache_backend": "redis"}, settings)

        self.assertEqual(str(caught.exception), "unknown KV cache backend: 'redis'")
        # fields written before the failing check are visible, the backend
        # itself is never applied
        written = _writes(settings)
        self.assertEqual(written["surveyjs_license_key"], "")
        self.assertNotIn("kv_cache_backend", written)

    def test_unknown_provider_falls_back_to_installed(self) -> None:
        _registry, settings = _recording_settings(self.field_names)

        self._save(
            {
                "ai_provider": "definitely-not-a-provider",
                "ai_model": "gpt-4o",
                "ai_api_key": "installed-key",
                "ollama_url": "http://localhost:11434",
                "custom_llm_name": "deepseek-chat",
            },
            settings,
        )

        written = _writes(settings)
        self.assertEqual(written["ai_provider"], "installed")
        self.assertEqual(written["ai_model"], "gpt-4o")
        self.assertEqual(written["ai_api_key"], "installed-key")
        # non-active provider groups are cleared
        self.assertIsNone(written["ollama_url"])
        self.assertEqual(written["custom_llm_name"], "")

    def test_invalid_numeric_values_fall_back_to_defaults(self) -> None:
        _registry, settings = _recording_settings(self.field_names)

        self._save(
            {
                "kv_cache_lock_timeout_seconds": "not-a-number",
                "authenticity_token_ttl_seconds": "not-a-number",
                "embed_direct_max_origins": "not-a-number",
            },
            settings,
        )

        written = _writes(settings)
        self.assertEqual(written["kv_cache_lock_timeout_seconds"], 5.0)
        self.assertEqual(written["authenticity_token_ttl_seconds"], 3600)
        self.assertEqual(written["embed_direct_max_origins"], 10)

    def test_numeric_values_are_parsed_and_clamped(self) -> None:
        _registry, settings = _recording_settings(self.field_names)

        self._save(
            {
                "kv_cache_lock_timeout_seconds": "-3",
                "authenticity_token_ttl_seconds": "7200",
                "embed_direct_max_origins": "42",
            },
            settings,
        )

        written = _writes(settings)
        self.assertEqual(written["kv_cache_lock_timeout_seconds"], 0.0)
        self.assertEqual(written["authenticity_token_ttl_seconds"], 7200)
        self.assertEqual(written["embed_direct_max_origins"], 42)

    def test_non_empty_secrets_are_written_stripped(self) -> None:
        _registry, settings = _recording_settings(self.field_names)

        self._save(
            {
                "authenticity_token_secret": "  token-secret  ",
                "embed_direct_signing_key": "  signing-key  ",
            },
            settings,
        )

        written = _writes(settings)
        self.assertEqual(written["authenticity_token_secret"], "token-secret")
        self.assertEqual(written["embed_direct_signing_key"], "signing-key")

    def test_empty_secrets_keep_the_stored_values(self) -> None:
        _registry, settings = _recording_settings(self.field_names)

        self._save(
            {
                "authenticity_token_secret": "   ",
                "embed_direct_signing_key": "",
            },
            settings,
        )

        written = _writes(settings)
        self.assertNotIn("authenticity_token_secret", written)
        self.assertNotIn("embed_direct_signing_key", written)
        # the save still runs to the end
        self.assertEqual(written["authenticity_token_issuer"], "privacyforms.studio")

    def test_fields_missing_from_the_settings_are_skipped(self) -> None:
        _registry, settings = _recording_settings(())

        self._save(
            {
                "surveyjs_license_key": "LIC",
                "features_enabled": ["ai"],
                "ai_provider": "ollama",
                "ollama_url": "http://localhost:11434",
                "database_uri": "sqlite:///var/results.db",
            },
            settings,
        )

        self.assertEqual(settings.writes, [])

    def test_only_existing_fields_are_written(self) -> None:
        known = ("surveyjs_license_key", "kv_cache_backend")
        _registry, settings = _recording_settings(known)

        self._save(
            {
                "surveyjs_license_key": "LIC",
                "ai_provider": "ollama",
                "kv_cache_backend": "diskcache",
            },
            settings,
        )

        self.assertEqual(
            sorted(_writes(settings)), ["kv_cache_backend", "surveyjs_license_key"]
        )
        self.assertEqual(_writes(settings)["surveyjs_license_key"], "LIC")


# --------------------------------------------------------------------------
# controlpanel.AITestView dispatch
# --------------------------------------------------------------------------


class AITestDispatchTests(unittest.TestCase):
    def _view(self) -> AITestView:
        return AITestView.__new__(AITestView)

    def test_ollama_provider_delegates_to_ollama_probe(self) -> None:
        view = self._view()
        payload = {"provider": "ollama", "api_url": "http://localhost:11434"}
        sentinel = {"ok": True, "message": "probed"}
        with patch.object(
            AITestView, "_test_ollama", return_value=sentinel
        ) as test_ollama:
            result = view._test_provider(payload)

        self.assertIs(result, sentinel)
        test_ollama.assert_called_once_with(payload)

    def test_model_list_is_truncated_after_eight_entries(self) -> None:
        view = self._view()
        models = [{"name": f"model-{index}"} for index in range(10)]
        with patch(
            f"{CONTROL_PANEL}.urlopen",
            return_value=_FakeUrlResponse({"models": models}),
        ):
            result = view._test_ollama({"api_url": "http://localhost:11434"})

        self.assertTrue(result["ok"])
        self.assertIn("10 model(s) available", result["message"])
        self.assertIn("model-0, model-1, model-2, model-3", result["message"])
        self.assertIn("model-7, ...", result["message"])
        self.assertNotIn("model-8", result["message"])

    def test_short_model_list_is_not_truncated(self) -> None:
        view = self._view()
        with patch(
            f"{CONTROL_PANEL}.urlopen",
            return_value=_FakeUrlResponse(
                {"models": [{"name": "llama3.2"}, {"name": "mistral"}]}
            ),
        ):
            result = view._test_ollama({"api_url": "http://localhost:11434"})

        self.assertIn("llama3.2, mistral", result["message"])
        self.assertNotIn("...", result["message"])


# --------------------------------------------------------------------------
# controlpanel submit pipeline over HTTP (POST -> save / 400 / 500)
# --------------------------------------------------------------------------


class FormsSettingsSubmitFunctionalTests(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.url = self.portal.absolute_url() + "/@@forms-settings"
        self.original_values = self._current_values()
        self._restore_payload = None

    def tearDown(self) -> None:
        if self._restore_payload is None:
            return
        try:
            self._post(self._browser(), self._restore_payload)
        except Exception:  # pragma: no cover - best effort restore
            pass

    # -- helpers ---------------------------------------------------------

    def _browser(self):
        import transaction
        from plone.testing.zope import Browser

        transaction.commit()
        browser = Browser(self.layer["app"])
        browser.raiseHttpErrors = False
        browser.addHeader(
            "Authorization", f"Basic {TEST_USER_NAME}:{TEST_USER_PASSWORD}"
        )
        return browser

    def _current_values(self) -> dict:
        view = FormsSettingsView(self.portal, _FakeRequest())
        values = dict(view.form_values)
        values.pop("__ai_model_choices", None)
        return values

    def _post(self, browser, payload) -> None:
        browser.open(self.portal.absolute_url() + "/@@authenticator/token")
        token = browser.contents.strip()
        body = urlencode(
            {
                "payload": orjson.dumps(payload).decode("utf-8"),
                "_authenticator": token,
            }
        )
        browser.post(self.url, body, "application/x-www-form-urlencoded")

    def _initial_data(self, contents) -> dict:
        match = re.search(
            r'<script type="application/json"[^>]*id="survey-add-initial-data"'
            r"[^>]*>(.*?)</script>",
            contents,
            re.S,
        )
        self.assertIsNotNone(match, "initial data script missing")
        return json.loads(match.group(1))

    # -- tests -----------------------------------------------------------

    def test_manager_can_open_the_panel(self) -> None:
        browser = self._browser()
        browser.open(self.url)

        self.assertIn("200", browser.headers.get("Status", ""))
        self.assertNotIn("/login", browser.url)
        data = self._initial_data(browser.contents)
        self.assertEqual(
            data["surveyjs_license_key"], self.original_values["surveyjs_license_key"]
        )

    def test_valid_submission_saves_and_redirects(self) -> None:
        payload = dict(self.original_values)
        payload["surveyjs_license_key"] = "COVERAGE-LICENSE-KEY"
        self._restore_payload = self.original_values
        captured = {}
        original_save = FormsSettingsView._save_to_registry

        def spy(view_self, data):
            captured["data"] = dict(data)
            return original_save(view_self, data)

        browser = self._browser()
        with patch.object(FormsSettingsView, "_save_to_registry", spy):
            self._post(browser, payload)

        # the redirect was followed back to the panel and the success
        # message rendered
        self.assertIn("200", browser.headers.get("Status", ""))
        self.assertEqual(browser.url, self.url)
        self.assertIn("Settings saved successfully.", browser.contents)
        # the parsed payload reached the save step unchanged
        self.assertEqual(
            captured["data"]["surveyjs_license_key"], "COVERAGE-LICENSE-KEY"
        )
        # the new value was persisted and read back from the registry
        saved = self._initial_data(browser.contents)
        self.assertEqual(saved["surveyjs_license_key"], "COVERAGE-LICENSE-KEY")

        # restore the original value through the same view
        self._post(browser, self.original_values)
        restored = self._initial_data(browser.contents)
        self.assertEqual(
            restored["surveyjs_license_key"],
            self.original_values["surveyjs_license_key"],
        )
        self._restore_payload = None

    def test_unparsable_payload_returns_400_with_error(self) -> None:
        browser = self._browser()
        browser.open(self.portal.absolute_url() + "/@@authenticator/token")
        token = browser.contents.strip()
        browser.post(
            self.url,
            urlencode({"payload": "not-json{", "_authenticator": token}),
            "application/x-www-form-urlencoded",
        )

        self.assertIn("400", browser.headers.get("Status", ""))
        self.assertIn("We could not read the submitted form data.", browser.contents)

    def test_invalid_values_return_400_and_keep_submitted_values(self) -> None:
        payload = dict(self.original_values)
        payload["authenticity_token_ttl_seconds"] = 5
        browser = self._browser()
        self._post(browser, payload)

        self.assertIn("400", browser.headers.get("Status", ""))
        self.assertIn(
            "Authenticity token TTL must be at least 60 seconds.", browser.contents
        )
        # the rejected values are re-rendered so the user can fix them
        submitted = self._initial_data(browser.contents)
        self.assertEqual(submitted["authenticity_token_ttl_seconds"], 5)

    def test_registry_save_failure_returns_500(self) -> None:
        browser = self._browser()
        with patch.object(
            FormsSettingsView,
            "_save_to_registry",
            side_effect=RuntimeError("registry down"),
        ):
            self._post(browser, dict(self.original_values))

        self.assertIn("500", browser.headers.get("Status", ""))
        self.assertIn(
            "We could not save the settings. Please try again.", browser.contents
        )
        submitted = self._initial_data(browser.contents)
        self.assertEqual(
            submitted["surveyjs_license_key"],
            self.original_values["surveyjs_license_key"],
        )


# --------------------------------------------------------------------------
# survey_versions.SurveyVersions
# --------------------------------------------------------------------------


class SurveyVersionsIntegrationTests(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.survey = api.content.create(
            container=self.portal,
            type="Survey",
            id="survey-versions",
            title="Versions",
            description="Survey description",
        )
        self.request = _FakeRequest()
        self.view = SurveyVersions(self.survey, self.request)

    # -- helpers ---------------------------------------------------------

    def _annotations(self):
        return IAnnotations(self.survey)

    def _versions(self) -> dict:
        return self._annotations().get(FORM_VERSIONS_KEY, {})

    def _seed_version(
        self,
        version_id: str,
        created: datetime | None = None,
        form_json: dict | None = None,
        locked: bool = False,
    ) -> dict:
        versions = self._annotations().setdefault(FORM_VERSIONS_KEY, {})
        versions[version_id] = {
            "id": version_id,
            "created": created or datetime(2024, 1, 1, tzinfo=timezone.utc),
            "form_json": (
                form_json if form_json is not None else {"pages": [{"name": "page1"}]}
            ),
            "locked": locked,
            "user": "tester",
        }
        return versions[version_id]

    def _redirect_target(self) -> str:
        return self.survey.absolute_url() + "/@@form-versions"

    # -- versions / has_versions ----------------------------------------

    def test_versions_empty_before_any_form_is_saved(self) -> None:
        self.assertFalse(self.view.has_versions)
        self.assertEqual(self.view.versions, [])

    def test_versions_are_returned_newest_first(self) -> None:
        self._seed_version(
            "v-old",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            {"pages": [{"name": "old"}]},
        )
        self._seed_version(
            "v-new",
            datetime(2025, 6, 1, tzinfo=timezone.utc),
            {"pages": [{"name": "new"}]},
        )

        versions = self.view.versions

        self.assertEqual([version["id"] for version in versions], ["v-new", "v-old"])
        self.assertEqual(versions[0]["form_json"], {"pages": [{"name": "new"}]})
        self.assertTrue(self.view.has_versions)

    # -- restore_version -------------------------------------------------

    def test_restore_version_without_id_reports_error(self) -> None:
        with patch("plone.api.portal.show_message") as show_message:
            result = self.view.restore_version()

        self.assertIsNone(result)
        self.assertEqual(self.request.response.redirects, [self._redirect_target()])
        self.assertEqual(str(show_message.call_args.args[0]), "No version ID provided")
        self.assertEqual(show_message.call_args.kwargs["type"], "error")
        self.assertEqual(len(self._versions()), 0)

    def test_restore_version_for_unknown_id_reports_error(self) -> None:
        self._seed_version("v1")
        self.request.form = {"version_id": "does-not-exist"}

        with patch("plone.api.portal.show_message") as show_message:
            self.view.restore_version()

        self.assertEqual(str(show_message.call_args.args[0]), "Version not found")
        self.assertEqual(show_message.call_args.kwargs["type"], "error")
        self.assertEqual(list(self._versions()), ["v1"])

    def test_restore_version_creates_new_version_and_audits(self) -> None:
        original_json = {"pages": [{"name": "original"}]}
        self._seed_version("v1", form_json=original_json)
        self.request.form = {"version_id": "v1"}

        with (
            patch(f"{VERSIONS}.audit_form_version_change") as audit,
            patch("plone.api.portal.show_message") as show_message,
        ):
            self.view.restore_version()

        versions = self._versions()
        self.assertEqual(len(versions), 2)
        new_id = next(version_id for version_id in versions if version_id != "v1")
        new_version = versions[new_id]
        self.assertEqual(new_version["form_json"], original_json)
        self.assertFalse(new_version["locked"])

        audit.assert_called_once()
        self.assertEqual(audit.call_args.args[0], self.survey)
        self.assertEqual(audit.call_args.kwargs["form_json"], original_json)
        self.assertEqual(audit.call_args.kwargs["source"], "restore_version")
        self.assertEqual(audit.call_args.kwargs["new_version_id"], new_id)
        self.assertEqual(audit.call_args.kwargs["previous_version_id"], "v1")
        self.assertEqual(audit.call_args.kwargs["previous_form_json"], original_json)
        self.assertIs(audit.call_args.kwargs["locked"], False)
        self.assertEqual(
            audit.call_args.kwargs["extra"], {"restored_from_version_id": "v1"}
        )
        self.assertEqual(
            str(show_message.call_args.args[0]),
            "Version restored successfully. A new version has been created.",
        )
        self.assertEqual(show_message.call_args.kwargs["type"], "info")
        self.assertEqual(self.request.response.redirects, [self._redirect_target()])

    # -- toggle_version_lock ---------------------------------------------

    def test_toggle_version_lock_without_id_reports_error(self) -> None:
        with patch("plone.api.portal.show_message") as show_message:
            result = self.view.toggle_version_lock()

        self.assertIsNone(result)
        self.assertEqual(str(show_message.call_args.args[0]), "No version ID provided")
        self.assertEqual(show_message.call_args.kwargs["type"], "error")
        self.assertEqual(self.request.response.redirects, [self._redirect_target()])

    def test_toggle_version_lock_for_unknown_id_reports_error(self) -> None:
        self._seed_version("v1", locked=False)
        self.request.form = {"version_id": "missing"}

        with patch("plone.api.portal.show_message") as show_message:
            self.view.toggle_version_lock()

        self.assertEqual(str(show_message.call_args.args[0]), "Version not found")
        self.assertFalse(self._versions()["v1"]["locked"])

    # -- delete_version --------------------------------------------------

    def test_delete_version_without_id_reports_error(self) -> None:
        self._seed_version("v1")
        with patch("plone.api.portal.show_message") as show_message:
            result = self.view.delete_version()

        self.assertIsNone(result)
        self.assertEqual(str(show_message.call_args.args[0]), "No version ID provided")
        self.assertEqual(list(self._versions()), ["v1"])
        self.assertEqual(self.request.response.redirects, [self._redirect_target()])

    def test_delete_version_for_unknown_id_reports_error(self) -> None:
        self.request.form = {"version_id": "missing"}
        with patch("plone.api.portal.show_message") as show_message:
            self.view.delete_version()

        self.assertEqual(str(show_message.call_args.args[0]), "Version not found")
        self.assertEqual(show_message.call_args.kwargs["type"], "error")

    def test_delete_version_removes_unlocked_version_and_audits(self) -> None:
        self._seed_version("v1", locked=False)
        self._seed_version("v2", datetime(2025, 1, 1, tzinfo=timezone.utc), locked=True)
        self.request.form = {"version_id": "v1"}

        with (
            patch(f"{VERSIONS}.audit_form_version_state_change") as audit,
            patch("plone.api.portal.show_message") as show_message,
        ):
            self.view.delete_version()

        self.assertEqual(list(self._versions()), ["v2"])
        audit.assert_called_once()
        self.assertEqual(audit.call_args.args[0], self.survey)
        self.assertEqual(audit.call_args.kwargs["action"], "form.version.delete")
        self.assertEqual(audit.call_args.kwargs["comment"], "Form version deleted")
        self.assertEqual(audit.call_args.kwargs["version_id"], "v1")
        self.assertEqual(audit.call_args.kwargs["source"], "form_versions")
        self.assertEqual(audit.call_args.kwargs["extra"], {"was_locked": False})
        self.assertEqual(str(show_message.call_args.args[0]), "Version deleted")
        self.assertEqual(show_message.call_args.kwargs["type"], "info")
        self.assertEqual(self.request.response.redirects, [self._redirect_target()])

    # -- upload_version --------------------------------------------------

    def test_upload_version_without_file_reports_error(self) -> None:
        with patch("plone.api.portal.show_message") as show_message:
            result = self.view.upload_version()

        self.assertIsNone(result)
        self.assertEqual(str(show_message.call_args.args[0]), "No file uploaded")
        self.assertEqual(show_message.call_args.kwargs["type"], "error")
        self.assertEqual(self.request.response.redirects, [self._redirect_target()])
        self.assertEqual(len(self._versions()), 0)

    def test_upload_version_rejects_non_object_json(self) -> None:
        self.request.form = {"json_file": BytesIO(b'["a", "b"]')}

        with patch("plone.api.portal.show_message") as show_message:
            self.view.upload_version()

        message = show_message.call_args.args[0]
        self.assertEqual(str(message), "Invalid JSON file: ${error}")
        self.assertEqual(message.mapping["error"], "JSON must be an object")
        self.assertEqual(show_message.call_args.kwargs["type"], "error")
        self.assertEqual(len(self._versions()), 0)
        self.assertEqual(self.request.response.redirects, [self._redirect_target()])

    # -- create_template_from_version ------------------------------------

    def test_create_template_from_version_copies_form_and_fields(self) -> None:
        form_json = {
            "pages": [{"name": "page1", "elements": [{"type": "text", "name": "q1"}]}]
        }
        self._seed_version("v1", form_json=form_json)
        self.survey.access_mode = "trusted"
        self.survey.force_server_side_validation = True
        self.survey.max_payload_size_mb = 7
        self.request.form = {"version_id": "v1", "template_title": "Coverage Template"}

        with patch("plone.api.portal.show_message") as show_message:
            self.view.create_template_from_version()

        template = self.portal["coverage-template"]
        self.assertEqual(template.portal_type, "SurveyTemplate")
        self.assertEqual(template.title, "Coverage Template")
        self.assertEqual(orjson.loads(template.template_json), form_json)
        self.assertEqual(template.Description(), "Survey description")
        # fields stored on the survey are carried over to the template
        self.assertEqual(template.access_mode, "trusted")
        self.assertIs(template.force_server_side_validation, True)
        self.assertEqual(template.max_payload_size_mb, 7)
        self.assertIn("coverage-template", self.portal.objectIds())
        self.assertEqual(
            str(show_message.call_args.args[0]), "Template created successfully."
        )
        self.assertEqual(show_message.call_args.kwargs["type"], "info")
        self.assertEqual(self.request.response.redirects, [template.absolute_url()])

    def test_create_template_from_version_requires_title_and_version(self) -> None:
        self.request.form = {"version_id": "", "template_title": ""}

        with patch("plone.api.portal.show_message") as show_message:
            self.view.create_template_from_version()

        self.assertEqual(
            str(show_message.call_args.args[0]),
            "Template name and version are required.",
        )
        self.assertEqual(show_message.call_args.kwargs["type"], "error")
        self.assertEqual(self.request.response.redirects, [self._redirect_target()])


if __name__ == "__main__":
    unittest.main()
