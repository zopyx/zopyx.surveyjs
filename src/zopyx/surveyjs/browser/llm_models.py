"""View for listing available LLM models."""

from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile


class LLMModelsView(BrowserView):
    """List available LLM models from the llm library."""

    index = ViewPageTemplateFile("llm_models.pt")

    def __call__(self):
        return self.index()

    def get_models(self):
        """Get all registered LLM models with their details."""
        try:
            import llm
        except ImportError:
            return []

        models_with_aliases = llm.get_models_with_aliases()
        models = []

        for mwa in models_with_aliases:
            model = mwa.model
            if not model:
                continue

            model_info = {
                "model_id": model.model_id,
                "aliases": sorted(mwa.aliases),
                "can_stream": getattr(model, "can_stream", False),
                "supports_schema": getattr(model, "supports_schema", False),
                "supports_tools": getattr(model, "supports_tools", False),
                "attachment_types": sorted(getattr(model, "attachment_types", set())),
                "is_async": mwa.async_model is not None,
                "class_name": model.__class__.__name__,
            }
            models.append(model_info)

        # Sort by model_id for consistent display
        models.sort(key=lambda x: x["model_id"].lower())
        return models

    def has_llm(self):
        """Check if the llm library is available."""
        try:
            import llm  # noqa: F401
            return True
        except ImportError:
            return False
