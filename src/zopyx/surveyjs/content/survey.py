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


DEFAULT_FORM_JSON = """{
 "logoPosition": "right",
 "pages": [
  {
   "name": "This is Page 1",
   "elements": [
    {
     "type": "text",
     "name": "question1",
     "title": "Hello World",
     "description": "Description for Hello World field",
     "placeHolder": "input goes here"
    }
   ],
   "title": "This is Page 1 Title",
   "description": "This is Page 1 Description"
  }
 ]
}
"""

class ISurvey(model.Schema):
    """ Marker interface and Dexterity Python Schema for Survey
    """
    # If you want, you can load a xml model created TTW here
    # and customize it in Python:

    # model.load('survey.xml')

    # directives.widget(level=RadioFieldWidget)
    # level = schema.Choice(
    #     title=_(u'Sponsoring Level'),
    #     vocabulary=LevelVocabulary,
    #     required=True
    # )

    survey_status = schema.Choice(
            title=_("survey status", "Survey status"),
            vocabulary="zopyx.surveyjs.SurveyStatus"
            )

    form.widget("form_json", JSONWidget)
    form_json = Text(
        title=_(u'Form JSON'),
        required=True,
        default=DEFAULT_FORM_JSON
    )

    # url = schema.URI(
    #     title=_(u'Link'),
    #     required=False
    # )

    # fieldset('Images', fields=['logo', 'advertisement'])
    # logo = namedfile.NamedBlobImage(
    #     title=_(u'Logo'),
    #     required=False,
    # )

    # advertisement = namedfile.NamedBlobImage(
    #     title=_(u'Advertisement (Gold-sponsors and above)'),
    #     required=False,
    # )

    # directives.read_permission(notes='cmf.ManagePortal')
    # directives.write_permission(notes='cmf.ManagePortal')
    # notes = RichText(
    #     title=_(u'Secret Notes (only for site-admins)'),
    #     required=False
    # )


@implementer(ISurvey)
class Survey(Item):
    """ Content-type class for ISurvey
    """
