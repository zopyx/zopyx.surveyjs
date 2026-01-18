from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from zopyx.surveyjs.browser import ai_generator


class FakeResponse:
    def __init__(self, text_value, callable_text: bool = False) -> None:
        if callable_text:
            self.text = lambda: text_value
        else:
            self.text = text_value


class FakeModel:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.last_prompt = None
        self.last_attachments = None

    def prompt(self, prompt, attachments=None):
        self.last_prompt = prompt
        self.last_attachments = attachments
        return self.response


class FakeLLMModule:
    def __init__(self, model_name: str, response: FakeResponse) -> None:
        self._model_name = model_name
        self._model = FakeModel(response)
        self.last_model_name = None

    def get_default_model(self):
        return self._model_name

    def get_model(self, model_name):
        self.last_model_name = model_name
        return self._model


class FakeAttachment:
    def __init__(self, value):
        self.value = value

    @classmethod
    def from_path(cls, path):
        return cls(path)


class AIGeneratorTests(unittest.TestCase):
    def test_strip_markdown_json(self) -> None:
        text = "```json\n{\"a\": 1}\n```"
        self.assertEqual(ai_generator.strip_markdown_json(text), "{\"a\": 1}")

    def test_generate_survey_json_uses_default_model_and_api_key(self) -> None:
        response = FakeResponse("{\"ok\": true}", callable_text=True)
        fake_llm = FakeLLMModule("gpt-4", response)
        original_key = os.environ.get("OPENAI_API_KEY")
        try:
            with patch.dict(sys.modules, {"llm": fake_llm}):
                output = ai_generator.generate_survey_json(
                    "Question?", api_key="secret"
                )
                self.assertEqual(output, "{\"ok\": true}")
                self.assertEqual(fake_llm.last_model_name, "gpt-4")
                self.assertEqual(os.environ.get("OPENAI_API_KEY"), "secret")
        finally:
            if original_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original_key

    def test_generate_survey_json_with_ollama_prefixes_model(self) -> None:
        response = FakeResponse("{\"ok\": true}")
        fake_llm = FakeLLMModule("llama2", response)
        original_host = os.environ.get("OLLAMA_HOST")
        try:
            with patch.dict(sys.modules, {"llm": fake_llm}):
                output = ai_generator.generate_survey_json(
                    "Question?", model_name="llama2", ollama_url="http://ollama"
                )
                self.assertEqual(output, "{\"ok\": true}")
                self.assertEqual(fake_llm.last_model_name, "ollama/llama2")
                self.assertEqual(os.environ.get("OLLAMA_HOST"), "http://ollama")
        finally:
            if original_host is None:
                os.environ.pop("OLLAMA_HOST", None)
            else:
                os.environ["OLLAMA_HOST"] = original_host

    def test_generate_survey_json_from_image_uses_attachment(self) -> None:
        response = FakeResponse("{\"ok\": true}")
        fake_llm = FakeLLMModule("gpt-4", response)
        fake_llm.Attachment = FakeAttachment

        with patch.dict(sys.modules, {"llm": fake_llm}):
            output = ai_generator.generate_survey_json_from_image(
                "/tmp/fake.png", "Describe the form", model_name="gpt-4"
            )

        self.assertEqual(output, "{\"ok\": true}")
        attachments = fake_llm._model.last_attachments
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].value, "/tmp/fake.png")

    def test_refine_survey_json_sets_anthropic_key(self) -> None:
        response = FakeResponse("{\"ok\": true}", callable_text=False)
        fake_llm = FakeLLMModule("claude-3", response)
        original_key = os.environ.get("ANTHROPIC_API_KEY")
        try:
            with patch.dict(sys.modules, {"llm": fake_llm}):
                output = ai_generator.refine_survey_json(
                    {"pages": []}, "Add a question", api_key="anthropic-key"
                )
                self.assertEqual(output, "{\"ok\": true}")
                self.assertEqual(fake_llm.last_model_name, "claude-3")
                self.assertEqual(os.environ.get("ANTHROPIC_API_KEY"), "anthropic-key")
        finally:
            if original_key is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = original_key
