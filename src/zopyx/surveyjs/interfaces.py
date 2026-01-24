# -*- coding: utf-8 -*-
"""Module where all interfaces, events and exceptions live."""

from zope.publisher.interfaces.browser import IDefaultBrowserLayer
from zope import schema
from zope.interface import Interface
from plone.supermodel.directives import fieldset
from zope.schema.vocabulary import SimpleVocabulary


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

    fieldset(
        "surveyjs",
        label="SurveyJS",
        fields=("surveyjs_license_key",),
    )

    fieldset(
        "ai_provider",
        label="AI Provider",
        fields=(
            "ai_model",
            "ai_api_key",
            "ollama_url",
        ),
    )

    fieldset(
        "ai_prompts",
        label="AI Prompts",
        fields=(
            "ai_prompt_before",
            "ai_prompt_default",
            "ai_prompt_after",
        ),
    )

    fieldset(
        "logging",
        label="Logging",
        fields=(
            "log_ip_addresses",
            "log_user_agent",
        ),
    )

    fieldset(
        "storage",
        label="Result Storage",
        fields=(
            "result_storage_backend",
            "database_uri",
        ),
    )

    fieldset(
        "security",
        label="Security",
        fields=(
            "authenticity_token_enabled",
            "authenticity_token_secret",
            "authenticity_token_ttl_seconds",
            "authenticity_token_issuer",
            "authenticity_token_audience",
        ),
    )

    surveyjs_license_key = schema.TextLine(
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

    result_storage_backend = schema.Choice(
        title="Result storage backend",
        description="Storage backend for survey results.",
        required=False,
        default="zodb",
        vocabulary=SimpleVocabulary.fromItems(
            [
                ("zodb", "zodb", "Plone (ZODB)"),
                ("rdbms", "rdbms", "Relational database"),
            ]
        ),
    )

    database_uri = schema.URI(
        title="Database URI",
        description=(
            "SQLAlchemy-style database URI for storing survey results "
            "(e.g. sqlite:///var/surveyjs-results.db, "
            "postgresql+psycopg2://user:pass@host/db)."
        ),
        required=False,
        default="sqlite:///var/surveyjs-results.db",
    )

    authenticity_token_enabled = schema.Bool(
        title="Enable authenticity token",
        description="When enabled, require a short-lived authenticity token for form submissions.",
        required=False,
        default=True,
    )

    authenticity_token_secret = schema.Password(
        title="Authenticity token secret",
        description="HMAC secret used to sign authenticity tokens (keep private).",
        required=False,
        default="",
    )

    authenticity_token_ttl_seconds = schema.Int(
        title="Authenticity token TTL (seconds)",
        description="Token lifetime in seconds.",
        required=False,
        default=600,
        min=60,
    )

    authenticity_token_issuer = schema.TextLine(
        title="Authenticity token issuer",
        description="Issuer claim for authenticity tokens.",
        required=False,
        default="zopyx.surveyjs",
    )

    authenticity_token_audience = schema.TextLine(
        title="Authenticity token audience",
        description="Audience claim for authenticity tokens.",
        required=False,
        default="zopyx.surveyjs",
    )
