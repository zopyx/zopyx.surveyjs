# -*- coding: utf-8 -*-
"""Module where all interfaces, events and exceptions live."""

from zope.publisher.interfaces.browser import IDefaultBrowserLayer
from zope import schema
from zope.interface import Interface


class IZopyxSurveyjsLayer(IDefaultBrowserLayer):
    """Marker interface that defines a browser layer."""


class IFormsSettings(Interface):
    """Settings for AI-powered form generation."""

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
