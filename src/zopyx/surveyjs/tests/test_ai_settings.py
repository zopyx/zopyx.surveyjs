# -*- coding: utf-8 -*-
"""Tests for the AI provider settings (installed / ollama / custom).

Covers the registry mapping in ``load_ai_settings``, the configuration
completeness checks, the shared LLM model resolver and the control panel
save/validate logic enforcing mutual exclusivity of the three providers.
"""

import json
import os
import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from plone.app.testing import (
    TEST_USER_NAME,
    TEST_USER_PASSWORD,
    setRoles,
    TEST_USER_ID,
)
from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from zopyx.surveyjs.browser.controlpanel import FormsSettingsView
from zopyx.surveyjs.browser.services.ai import (
    PROVIDER_CUSTOM,
    PROVIDER_INSTALLED,
    PROVIDER_OLLAMA,
    build_llm_model,
    is_configured,
    load_ai_settings,
)
from zopyx.surveyjs.interfaces import IFormsSettings
from zopyx.surveyjs.testing import (  # noqa
    ZOPYX_SURVEYJS_FUNCTIONAL_TESTING,
    ZOPYX_SURVEYJS_INTEGRATION_TESTING,
)

AI_FIELDS = (
    "ai_provider",
    "ai_model",
    "ai_api_key",
    "ollama_url",
    "ollama_model",
    "custom_llm_name",
    "custom_api_url",
    "custom_api_key",
)


def _make_fake_ai():
    """Build a stub ``privacyforms_ai`` module recording calls."""

    class FakeAI:
        calls = {"get_model": [], "get_custom_model": []}

        @staticmethod
        def get_model(key):
            FakeAI.calls["get_model"].append(key)
            return f"model:{key}"

        @staticmethod
        def get_custom_model(model_name, api_url, api_key, **kwargs):
            FakeAI.calls["get_custom_model"].append(
                (model_name, api_url, api_key, kwargs)
            )
            return f"custom:{model_name}"

    module = types.ModuleType("privacyforms_ai")
    module.AI = FakeAI
    return module, FakeAI


class IsConfiguredTests(unittest.TestCase):
    def test_installed_requires_model(self) -> None:
        self.assertTrue(
            is_configured(
                {
                    "provider": PROVIDER_INSTALLED,
                    "model_name": "gpt-4o",
                    "api_key": None,
                    "api_url": None,
                }
            )
        )
        self.assertFalse(
            is_configured(
                {
                    "provider": PROVIDER_INSTALLED,
                    "model_name": None,
                    "api_key": None,
                    "api_url": None,
                }
            )
        )

    def test_ollama_requires_url(self) -> None:
        self.assertTrue(
            is_configured(
                {
                    "provider": PROVIDER_OLLAMA,
                    "model_name": None,
                    "api_key": None,
                    "api_url": "http://localhost:11434",
                }
            )
        )
        self.assertFalse(
            is_configured(
                {
                    "provider": PROVIDER_OLLAMA,
                    "model_name": "llama3.2",
                    "api_key": None,
                    "api_url": None,
                }
            )
        )

    def test_custom_requires_all_three(self) -> None:
        complete = {
            "provider": PROVIDER_CUSTOM,
            "model_name": "deepseek-chat",
            "api_key": "secret",
            "api_url": "https://api.deepseek.com",
        }
        self.assertTrue(is_configured(complete))
        for key in ("model_name", "api_key", "api_url"):
            partial = dict(complete)
            partial[key] = None
            self.assertFalse(is_configured(partial))

    def test_unknown_provider_is_not_configured(self) -> None:
        self.assertFalse(is_configured({"provider": "bogus"}))


