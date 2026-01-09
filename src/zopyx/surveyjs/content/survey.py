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
from plone.supermodel.directives import fieldset
from zope.annotation.interfaces import IAnnotations

from ..browser.views import FORM_VERSIONS_KEY, RESULTS_KEY

survey_actions_vocabulary = SimpleVocabulary(
    [
        SimpleTerm(value="store", title=_("Store")),
        SimpleTerm(value="mail", title=_("Mail")),
    ]
)

survey_formats_vocabulary = SimpleVocabulary(
    [
        SimpleTerm(value="text", title=_("Text (.txt)")),
        SimpleTerm(value="md", title=_("Markdown (.md)")),
        SimpleTerm(value="html", title=_("HTML (.html)")),
        SimpleTerm(value="pdf", title=_("PDF (.pdf)")),
        SimpleTerm(value="csv", title=_("CSV (.csv)")),
        SimpleTerm(value="xlsx", title=_("Excel (.xlsx)")),
        SimpleTerm(value="xml", title=_("XML (.xml)")),
        SimpleTerm(value="docx", title=_("Word (.docx)")),
        SimpleTerm(value="json", title=_("JSON (.json)")),
    ]
)


class ISurvey(model.Schema):
    """Marker interface and Dexterity Python Schema for Survey"""

    fieldset(
        "mail",
        label=_("Mail"),
        fields=(
            "email_sender",
            "email_subject",
            "email_to",
            "email_formats",
            "email_body",
        ),
    )

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

    email_to = schema.TextLine(
        title=_("E-Mail recipient"),
        description=_("Email address to receive results"),
        required=False,
    )

    email_subject = schema.TextLine(
        title=_("Subject"),
        description=_("Subject line for notification emails"),
        required=False,
    )

    form.widget("email_formats", CheckBoxFieldWidget)
    email_formats = schema.Set(
        title=_("Formats"),
        description=_("Select export formats to include"),
        value_type=schema.Choice(vocabulary=survey_formats_vocabulary),
        required=False,
        default=set(),
    )

    email_body = schema.Text(
        title=_("Body"),
        description=_("Body text for notification emails"),
        required=False,
    )


@implementer(ISurvey)
class Survey(Item):
    """Content-type class for ISurvey"""

    def __init__(self, *args, **kw):
        for k,v in kw.items():
            setattr(self, k, v)

        annos = IAnnotations(self)
        annos[FORM_VERSIONS_KEY] = OOBTree()
        annos[RESULTS_KEY] = OOBTree()

        super().__init__(*args, **kw)
