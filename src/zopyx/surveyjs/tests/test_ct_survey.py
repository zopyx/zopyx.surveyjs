# -*- coding: utf-8 -*-
from plone import api
from plone.app.testing import setRoles, TEST_USER_ID
from plone.dexterity.interfaces import IDexterityFTI
from zope.component import createObject, queryUtility
from zopyx.surveyjs.content.survey import ISurvey  # NOQA E501
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING  # noqa

import unittest


class SurveyIntegrationTest(unittest.TestCase):

    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self):
        """Custom shared utility setup for tests."""
        self.portal = self.layer['portal']
        setRoles(self.portal, TEST_USER_ID, ['Manager'])
        self.parent = self.portal

    def test_ct_survey_schema(self):
        fti = queryUtility(IDexterityFTI, name='Survey')
        schema = fti.lookupSchema()
        self.assertEqual(ISurvey, schema)

    def test_ct_survey_fti(self):
        fti = queryUtility(IDexterityFTI, name='Survey')
        self.assertTrue(fti)

    def test_ct_survey_factory(self):
        fti = queryUtility(IDexterityFTI, name='Survey')
        factory = fti.factory
        obj = createObject(factory)

        self.assertTrue(
            ISurvey.providedBy(obj),
            u'ISurvey not provided by {0}!'.format(
                obj,
            ),
        )

    def test_ct_survey_adding(self):
        setRoles(self.portal, TEST_USER_ID, ['Contributor'])
        obj = api.content.create(
            container=self.portal,
            type='Survey',
            id='survey',
        )

        self.assertTrue(
            ISurvey.providedBy(obj),
            u'ISurvey not provided by {0}!'.format(
                obj.id,
            ),
        )

        parent = obj.__parent__
        self.assertIn('survey', parent.objectIds())

        # check that deleting the object works too
        api.content.delete(obj=obj)
        self.assertNotIn('survey', parent.objectIds())

    def test_ct_survey_globally_addable(self):
        setRoles(self.portal, TEST_USER_ID, ['Contributor'])
        fti = queryUtility(IDexterityFTI, name='Survey')
        self.assertTrue(
            fti.global_allow,
            u'{0} is not globally addable!'.format(fti.id)
        )
