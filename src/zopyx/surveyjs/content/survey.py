# -*- coding: utf-8 -*-
from plone.app.textfield import RichText
# from plone.autoform import directives
from plone.dexterity.content import Item
# from plone.namedfile import field as namedfile
from plone.supermodel import model
from zope.interface import implementer
# from plone.supermodel.directives import fieldset
# from z3c.form.browser.radio import RadioFieldWidget
from z3c.form.browser.checkbox import CheckBoxFieldWidget
from zope import schema
from zope.schema import Text
from zope.schema.vocabulary import SimpleVocabulary, SimpleTerm
from zopyx.surveyjs import _
from collective.z3cform.jsonwidget.browser.widget import JSONWidget
from plone.autoform import directives as form


survey_actions_vocabulary = SimpleVocabulary([
    SimpleTerm(value='store', title=_(u'Store')),
    SimpleTerm(value='mail', title=_(u'Mail')),
])


class ISurvey(model.Schema):
    """ Marker interface and Dexterity Python Schema for Survey
    """

    form.widget('actions', CheckBoxFieldWidget)
    actions = schema.Set(
        title=_(u"Actions"),
        description=_(u"Select how to handle survey submissions (multiple options possible)"),
        value_type=schema.Choice(vocabulary=survey_actions_vocabulary),
        required=True,
        default={'store'},
    )

    email_sender = schema.TextLine(
        title=_(u"E-Mail sender"),
        description=_(u"Email address of the sender"),
        required=False,
    )

    email_subject = schema.TextLine(
        title=_(u"E-Mail Subject"),
        description=_(u"Subject line for notification emails"),
        required=False,
    )



@implementer(ISurvey)
class Survey(Item):
    """ Content-type class for ISurvey
    """
