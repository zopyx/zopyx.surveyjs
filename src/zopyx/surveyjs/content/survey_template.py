# -*- coding: utf-8 -*-
from plone.autoform import directives as form
from zopyx.surveyjs.content.survey import ISurvey, Survey
from plone.supermodel import model
from plone.dexterity.content import Item
from z3c.form.browser.textarea import TextAreaFieldWidget
from zope import schema
from zope.interface import implementer, invariant, Invalid
import json

from zopyx.surveyjs import _


def _parse_template_json(value: str) -> dict:
    if not value:
        raise Invalid(_("Template JSON is required."))
    try:
        parsed = json.loads(value)
    except Exception as exc:
        raise Invalid(_("Template JSON must be valid JSON.")) from exc
    if not isinstance(parsed, dict):
        raise Invalid(_("Template JSON must be a JSON object."))
    return parsed


class ISurveyTemplate(ISurvey):
    """Marker interface and Dexterity Python Schema for SurveyTemplate"""

    form.widget("template_json", TextAreaFieldWidget, rows=20, cols=80)
    template_json = schema.Text(
        title=_("Template JSON"),
        description=_("SurveyJS JSON definition for this template."),
        required=True,
    )

    @invariant
    def validate_template_json(data):
        _parse_template_json(data.template_json)


@implementer(ISurveyTemplate)
class SurveyTemplate(Item):
    """Content-type class for ISurveyTemplate"""
