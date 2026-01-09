# -*- coding: utf-8 -*-
"""Event definitions for zopyx.surveyjs."""

from zope.interface.interfaces import IObjectEvent
from zope.interface import Attribute
from zope.interface import implementer
from zope.lifecycleevent import ObjectEvent


class ISurveyJSFormSubmittedEvent(IObjectEvent):
    """Event fired when a SurveyJS form is submitted."""

    form_data = Attribute("Submitted form data")


@implementer(ISurveyJSFormSubmittedEvent)
class SurveyJSFormSubmitted(ObjectEvent):
    """SurveyJS form submission event."""

    def __init__(self, context, form_data):
        super().__init__(context)
        self.form_data = form_data
