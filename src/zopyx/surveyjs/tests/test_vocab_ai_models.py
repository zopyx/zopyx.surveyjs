# -*- coding: utf-8 -*-
from unittest.mock import patch

from plone.app.testing import setRoles, TEST_USER_ID
from zope.component import getUtility
from zope.schema.interfaces import IVocabularyFactory, IVocabularyTokenized
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING  # noqa

import unittest


class AIModelsVocabularyIntegrationTest(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self):
        """Custom shared utility setup for tests."""
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])

    def test_vocab_ai_models_factory_registered(self):
        vocab_name = "zopyx.surveyjs.AIModels"
        factory = getUtility(IVocabularyFactory, vocab_name)
        self.assertTrue(IVocabularyFactory.providedBy(factory))

    @patch("zopyx.surveyjs.vocabularies.ai_models._AI")
    def test_vocab_ai_models_returns_models(self, mock_ai):
        mock_ai.get_models.return_value = [
            {"key": "gpt-4o", "name": "Chat: gpt-4o", "provider": "openai"},
            {"key": "claude-3-opus", "name": "ClaudeMessages: claude-3-opus", "provider": "anthropic"},
        ]
        vocab_name = "zopyx.surveyjs.AIModels"
        factory = getUtility(IVocabularyFactory, vocab_name)
        vocabulary = factory(self.portal)
        self.assertTrue(IVocabularyTokenized.providedBy(vocabulary))
        self.assertIn("gpt-4o", [term.value for term in vocabulary])
        self.assertIn("claude-3-opus", [term.value for term in vocabulary])
        self.assertEqual(
            vocabulary.getTerm("gpt-4o").title,
            "gpt-4o (openai)",
        )
        self.assertEqual(
            vocabulary.getTerm("claude-3-opus").title,
            "claude-3-opus (anthropic)",
        )

    def test_vocab_ai_models_fallback_when_no_ai_module(self):
        vocab_name = "zopyx.surveyjs.AIModels"
        factory = getUtility(IVocabularyFactory, vocab_name)
        with patch(
            "zopyx.surveyjs.vocabularies.ai_models._AI",
            None,
        ):
            vocabulary = factory(self.portal)
            self.assertTrue(IVocabularyTokenized.providedBy(vocabulary))
            self.assertEqual(len(vocabulary), 1)
            self.assertEqual(vocabulary.by_token["empty"].value, "")
