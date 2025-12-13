# -*- coding: utf-8 -*-
from plone.app.textfield import RichText
# from plone.autoform import directives
from plone.dexterity.content import Item
# from plone.namedfile import field as namedfile
from plone.supermodel import model
from zope.interface import implementer
# from plone.supermodel.directives import fieldset
# from z3c.form.browser.radio import RadioFieldWidget
from zope import schema
from zope.schema import Text
from zopyx.surveyjs import _
from collective.z3cform.jsonwidget.browser.widget import JSONWidget
from plone.autoform import directives as form



class ISurvey(model.Schema):
    """ Marker interface and Dexterity Python Schema for Survey
    """



@implementer(ISurvey)
class Survey(Item):
    """ Content-type class for ISurvey
    """
