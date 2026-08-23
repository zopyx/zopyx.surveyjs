# -*- coding: utf-8 -*-
"""Tests for the AI provider connection test (``@@ai-test``).

Covers the per-provider test actions (Ollama /api/tags reachability check,
installed and custom model prompt round-trips), configuration validation,
the worker-thread timeout and the JSON endpoint contract.
"""

import json
import sys
import time
import types
import unittest
from unittest.mock import MagicMock, patch

import orjson

from zopyx.surveyjs.browser.controlpanel import AITestView
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_FUNCTIONAL_TESTING  # noqa


class FakeResponse:
    def __init__(self) -> None:
        self.status = None
        self.headers = {}
        self.body = b""

    def setStatus(self, status) -> None:  # noqa: N802
        self.status = status

    def setHeader(self, key, value) -> None:  # noqa: N802
        self.headers[key] = value

    def write(self, data) -> None:
        self.body += data


class FakeRequest:
    def __init__(self, body: bytes = b"") -> None:
        self.body = body
        self.response = FakeResponse()

    def get(self, key, default=None):
        if key == "BODY":
            return self.body
        return default


def _make_view(body=b""):
    view = AITestView.__new__(AITestView)
    view.request = FakeRequest(body)
    return view


class _FakeUrlResponse:
    def __init__(self, payload) -> None:
        self._payload = payload

    def read(self):
        return orjson.dumps(self._payload)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class OllamaTestTests(unittest.TestCase):
    def _view(self):
        return _make_view()

    def test_reachable_lists_models(self) -> None:
        view = self._view()
        with patch(
            "zopyx.surveyjs.browser.controlpanel.urlopen",
            return_value=_FakeUrlResponse(
                {"models": [{"name": "llama3.2"}, {"name": "mistral"}]}
            ),
        ):
            result = view._test_ollama(
                {"api_url": "http://localhost:11434", "model_name": ""}
            )
        self.assertTrue(result["ok"])
        self.assertIn("llama3.2", result["message"])
        self.assertIn("mistral", result["message"])
        self.assertIn("2 model(s)", result["message"])

    def test_reachable_with_missing_model_warns(self) -> None:
        view = self._view()
        with patch(
            "zopyx.surveyjs.browser.controlpanel.urlopen",
            return_value=_FakeUrlResponse({"models": [{"name": "llama3.2"}]}),
        ):
            result = view._test_ollama(
                {"api_url": "http://localhost:11434", "model_name": "gpt-4o"}
            )
        self.assertTrue(result["ok"])
        self.assertIn("'gpt-4o' was not found", result["message"])

    def test_reachable_model_name_prefix_match(self) -> None:
        view = self._view()
        with patch(
            "zopyx.surveyjs.browser.controlpanel.urlopen",
            return_value=_FakeUrlResponse({"models": [{"name": "llama3.2:latest"}]}),
        ):
            result = view._test_ollama(
                {"api_url": "http://localhost:11434", "model_name": "llama3.2"}
            )
        self.assertTrue(result["ok"])
        self.assertNotIn("was not found", result["message"])

    def test_reachable_without_models(self) -> None:
        view = self._view()
        with patch(
            "zopyx.surveyjs.browser.controlpanel.urlopen",
            return_value=_FakeUrlResponse({"models": []}),
        ):
            result = view._test_ollama({"api_url": "http://localhost:11434"})
        self.assertTrue(result["ok"])
        self.assertIn("No models found", result["message"])

    def test_unreachable_server(self) -> None:
        view = self._view()
        with patch(
            "zopyx.surveyjs.browser.controlpanel.urlopen",
            side_effect=Exception("Connection refused"),
        ):
            result = view._test_ollama(
                {"api_url": "http://localhost:11434", "model_name": ""}
            )
        self.assertFalse(result["ok"])
        self.assertIn("not reachable", result["message"])
        self.assertIn("Connection refused", result["message"])

    def test_missing_url(self) -> None:
        view = self._view()
        result = view._test_ollama({"api_url": ""})
        self.assertFalse(result["ok"])
        self.assertIn("Ollama URL is required", result["message"])

    def test_url_gets_trailing_slash_normalized(self) -> None:
        view = self._view()
        with patch(
            "zopyx.surveyjs.browser.controlpanel.urlopen",
            return_value=_FakeUrlResponse({"models": []}),
        ) as urlopen:
            view._test_ollama({"api_url": "http://localhost:11434/"})
        called_url = urlopen.call_args[0][0].full_url
        self.assertEqual(called_url, "http://localhost:11434/api/tags")