class BuildLLMModelTests(unittest.TestCase):
    def _patch_ai(self):
        module, fake = _make_fake_ai()
        fake.calls["get_model"] = []
        fake.calls["get_custom_model"] = []
        return patch.dict(sys.modules, {"privacyforms_ai": module}), fake

    def test_installed_uses_get_model_and_sets_openai_key(self) -> None:
        env_backup = dict(os.environ)
        try:
            with self._patch_ai()[0]:
                model = build_llm_model(
                    {
                        "provider": PROVIDER_INSTALLED,
                        "model_name": "gpt-4o",
                        "api_key": "secret",
                        "api_url": None,
                    }
                )
            self.assertEqual(model, "model:gpt-4o")
            self.assertEqual(os.environ.get("OPENAI_API_KEY"), "secret")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_ollama_sets_host_and_prefixes_model(self) -> None:
        env_backup = dict(os.environ)
        try:
            with self._patch_ai()[0]:
                model = build_llm_model(
                    {
                        "provider": PROVIDER_OLLAMA,
                        "model_name": "llama3.2",
                        "api_key": None,
                        "api_url": "http://localhost:11434",
                    }
                )
            self.assertEqual(model, "model:ollama/llama3.2")
            self.assertEqual(os.environ.get("OLLAMA_HOST"), "http://localhost:11434")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_ollama_defaults_to_llama32(self) -> None:
        env_backup = dict(os.environ)
        try:
            with self._patch_ai()[0]:
                model = build_llm_model(
                    {
                        "provider": PROVIDER_OLLAMA,
                        "model_name": None,
                        "api_key": None,
                        "api_url": "http://localhost:11434",
                    }
                )
            self.assertEqual(model, "model:ollama/llama3.2")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_ollama_keeps_existing_prefix(self) -> None:
        env_backup = dict(os.environ)
        try:
            with self._patch_ai()[0]:
                model = build_llm_model(
                    {
                        "provider": PROVIDER_OLLAMA,
                        "model_name": "ollama/mistral",
                        "api_key": None,
                        "api_url": "http://localhost:11434",
                    }
                )
            self.assertEqual(model, "model:ollama/mistral")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_custom_uses_get_custom_model(self) -> None:
        patcher, fake = self._patch_ai()
        with patcher:
            model = build_llm_model(
                {
                    "provider": PROVIDER_CUSTOM,
                    "model_name": "deepseek-chat",
                    "api_key": "secret",
                    "api_url": "https://api.deepseek.com",
                }
            )
        self.assertEqual(model, "custom:deepseek-chat")
        self.assertEqual(
            fake.calls["get_custom_model"],
            [("deepseek-chat", "https://api.deepseek.com", "secret", {})],
        )

    def test_custom_incomplete_raises(self) -> None:
        with self._patch_ai()[0]:
            with self.assertRaises(RuntimeError):
                build_llm_model(
                    {
                        "provider": PROVIDER_CUSTOM,
                        "model_name": "deepseek-chat",
                        "api_key": None,
                        "api_url": "https://api.deepseek.com",
                    }
                )

    def test_installed_without_model_raises(self) -> None:
        with self._patch_ai()[0]:
            with self.assertRaises(RuntimeError):
                build_llm_model(
                    {
                        "provider": PROVIDER_INSTALLED,
                        "model_name": None,
                        "api_key": None,
                        "api_url": None,
                    }
                )

    def test_missing_privacyforms_ai_raises(self) -> None:
        with patch.dict(sys.modules, {"privacyforms_ai": None}):
            with self.assertRaises(RuntimeError):
                build_llm_model(
                    {
                        "provider": PROVIDER_INSTALLED,
                        "model_name": "gpt-4o",
                        "api_key": None,
                        "api_url": None,
                    }
                )


