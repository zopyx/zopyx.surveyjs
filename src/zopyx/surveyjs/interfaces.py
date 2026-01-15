# -*- coding: utf-8 -*-
"""Module where all interfaces, events and exceptions live."""

from zope.publisher.interfaces.browser import IDefaultBrowserLayer
from zope import schema
from zope.interface import Interface


class IZopyxSurveyjsLayer(IDefaultBrowserLayer):
    """Marker interface that defines a browser layer."""


class IPloneLoggingSettings(Interface):
    """Global logging settings stored in the Plone registry."""

    log_ip_addresses = schema.Bool(
        title="Log IP addresses",
        description="When enabled, save client IP addresses as part of the form data.",
        required=False,
        default=False,
    )

    log_user_agent = schema.Bool(
        title="Log user agent",
        description="When enabled, save user agent strings as part of the form data.",
        required=False,
        default=False,
    )


class IFormsSettings(IPloneLoggingSettings):
    """Settings for AI-powered form generation."""

    surveyjs_licence_key = schema.TextLine(
        title="SurveyJS License Key",
        description="License key for SurveyJS components (optional).",
        required=False,
        default="",
    )

    ai_model = schema.TextLine(
        title="AI Model",
        description="The LLM model to use for form generation (e.g., 'gpt-4', 'claude-3-sonnet-20240229')",
        required=False,
        default="",
    )

    ai_api_key = schema.Password(
        title="API Key",
        description="API key for the AI model provider. This will be stored securely.",
        required=False,
        default="",
    )

    ollama_url = schema.URI(
        title="Ollama URL",
        description="Optional Ollama server URL for AI-powered form generation (e.g., 'http://localhost:11434'). If set, the AI generator will use Ollama instead of the default LLM provider.",
        required=False,
    )

    ai_prompt_before = schema.Text(
        title="Prompt before",
        description="Text/Instructions to be used before the user's form prompt",
        required=False,
        default="",
    )

    ai_prompt_default = schema.Text(
        title="Default prompt",
        description="Default text for the user's prompt",
        required=False,
        default="",
    )

    ai_prompt_after = schema.Text(
        title="Prompt after",
        description="Text/Instructions to be used after the user's form prompt",
        required=False,
        default="",
    )
