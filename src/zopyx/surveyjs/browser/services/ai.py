"""Registry-backed helpers for AI-related service configuration.

The AI provider settings support three mutually exclusive provider modes:

- ``installed``: an LLM model from the ``llm`` plugin registry (``ai_model``),
  optionally with an API key (``ai_api_key``).
- ``ollama``: a local Ollama server (``ollama_url``) with an optional model
  name (``ollama_model``; defaults to ``llama3.2``).
- ``custom``: an arbitrary OpenAI-compatible endpoint (``custom_llm_name``,
  ``custom_api_url``, ``custom_api_key``).

``load_ai_settings()`` normalizes the registry state into a single dict and
``build_llm_model()`` turns it into a concrete ``llm`` model instance.
"""

from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from ...interfaces import IFormsSettings

PROVIDER_INSTALLED = "installed"
PROVIDER_OLLAMA = "ollama"
PROVIDER_CUSTOM = "custom"

PROVIDERS = (PROVIDER_INSTALLED, PROVIDER_OLLAMA, PROVIDER_CUSTOM)

# Registry field names per provider group. Used to enforce mutual
# exclusivity when saving: fields of non-active groups are cleared.
PROVIDER_FIELDS = {
    PROVIDER_INSTALLED: ("ai_model", "ai_api_key"),
    PROVIDER_OLLAMA: ("ollama_url", "ollama_model"),
    PROVIDER_CUSTOM: ("custom_llm_name", "custom_api_url", "custom_api_key"),
}


def _strip(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def load_ai_settings():
    """Load and normalize AI provider settings from the Plone registry.

    Returns a dict with keys:
        provider: "installed", "ollama", "custom" or None
        model_name: model key/name of the active provider (or None)
        api_key: API key for installed/custom providers (or None)
        api_url: Ollama server URL or custom API base URL (or None)
    """
    registry = getUtility(IRegistry)
    settings = registry.forInterface(IFormsSettings, check=False)

    provider = getattr(settings, "ai_provider", None)
    if provider not in PROVIDERS:
        # Legacy installs: derive the provider from populated fields.
        provider = None

    model_name = _strip(getattr(settings, "ai_model", None))
    api_key = _strip(getattr(settings, "ai_api_key", None))
    ollama_url = _strip(getattr(settings, "ollama_url", None))
    ollama_model = _strip(getattr(settings, "ollama_model", None))
    custom_llm_name = _strip(getattr(settings, "custom_llm_name", None))
    custom_api_url = _strip(getattr(settings, "custom_api_url", None))
    custom_api_key = _strip(getattr(settings, "custom_api_key", None))

    if provider is None:
        if ollama_url:
            provider = PROVIDER_OLLAMA
        elif custom_api_url:
            provider = PROVIDER_CUSTOM
        else:
            provider = PROVIDER_INSTALLED

    if provider == PROVIDER_OLLAMA:
        return {
            "provider": provider,
            "model_name": ollama_model,
            "api_key": None,
            "api_url": ollama_url,
        }
    if provider == PROVIDER_CUSTOM:
        return {
            "provider": provider,
            "model_name": custom_llm_name,
            "api_key": custom_api_key,
            "api_url": custom_api_url,
        }
    return {
        "provider": provider,
        "model_name": model_name,
        "api_key": api_key,
        "api_url": None,
    }


def is_configured(settings) -> bool:
    """Return True when the active provider has enough config to run.

    Ollama works with just a URL (model defaults to 'llama3.2'); the
    installed and custom providers need a model name, and custom also
    needs URL and API key.
    """
    provider = settings.get("provider")
    if provider == PROVIDER_OLLAMA:
        return bool(settings.get("api_url"))
    if provider == PROVIDER_CUSTOM:
        return bool(
            settings.get("model_name")
            and settings.get("api_url")
            and settings.get("api_key")
        )
    if provider == PROVIDER_INSTALLED:
        return bool(settings.get("model_name"))
    return False


def build_llm_model(settings):
    """Resolve the active provider configuration to an llm model instance.

    Uses privacyforms_ai's AI helper. Raises RuntimeError when the package
    is unavailable or the configuration is incomplete.

    Args:
        settings: dict as returned by ``load_ai_settings()``.

    Returns:
        An ``llm.models.Model`` instance ready for ``send_prompt()``.
    """
    try:
        from privacyforms_ai import AI
    except ImportError:
        raise RuntimeError("privacyforms_ai package not found") from None

    provider = settings.get("provider")
    model_name = settings.get("model_name")
    api_key = settings.get("api_key")
    api_url = settings.get("api_url")

    if provider == PROVIDER_CUSTOM:
        if not (model_name and api_url and api_key):
            raise RuntimeError(
                "Custom LLM configuration incomplete: LLM name, API URL "
                "and API key are required."
            )
        return AI.get_custom_model(
            model_name=model_name,
            api_url=api_url,
            api_key=api_key,
        )

    if provider == PROVIDER_OLLAMA:
        import os

        if not api_url:
            raise RuntimeError(
                "Ollama URL not configured. Configure an AI model in Forms settings."
            )
        os.environ["OLLAMA_HOST"] = api_url
        effective_model = model_name or "llama3.2"
        if not effective_model.startswith("ollama/"):
            effective_model = f"ollama/{effective_model}"
        return AI.get_model(effective_model)

    # installed provider (or legacy fallback)
    if not model_name:
        raise RuntimeError(
            "No AI model configured. Configure an AI model in Forms settings."
        )
    if api_key:
        import os

        key = model_name.lower()
        if "gpt" in key or "openai" in key:
            os.environ["OPENAI_API_KEY"] = api_key
        elif "claude" in key or "anthropic" in key:
            os.environ["ANTHROPIC_API_KEY"] = api_key
    return AI.get_model(model_name)
