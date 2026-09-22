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

from zopyx.surveyjs.browser.ai import AIView
from zopyx.surveyjs.browser.controlpanel import FormsSettingsView
from zopyx.surveyjs.browser.services.ai import (
    PROVIDER_CUSTOM,
    PROVIDER_INSTALLED,
    PROVIDER_OLLAMA,
    apply_prompt_wrapper,
    build_llm_model,
    is_configured,
    load_ai_settings,
    load_prompt_settings,
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

PROMPT_FIELDS = ("ai_prompt_before", "ai_prompt_default", "ai_prompt_after")


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
        self.assertTrue(any("Custom LLM configuration" in error for error in errors))

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
        errors = self.view._validate_data({"ai_provider": "ollama", "ollama_url": ""})
        self.assertTrue(any("Ollama configuration" in error for error in errors))

    def test_validate_installed_allows_unconfigured(self) -> None:
        # An unconfigured installed provider stays valid: AI stays optional.
        errors = self.view._validate_data({"ai_provider": "installed"})
        self.assertEqual(errors, [])


class FormsSettingsCachingSchemaTests(unittest.TestCase):
    def test_storage_uses_dedicated_result_and_cache_fieldsets(self) -> None:
        schema_path = (
            Path(__file__).parents[1] / "browser" / "static" / "forms_settings.json"
        )
        schema = json.loads(schema_path.read_text())
        results_storage = next(
            page for page in schema["pages"] if page["name"] == "page_results_storage"
        )
        caching_storage = next(
            page for page in schema["pages"] if page["name"] == "page_caching_storage"
        )

        self.assertEqual(results_storage["navigationTitle"]["en"], "Results storage")
        self.assertIn(
            "always stored in Plone/ZODB", results_storage["description"]["en"]
        )
        result_storage = next(
            element
            for element in results_storage["elements"]
            if element.get("name") == "result_storage_backend"
        )
        self.assertIn(
            "submitted survey results only", result_storage["description"]["en"]
        )
        self.assertIn("remains in Plone/ZODB", result_storage["description"]["en"])

        self.assertEqual(caching_storage["navigationTitle"]["en"], "Caching storage")
        caching_fields = {element["name"] for element in caching_storage["elements"]}
        self.assertEqual(
            caching_fields,
            {
                "kv_cache_backend",
                "kv_cache_directory",
                "kv_cache_database_uri",
                "kv_cache_lock_timeout_seconds",
            },
        )
        self.assertNotIn("panel_caching", caching_fields)
        labels = []
        for element in caching_storage["elements"]:
            for key in ("title", "description"):
                value = element.get(key, "")
                labels.append(value if isinstance(value, str) else json.dumps(value))
        labels.append(caching_storage["title"]["en"])
        labels.append(caching_storage["description"])
        self.assertTrue(all("KV" not in label for label in labels))
        self.assertIn("standalone", caching_storage["description"])
        self.assertIn("ZEO", caching_storage["description"])
        self.assertIn("NFS", caching_storage["description"])
        self.assertIn("PostgreSQL", caching_storage["description"])


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


class ApplyPromptWrapperTests(unittest.TestCase):
    def test_unconfigured_wrapper_returns_prompt_unchanged(self) -> None:
        self.assertEqual(
            apply_prompt_wrapper(
                "  Create a form  ", {"before": "", "default": "", "after": ""}
            ),
            "Create a form",
        )

    def test_before_and_after_wrap_the_prompt(self) -> None:
        wrapped = apply_prompt_wrapper(
            "Create a form",
            {
                "before": "Use German labels.",
                "default": "not used here",
                "after": "Add a consent question.",
            },
        )
        self.assertEqual(
            wrapped,
            "Use German labels.\n\nCreate a form\n\nAdd a consent question.",
        )

    def test_blank_parts_are_dropped(self) -> None:
        self.assertEqual(
            apply_prompt_wrapper(
                "Only me", {"before": "   ", "default": "x", "after": ""}
            ),
            "Only me",
        )

    def test_missing_keys_are_tolerated(self) -> None:
        self.assertEqual(apply_prompt_wrapper("Prompt", {}), "Prompt")


class LoadPromptSettingsTests(unittest.TestCase):
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
        for field in PROMPT_FIELDS:
            setattr(self.settings, field, "")

    def test_defaults_are_empty(self) -> None:
        self.assertEqual(
            load_prompt_settings(), {"before": "", "default": "", "after": ""}
        )

    def test_values_are_stripped(self) -> None:
        self.settings.ai_prompt_before = "  Rule A  "
        self.settings.ai_prompt_default = "  Prefill  "
        self.settings.ai_prompt_after = "  Rule B  "
        self.assertEqual(
            load_prompt_settings(),
            {"before": "Rule A", "default": "Prefill", "after": "Rule B"},
        )


class AIPromptWiringTests(unittest.TestCase):
    """The global prompt settings must reach the generated prompts and
    prefill the prompt field of the AI workspace."""

    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        registry = getUtility(IRegistry)
        self.settings = registry.forInterface(IFormsSettings, check=False)
        for field in PROMPT_FIELDS:
            setattr(self.settings, field, "")

    def tearDown(self) -> None:
        for field in PROMPT_FIELDS:
            setattr(self.settings, field, "")

    def _view(self) -> AIView:
        view = AIView.__new__(AIView)
        view.context = self.portal
        return view

    def test_generation_prompt_wraps_the_user_request(self) -> None:
        self.settings.ai_prompt_before = "Always use German labels."
        self.settings.ai_prompt_after = "Always add a consent question."
        prompt = self._view()._build_generation_prompt("Create a contact form")
        self.assertLess(
            prompt.index("Always use German labels."),
            prompt.index("Create a contact form"),
        )
        self.assertLess(
            prompt.index("Create a contact form"),
            prompt.index("Always add a consent question."),
        )

    def test_generation_prompt_without_wrapper_keeps_the_request_verbatim(self) -> None:
        prompt = self._view()._build_generation_prompt("Create a contact form")
        self.assertIn("User request:\nCreate a contact form\n", prompt)

    def test_default_prompt_property_prefills_the_field(self) -> None:
        self.settings.ai_prompt_default = "Create a customer satisfaction survey."
        self.assertEqual(
            self._view().default_prompt, "Create a customer satisfaction survey."
        )

    def test_default_prompt_is_not_wrapped_into_the_request(self) -> None:
        self.settings.ai_prompt_default = "Prefill only."
        prompt = self._view()._build_generation_prompt("Real request")
        self.assertNotIn("Prefill only.", prompt)


if __name__ == "__main__":
    unittest.main()
