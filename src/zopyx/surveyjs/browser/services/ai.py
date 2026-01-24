from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from ...interfaces import IFormsSettings


def load_ai_settings():
    registry = getUtility(IRegistry)
    settings = registry.forInterface(IFormsSettings, check=False)

    model_name = getattr(settings, "ai_model", None)
    api_key = getattr(settings, "ai_api_key", None)
    ollama_url = getattr(settings, "ollama_url", None)

    if model_name:
        model_name = model_name.strip()
    if api_key:
        api_key = api_key.strip()
    if ollama_url:
        ollama_url = ollama_url.strip()

    return model_name or None, api_key or None, ollama_url or None