class LoadAISettingsIntegrationTests(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        registry = getUtility(IRegistry)
        self.settings = registry.forInterface(IFormsSettings, check=False)
        self._reset()

    def tearDown(self) -> None:
        self._reset()

    def _reset(self) -> None:
        for field in AI_FIELDS:
            try:
                if field == "ai_provider":
                    setattr(self.settings, field, "installed")
                elif field in ("ai_model", "ollama_url", "custom_api_url"):
                    setattr(self.settings, field, None)
                else:
                    setattr(self.settings, field, "")
            except AttributeError:
                pass

    def test_installed_provider_mapping(self) -> None:
        self.settings.ai_provider = "installed"
        self.settings.ai_model = "gpt-4o"
        self.settings.ai_api_key = "secret"
        result = load_ai_settings()
        self.assertEqual(
            result,
            {
                "provider": "installed",
                "model_name": "gpt-4o",
                "api_key": "secret",
                "api_url": None,
            },
        )

    def test_ollama_provider_mapping(self) -> None:
        self.settings.ai_provider = "ollama"
        self.settings.ollama_url = "http://localhost:11434"
        self.settings.ollama_model = "llama3.2"
        result = load_ai_settings()
        self.assertEqual(
            result,
            {
                "provider": "ollama",
                "model_name": "llama3.2",
                "api_key": None,
                "api_url": "http://localhost:11434",
            },
        )

    def test_custom_provider_mapping(self) -> None:
        self.settings.ai_provider = "custom"
        self.settings.custom_llm_name = "deepseek-chat"
        self.settings.custom_api_url = "https://api.deepseek.com"
        self.settings.custom_api_key = "secret"
        result = load_ai_settings()
        self.assertEqual(
            result,
            {
                "provider": "custom",
                "model_name": "deepseek-chat",
                "api_key": "secret",
                "api_url": "https://api.deepseek.com",
            },
        )

    def test_legacy_ollama_url_derives_provider(self) -> None:
        # Simulate a pre-upgrade install: no ai_provider record.
        registry = getUtility(IRegistry)
        record_name = "zopyx.surveyjs.interfaces.IFormsSettings.ai_provider"
        del registry.records[record_name]
        self.settings.ollama_url = "http://localhost:11434"
        self.settings.ai_model = "gpt-4o"
        result = load_ai_settings()
        self.assertEqual(result["provider"], "ollama")
        self.assertEqual(result["api_url"], "http://localhost:11434")

    def test_legacy_empty_config_derives_installed(self) -> None:
        registry = getUtility(IRegistry)
        record_name = "zopyx.surveyjs.interfaces.IFormsSettings.ai_provider"
        del registry.records[record_name]
        result = load_ai_settings()
        self.assertEqual(result["provider"], "installed")
        self.assertIsNone(result["model_name"])

    def test_values_are_stripped(self) -> None:
        self.settings.ai_provider = "ollama"
        self.settings.ollama_url = "http://localhost:11434"
        self.settings.ollama_model = "  llama3.2  "
        result = load_ai_settings()
        self.assertEqual(result["model_name"], "llama3.2")
        self.assertEqual(result["api_url"], "http://localhost:11434")


class ControlPanelAISettingsTests(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        registry = getUtility(IRegistry)
        self.settings = registry.forInterface(IFormsSettings, check=False)
        self._reset()
        self.view = FormsSettingsView.__new__(FormsSettingsView)
        self.view.context = self.portal

    def tearDown(self) -> None:
        self._reset()

    def _reset(self) -> None:
        for field in AI_FIELDS:
            try:
                if field == "ai_provider":
                    setattr(self.settings, field, "installed")
                elif field in ("ai_model", "ollama_url", "custom_api_url"):
                    setattr(self.settings, field, None)
                else:
                    setattr(self.settings, field, "")
            except AttributeError:
                pass

    def test_effective_ai_provider_uses_stored_value(self) -> None:
        self.settings.ai_provider = "custom"
        self.settings.custom_api_url = "https://api.deepseek.com"
        self.assertEqual(self.view._effective_ai_provider(self.settings), "custom")

    def test_effective_ai_provider_derives_ollama_from_legacy_url(self) -> None:
        registry = getUtility(IRegistry)
        record_name = "zopyx.surveyjs.interfaces.IFormsSettings.ai_provider"
        del registry.records[record_name]
        self.settings.ollama_url = "http://localhost:11434"
        self.assertEqual(self.view._effective_ai_provider(self.settings), "ollama")

    def test_effective_ai_provider_defaults_to_installed(self) -> None:
        registry = getUtility(IRegistry)
        record_name = "zopyx.surveyjs.interfaces.IFormsSettings.ai_provider"
        del registry.records[record_name]
        self.assertEqual(self.view._effective_ai_provider(self.settings), "installed")

    def test_save_custom_clears_other_groups(self) -> None:
        data = {
            "ai_provider": "custom",
            "custom_llm_name": "deepseek-chat",
            "custom_api_url": "https://api.deepseek.com",
            "custom_api_key": "secret",
            "ai_model": "gpt-4o",  # stale value from a previous mode
            "ollama_url": "http://localhost:11434",  # stale value
            "ollama_model": "llama3.2",
        }
        self.view._save_to_registry(data)
        self.assertEqual(self.settings.ai_provider, "custom")
        self.assertEqual(self.settings.custom_llm_name, "deepseek-chat")
        self.assertEqual(self.settings.custom_api_url, "https://api.deepseek.com")
        self.assertEqual(self.settings.custom_api_key, "secret")
        # non-active groups are cleared
        self.assertIsNone(self.settings.ai_model)
        self.assertEqual(self.settings.ai_api_key, "")
        self.assertIsNone(self.settings.ollama_url)
        self.assertEqual(self.settings.ollama_model, "")

    def test_save_installed_keeps_masked_key_and_clears_others(self) -> None:
        self.settings.ai_api_key = "stored-key"
        data = {
            "ai_provider": "installed",
            "ai_model": "gpt-4o",
            "ai_api_key": "",  # masked: empty submission keeps stored key
            "custom_llm_name": "deepseek-chat",
            "custom_api_url": "https://api.deepseek.com",
            "custom_api_key": "stale-secret",
        }
        self.view._save_to_registry(data)
        self.assertEqual(self.settings.ai_provider, "installed")
        self.assertEqual(self.settings.ai_model, "gpt-4o")
        self.assertEqual(self.settings.ai_api_key, "stored-key")
        self.assertEqual(self.settings.custom_llm_name, "")
        self.assertIsNone(self.settings.custom_api_url)
        self.assertEqual(self.settings.custom_api_key, "")

    def test_save_ollama_clears_installed_and_custom(self) -> None:
        data = {
            "ai_provider": "ollama",
            "ollama_url": "http://localhost:11434",
            "ollama_model": "llama3.2",
            "ai_model": "gpt-4o",
            "custom_api_key": "stale",
        }
        self.view._save_to_registry(data)
        self.assertEqual(self.settings.ai_provider, "ollama")
        self.assertEqual(self.settings.ollama_url, "http://localhost:11434")
        self.assertEqual(self.settings.ollama_model, "llama3.2")
        self.assertIsNone(self.settings.ai_model)
        self.assertEqual(self.settings.custom_api_key, "")

    def test_save_creates_missing_registry_records(self) -> None:
        # Simulate an install that was upgraded without re-importing the
        # registry profile step: the ai_provider record does not exist yet.
        registry = getUtility(IRegistry)
        record_name = "zopyx.surveyjs.interfaces.IFormsSettings.ai_provider"
        del registry.records[record_name]
        data = {
            "ai_provider": "ollama",
            "ollama_url": "http://localhost:11434",
            "ollama_model": "llama3.2",
        }
        self.view._save_to_registry(data)
        self.assertEqual(registry.records[record_name].value, "ollama")
        self.assertEqual(self.settings.ollama_url, "http://localhost:11434")

    def test_validate_kv_backend_rejects_unknown_value(self) -> None:
        errors = self.view._validate_data({"kv_cache_backend": "redis"})
        self.assertTrue(any("Caching backend" in error for error in errors))

    def test_validate_kv_rdbms_requires_dedicated_uri(self) -> None:
        errors = self.view._validate_data(
            {
                "kv_cache_backend": "rdbms",
                "database_uri": "sqlite:///var/results.db",
                "kv_cache_database_uri": "",
            }
        )
        self.assertTrue(any("Caching database URI" in error for error in errors))

    def test_validate_custom_requires_all_fields(self) -> None:
        errors = self.view._validate_data(
            {
                "ai_provider": "custom",
                "custom_llm_name": "deepseek-chat",
                "custom_api_url": "",
                "custom_api_key": "",
            }
        )
        self.assertTrue(
            any("Custom LLM configuration" in error for error in errors)
        )

    def test_validate_custom_complete_passes(self) -> None:
        errors = self.view._validate_data(
            {
                "ai_provider": "custom",
                "custom_llm_name": "deepseek-chat",
                "custom_api_url": "https://api.deepseek.com",
                "custom_api_key": "secret",
            }
        )
        self.assertEqual(errors, [])

    def test_validate_ollama_requires_url(self) -> None:
        errors = self.view._validate_data(
            {"ai_provider": "ollama", "ollama_url": ""}
        )
        self.assertTrue(any("Ollama configuration" in error for error in errors))

    def test_validate_installed_allows_unconfigured(self) -> None:
        # An unconfigured installed provider stays valid: AI stays optional.
        errors = self.view._validate_data({"ai_provider": "installed"})
        self.assertEqual(errors, [])


class FormsSettingsCachingSchemaTests(unittest.TestCase):
    def test_caching_is_a_dedicated_fieldset_without_kv_ui_labels(self) -> None:
        schema_path = (
            Path(__file__).parents[1]
            / "browser"
            / "static"
            / "forms_settings.json"
        )
        schema = json.loads(schema_path.read_text())
        storage = next(page for page in schema["pages"] if page["name"] == "page_storage")
        caching = next(
            element
            for element in storage["elements"]
            if element.get("name") == "panel_caching"
        )

        self.assertEqual(caching["type"], "panel")
        self.assertEqual(
            {element["name"] for element in caching["elements"]},
            {
                "kv_cache_backend",
                "kv_cache_directory",
                "kv_cache_database_uri",
                "kv_cache_lock_timeout_seconds",
            },
        )
        labels = []
        for element in caching["elements"]:
            for key in ("title", "description"):
                value = element.get(key, "")
                labels.append(value if isinstance(value, str) else json.dumps(value))
        labels.append(caching["title"])
        labels.append(caching["description"])
        self.assertTrue(all("KV" not in label for label in labels))
        self.assertIn("standalone", caching["description"])
        self.assertIn("ZEO", caching["description"])
        self.assertIn("NFS", caching["description"])
        self.assertIn("PostgreSQL", caching["description"])


class FormsSettingsInitialDataFunctionalTest(unittest.TestCase):
    """The AI fieldset must reflect the stored settings on load: the
    provider radiogroup is pre-selected from the registry and the related
    sub-fieldset is the visible one."""

    layer = ZOPYX_SURVEYJS_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        registry = getUtility(IRegistry)
        self.settings = registry.forInterface(IFormsSettings, check=False)

    def tearDown(self) -> None:
        for field in AI_FIELDS:
            try:
                if field == "ai_provider":
                    setattr(self.settings, field, "installed")
                elif field in ("ai_model", "ollama_url", "custom_api_url"):
                    setattr(self.settings, field, None)
                else:
                    setattr(self.settings, field, "")
            except AttributeError:
                pass
        import transaction

        transaction.commit()

    def _initial_data(self) -> dict:
        import transaction

        transaction.commit()
        from plone.testing.zope import Browser

        browser = Browser(self.layer["app"])
        browser.addHeader(
            "Authorization",
            f"Basic {TEST_USER_NAME}:{TEST_USER_PASSWORD}",
        )
        browser.open(self.portal.absolute_url() + "/@@forms-settings")
        match = re.search(
            r'<script type="application/json"[^>]*id="survey-add-initial-data"[^>]*>(.*?)</script>',
            browser.contents,
            re.S,
        )
        self.assertIsNotNone(match, "initial data script missing")
        return json.loads(match.group(1))

    def test_initial_data_preselects_ollama_provider(self) -> None:
        self.settings.ai_provider = "ollama"
        self.settings.ollama_url = "http://localhost:11434"
        self.settings.ollama_model = "llama3.2"
        data = self._initial_data()
        self.assertEqual(data["ai_provider"], "ollama")
        self.assertEqual(data["ollama_url"], "http://localhost:11434")
        self.assertEqual(data["ollama_model"], "llama3.2")

    def test_initial_data_preselects_custom_provider(self) -> None:
        self.settings.ai_provider = "custom"
        self.settings.custom_llm_name = "deepseek-chat"
        self.settings.custom_api_url = "https://api.deepseek.com"
        self.settings.custom_api_key = "secret"
        data = self._initial_data()
        self.assertEqual(data["ai_provider"], "custom")
        self.assertEqual(data["custom_llm_name"], "deepseek-chat")
        self.assertEqual(data["custom_api_url"], "https://api.deepseek.com")

    def test_initial_data_preselects_installed_provider(self) -> None:
        self.settings.ai_provider = "installed"
        self.settings.ai_model = "gpt-4o"
        data = self._initial_data()
        self.assertEqual(data["ai_provider"], "installed")
        self.assertEqual(data["ai_model"], "gpt-4o")

    def test_initial_data_derives_ollama_from_legacy_url(self) -> None:
        # Pre-upgrade install: no ai_provider record, but an Ollama URL.
        registry = getUtility(IRegistry)
        record_name = "zopyx.surveyjs.interfaces.IFormsSettings.ai_provider"
        del registry.records[record_name]
        self.settings.ollama_url = "http://localhost:11434"
        data = self._initial_data()
        self.assertEqual(data["ai_provider"], "ollama")


if __name__ == "__main__":
    unittest.main()
