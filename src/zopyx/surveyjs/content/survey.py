# -*- coding: utf-8 -*-
# from plone.autoform import directives
from plone.dexterity.content import Item

# from plone.namedfile import field as namedfile
from plone.supermodel import model
from zope.interface import implementer

# from plone.supermodel.directives import fieldset
# from z3c.form.browser.radio import RadioFieldWidget
from z3c.form.browser.checkbox import CheckBoxFieldWidget
from zope import schema
from BTrees.OOBTree import OOBTree
from zope.schema.vocabulary import SimpleVocabulary, SimpleTerm
from zopyx.surveyjs import _
from plone.autoform import directives as form
from zope.annotation.interfaces import IAnnotations

from ..browser.views import FORM_VERSIONS_KEY, RESULTS_KEY

survey_actions_vocabulary = SimpleVocabulary(
    [
        SimpleTerm(value="store", title=_("Store")),
        SimpleTerm(value="mail", title=_("Mail")),
    ]
)


class ISurvey(model.Schema):
    """Marker interface and Dexterity Python Schema for Survey"""

    form.widget("actions", CheckBoxFieldWidget)
    actions = schema.Set(
        title=_("Actions"),
        description=_(
            "Select how to handle survey submissions (multiple options possible)"
        ),
        value_type=schema.Choice(vocabulary=survey_actions_vocabulary),
        required=True,
        default={"store"},
    )

    email_sender = schema.TextLine(
        title=_("E-Mail sender"),
        description=_("Email address of the sender"),
        required=False,
    )

    email_subject = schema.TextLine(
        title=_("E-Mail Subject"),
        description=_("Subject line for notification emails"),
        required=False,
    )

    allow_embedding = schema.Bool(
        title=_("Allow Embedding"),
        description=_("Allow this survey to be embedded in an iframe on external websites"),
        required=False,
        default=False,
    )


@implementer(ISurvey)
class Survey(Item):
    """Content-type class for ISurvey"""

    def __init__(self):
        annos = IAnnotations(self)
        annos[FORM_VERSIONS_KEY] = OOBTree()
        annos[RESULTS_KEY] = OOBTree()
