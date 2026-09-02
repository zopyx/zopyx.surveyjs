# -*- coding: utf-8 -*-

from zope.annotation.interfaces import IAnnotations
from zope.component.hooks import getSite
from zope.interface import implementer
from zope.schema.interfaces import IVocabularyFactory
from zope.schema.vocabulary import SimpleTerm, SimpleVocabulary

from zopyx.surveyjs import _


@implementer(IVocabularyFactory)
class SurveyThemesVocabulary(object):
    """Vocabulary of available themes from the theme manager."""

    def __call__(self, context):
        terms = []
        try:
            from zopyx.surveyjs.browser.services import themes as themes_service

            site = getSite()
            if site is not None:
                annotations = IAnnotations(site)
                themes = themes_service.list_themes(annotations)
                for theme in themes:
                    tid = theme.get("id")
                    name = theme.get("name", "Unnamed")
                    if tid:
                        terms.append(
                            SimpleTerm(
                                value=str(tid),
                                token=str(tid),
                                title=name,
                            )
                        )
        except Exception:
            pass

        if not terms:
            terms.append(
                SimpleTerm(
                    value="",
                    token="empty",
                    title=_("No themes available"),
                )
            )

        return SimpleVocabulary(terms)


SurveyThemesVocabularyFactory = SurveyThemesVocabulary()