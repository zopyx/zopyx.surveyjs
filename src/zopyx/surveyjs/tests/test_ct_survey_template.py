# -*- coding: utf-8 -*-
from plone import api
from plone.app.testing import setRoles, TEST_USER_ID
from plone.dexterity.interfaces import IDexterityFTI
from zope.component import createObject, queryUtility
from zopyx.surveyjs.content.survey import ISurvey
from zopyx.surveyjs.content.survey_template import ISurveyTemplate
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING  # noqa

import unittest


class SurveyTemplateIntegrationTest(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self):
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])

    def test_ct_survey_template_schema(self):
        fti = queryUtility(IDexterityFTI, name="SurveyTemplate")
        schema = fti.lookupSchema()
        self.assertEqual(ISurveyTemplate, schema)
        self.assertTrue(
            ISurveyTemplate.isOrExtends(ISurvey),
            "SurveyTemplate schema must extend ISurvey",
        )

    def test_ct_survey_template_fti(self):
        fti = queryUtility(IDexterityFTI, name="SurveyTemplate")
        self.assertTrue(fti)

    def test_ct_survey_template_factory(self):
        fti = queryUtility(IDexterityFTI, name="SurveyTemplate")
        factory = fti.factory
        obj = createObject(factory)

        self.assertTrue(
            ISurveyTemplate.providedBy(obj),
            "ISurveyTemplate not provided by {0}!".format(obj),
        )
        self.assertTrue(
            ISurvey.providedBy(obj),
            "ISurvey not provided by {0}!".format(obj),
        )

    def test_ct_survey_template_adding(self):
        setRoles(self.portal, TEST_USER_ID, ["Contributor"])
        obj = api.content.create(
            container=self.portal,
            type="SurveyTemplate",
            id="survey-template",
            title="Survey Template",
            template_json='{"title": "Demo"}',
        )

        self.assertTrue(
            ISurveyTemplate.providedBy(obj),
            "ISurveyTemplate not provided by {0}!".format(obj.id),
        )
        self.assertTrue(
            ISurvey.providedBy(obj),
            "ISurvey not provided by {0}!".format(obj.id),
        )

        parent = obj.__parent__
        self.assertIn("survey-template", parent.objectIds())

        api.content.delete(obj=obj)
        self.assertNotIn("survey-template", parent.objectIds())

    def test_ct_survey_template_globally_addable(self):
        setRoles(self.portal, TEST_USER_ID, ["Contributor"])
        fti = queryUtility(IDexterityFTI, name="SurveyTemplate")
        self.assertTrue(fti.global_allow, "{0} is not globally addable!".format(fti.id))
