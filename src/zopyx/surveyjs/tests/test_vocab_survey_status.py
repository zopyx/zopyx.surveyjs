# -*- coding: utf-8 -*-
from plone.app.testing import setRoles, TEST_USER_ID
from zope.component import getUtility
from zope.schema.interfaces import IVocabularyFactory, IVocabularyTokenized
from zopyx.surveyjs import _
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING  # noqa

import unittest


class SurveyStatusIntegrationTest(unittest.TestCase):

    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self):
        """Custom shared utility setup for tests."""
        self.portal = self.layer['portal']
        setRoles(self.portal, TEST_USER_ID, ['Manager'])

    def test_vocab_survey_status(self):
        vocab_name = 'zopyx.surveyjs.SurveyStatus'
        factory = getUtility(IVocabularyFactory, vocab_name)
        self.assertTrue(IVocabularyFactory.providedBy(factory))

        vocabulary = factory(self.portal)
        self.assertTrue(IVocabularyTokenized.providedBy(vocabulary))
        self.assertEqual(
            vocabulary.getTerm('sony-a7r-iii').title,
            _(u'Sony Aplha 7R III'),
        )