def _fake_privacyforms_ai(responder):
    """Stub privacyforms_ai module: AI.get_model returns a model whose
    prompt() yields the given text; send_prompt/extract_response_text are
    simple passthroughs."""

    class FakeAI:
        get_custom_model = staticmethod(
            lambda model_name, api_url, api_key, **kwargs: MagicMock(
                model_id=f"custom/{model_name}"
            )
        )
        get_model = staticmethod(
            lambda key: MagicMock(model_id=key, prompt=lambda prompt: None)
        )
        send_prompt = staticmethod(lambda model, prompt: responder(model))
        extract_response_text = staticmethod(lambda response: str(response))

    module = types.ModuleType("privacyforms_ai")
    module.AI = FakeAI
    return module


class InstalledAndCustomTestTests(unittest.TestCase):
    def _view(self):
        return _make_view()

    def _patch_ai(self, text="OK"):
        module = _fake_privacyforms_ai(lambda model: text)
        return patch.dict(sys.modules, {"privacyforms_ai": module})

    def test_installed_success(self) -> None:
        view = self._view()
        with self._patch_ai("OK"):
            with patch(
                "zopyx.surveyjs.browser.controlpanel.build_llm_model",
                return_value=object(),
            ):
                result = view._test_provider(
                    {
                        "provider": "installed",
                        "model_name": "gpt-4o",
                        "api_key": "secret",
                        "api_url": "",
                    }
                )
        self.assertTrue(result["ok"])
        self.assertIn("gpt-4o", result["message"])
        self.assertIn("OK", result["message"])

    def test_installed_missing_model(self) -> None:
        view = self._view()
        with patch(
            "zopyx.surveyjs.browser.controlpanel.getUtility",
            return_value=MagicMock(),
        ):
            result = view._test_provider(
                {"provider": "installed", "model_name": "", "api_key": "", "api_url": ""}
            )
        self.assertFalse(result["ok"])
        self.assertIn("AI model is required", result["message"])

    def test_installed_model_failure_reported(self) -> None:
        view = self._view()

        def fail(model):
            raise RuntimeError("boom")

        with patch.dict(
            sys.modules, {"privacyforms_ai": _fake_privacyforms_ai(fail)}
        ):
            with patch(
                "zopyx.surveyjs.browser.controlpanel.build_llm_model",
                return_value=object(),
            ):
                result = view._test_provider(
                    {
                        "provider": "installed",
                        "model_name": "gpt-4o",
                        "api_key": "secret",
                        "api_url": "",
                    }
                )
        self.assertFalse(result["ok"])
        self.assertIn("failed", result["message"])
        self.assertIn("boom", result["message"])

    def test_custom_success(self) -> None:
        view = self._view()
        with self._patch_ai("OK"):
            with patch(
                "zopyx.surveyjs.browser.controlpanel.build_llm_model",
                return_value=object(),
            ) as build:
                result = view._test_provider(
                    {
                        "provider": "custom",
                        "model_name": "deepseek-chat",
                        "api_url": "https://api.deepseek.com",
                        "api_key": "secret",
                    }
                )
        self.assertTrue(result["ok"])
        build.assert_called_once()
        settings = build.call_args[0][0]
        self.assertEqual(settings["provider"], "custom")
        self.assertEqual(settings["api_url"], "https://api.deepseek.com")

    def test_custom_incomplete(self) -> None:
        view = self._view()
        fake_registry = MagicMock()
        fake_registry.forInterface.return_value = MagicMock(custom_api_key="")
        with patch(
            "zopyx.surveyjs.browser.controlpanel.getUtility",
            return_value=fake_registry,
        ):
            result = view._test_provider(
                {
                    "provider": "custom",
                    "model_name": "deepseek-chat",
                    "api_url": "",
                    "api_key": "",
                }
            )
        self.assertFalse(result["ok"])
        self.assertIn("Custom LLM configuration requires", result["message"])

    def test_unknown_provider(self) -> None:
        view = self._view()
        result = view._test_provider({"provider": "bogus"})
        self.assertFalse(result["ok"])
        self.assertIn("Unknown provider", result["message"])

    def test_masked_key_falls_back_to_registry(self) -> None:
        view = self._view()
        fake_settings = MagicMock()
        fake_settings.ai_api_key = "stored-key"
        fake_registry = MagicMock()
        fake_registry.forInterface.return_value = fake_settings
        with patch(
            "zopyx.surveyjs.browser.controlpanel.getUtility",
            return_value=fake_registry,
        ):
            payload = {
                "provider": "installed",
                "model_name": "gpt-4o",
                "api_key": "",
                "api_url": "",
            }
            view._fill_masked_api_key(payload)
        self.assertEqual(payload["api_key"], "stored-key")

    def test_existing_key_not_overwritten(self) -> None:
        view = self._view()
        payload = {"provider": "custom", "api_key": "typed-key"}
        view._fill_masked_api_key(payload)
        self.assertEqual(payload["api_key"], "typed-key")


