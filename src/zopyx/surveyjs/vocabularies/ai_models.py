# -*- coding: utf-8 -*-

from zope.interface import implementer
from zope.schema.interfaces import IVocabularyFactory
from zope.schema.vocabulary import SimpleTerm, SimpleVocabulary

from zopyx.surveyjs import _

try:
    from privacyforms_ai import AI as _AI
except ImportError:
    _AI = None  # type: ignore[misc,assignment]


@implementer(IVocabularyFactory)
class AIModelsVocabulary(object):
    """Vocabulary of installed LLM models introspected via privacyforms_ai."""

    def __call__(self, context):
        terms = []
        ai = _AI

        if ai is not None:
            try:
                models = ai.get_models()
            except Exception:
                models = []
            for model in models:
                key = model.get("key")
                provider = model.get("provider")
                if key:
                    title = key
                    if provider:
                        title = f"{key} ({provider})"
                    terms.append(
                        SimpleTerm(
                            value=key,
                            token=str(key),
                            title=title,
                        )
                    )

        if not terms:
            terms.append(
                SimpleTerm(
                    value="",
                    token="empty",
                    title=_("No LLM models available"),
                )
            )

        return SimpleVocabulary(terms)


AIModelsVocabularyFactory = AIModelsVocabulary()