class TimeoutAndEndpointTests(unittest.TestCase):
    def test_run_test_returns_timeout_message(self) -> None:
        view = _make_view()
        view.TEST_TIMEOUT = 0.2

        def slow(payload):
            time.sleep(2)
            return {"ok": True}

        with patch.object(view, "_test_provider", side_effect=slow):
            result = view.run_test({"provider": "ollama"})
        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["message"])

    def test_run_test_returns_worker_exception_message(self) -> None:
        view = _make_view()
        with patch.object(
            view, "_test_provider", side_effect=RuntimeError("worker boom")
        ):
            result = view.run_test({"provider": "ollama"})
        self.assertFalse(result["ok"])
        self.assertIn("worker boom", result["message"])

    def test_call_invalid_payload_returns_400(self) -> None:
        view = _make_view(b"not json{")
        view()
        self.assertEqual(view.request.response.status, 400)
        self.assertIn(b"invalid-payload", view.request.response.body)

    def test_call_valid_payload_returns_json(self) -> None:
        view = _make_view(
            orjson.dumps({"provider": "ollama", "api_url": "http://x:11434"})
        )
        with patch.object(
            view, "_test_provider", return_value={"ok": True, "message": "fine"}
        ):
            view()
        self.assertEqual(view.request.response.status, 200)
        self.assertEqual(
            view.request.response.headers.get("content-type"), "application/json"
        )
        payload = json.loads(view.request.response.body)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message"], "fine")


class AITestEndpointFunctionalTest(unittest.TestCase):
    """The @@ai-test view is registered, permission-protected and answers
    JSON to authenticated POSTs."""

    layer = ZOPYX_SURVEYJS_FUNCTIONAL_TESTING

    def setUp(self) -> None:
        from plone.app.testing import setRoles, TEST_USER_ID

        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])

    def _browser(self):
        from plone.testing.zope import Browser

        import transaction

        transaction.commit()
        browser = Browser(self.layer["app"])
        browser.raiseHttpErrors = False
        return browser

    def test_authenticated_post_returns_json(self) -> None:
        from plone.app.testing import TEST_USER_NAME, TEST_USER_PASSWORD

        browser = self._browser()
        browser.addHeader(
            "Authorization",
            f"Basic {TEST_USER_NAME}:{TEST_USER_PASSWORD}",
        )
        with patch(
            "zopyx.surveyjs.browser.controlpanel.AITestView._test_provider",
            return_value={"ok": True, "message": "mocked ok"},
        ):
            browser.post(
                self.portal.absolute_url() + "/@@ai-test",
                orjson.dumps(
                    {"provider": "ollama", "api_url": "http://localhost:11434"}
                ),
                "application/json",
            )
        self.assertIn("200", browser.headers.get("Status", ""))
        self.assertIn("application/json", browser.headers.get("Content-type", ""))
        payload = json.loads(browser.contents)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message"], "mocked ok")

    def test_anonymous_post_is_rejected(self) -> None:
        browser = self._browser()
        browser.post(
            self.portal.absolute_url() + "/@@ai-test",
            orjson.dumps({"provider": "ollama", "api_url": "http://x"}),
            "application/json",
        )
        # Unauthorized users are redirected to the login page, never get
        # the JSON response.
        self.assertIn("/login", browser.url)


if __name__ == "__main__":
    unittest.main()
