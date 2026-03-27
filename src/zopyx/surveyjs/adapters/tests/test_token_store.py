# -*- coding: utf-8 -*-
"""Tests for the token store adapter."""

from plone import api
from plone.app.testing import setRoles, TEST_USER_ID
from zope.component import getAdapter
from zopyx.surveyjs.content.survey import ISurvey
from zopyx.surveyjs.interfaces import ITokenStore
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING
from zopyx.surveyjs.constants import TOKEN_STORE_KEY

import unittest


class TokenStoreAdapterTest(unittest.TestCase):
    """Test the token store adapter."""

    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self):
        """Set up test fixtures."""
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        
        # Create a survey for testing
        self.survey = api.content.create(
            container=self.portal,
            type="Survey",
            id="test-survey",
            title="Test Survey",
        )
        
        # Get the token store adapter
        self.token_store = getAdapter(self.survey, ITokenStore)

    def tearDown(self):
        """Clean up after tests."""
        if "test-survey" in self.portal.objectIds():
            api.content.delete(obj=self.survey)

    def test_adapter_provides_interface(self):
        """Test that the adapter provides ITokenStore."""
        self.assertTrue(ITokenStore.providedBy(self.token_store))

    def test_adapter_is_per_survey(self):
        """Test that each survey has its own token store."""
        survey2 = api.content.create(
            container=self.portal,
            type="Survey",
            id="test-survey-2",
            title="Test Survey 2",
        )
        token_store2 = getAdapter(survey2, ITokenStore)
        
        # Generate tokens in first survey
        tokens1 = self.token_store.generate_tokens(2)
        
        # Second survey should have no tokens
        self.assertEqual(token_store2.list_tokens(), [])
        
        # Clean up
        api.content.delete(obj=survey2)

    def test_generate_tokens_returns_list(self):
        """Test that generate_tokens returns a list of strings."""
        tokens = self.token_store.generate_tokens(3)
        self.assertIsInstance(tokens, list)
        self.assertEqual(len(tokens), 3)
        for token in tokens:
            self.assertIsInstance(token, str)
            # Should be a valid UUID4 format
            self.assertEqual(len(token), 36)  # UUID4 string length
            self.assertEqual(token.count("-"), 4)  # UUID4 has 4 dashes

    def test_generate_tokens_unique(self):
        """Test that generated tokens are unique."""
        tokens = self.token_store.generate_tokens(10)
        self.assertEqual(len(set(tokens)), 10)  # All unique

    def test_has_token_existing(self):
        """Test has_token returns True for valid unused tokens."""
        tokens = self.token_store.generate_tokens(1)
        self.assertTrue(self.token_store.has_token(tokens[0]))

    def test_has_token_nonexistent(self):
        """Test has_token returns False for non-existent tokens."""
        self.assertFalse(self.token_store.has_token("non-existent-token"))

    def test_has_token_used(self):
        """Test has_token returns False for used tokens."""
        tokens = self.token_store.generate_tokens(1)
        self.token_store.invalidate(tokens[0])
        self.assertFalse(self.token_store.has_token(tokens[0]))

    def test_invalidate_existing_token(self):
        """Test invalidating an existing token."""
        tokens = self.token_store.generate_tokens(1)
        result = self.token_store.invalidate(tokens[0])
        self.assertTrue(result)
        self.assertFalse(self.token_store.has_token(tokens[0]))

    def test_invalidate_nonexistent_token(self):
        """Test invalidating a non-existent token returns False."""
        result = self.token_store.invalidate("non-existent-token")
        self.assertFalse(result)

    def test_invalidate_sets_used_timestamp(self):
        """Test that invalidating sets the used timestamp."""
        tokens = self.token_store.generate_tokens(1)
        info_before = self.token_store.get_token_info(tokens[0])
        self.assertIsNone(info_before["used"])
        
        self.token_store.invalidate(tokens[0])
        info_after = self.token_store.get_token_info(tokens[0])
        self.assertIsNotNone(info_after["used"])

    def test_get_token_info_existing(self):
        """Test getting info for an existing token."""
        tokens = self.token_store.generate_tokens(1)
        info = self.token_store.get_token_info(tokens[0])
        
        self.assertIsNotNone(info)
        self.assertEqual(info["token"], tokens[0])
        self.assertIn("created", info)
        self.assertIn("used", info)
        self.assertIsNone(info["used"])

    def test_get_token_info_nonexistent(self):
        """Test getting info for a non-existent token."""
        info = self.token_store.get_token_info("non-existent-token")
        self.assertIsNone(info)

    def test_list_tokens_empty(self):
        """Test listing tokens when none exist."""
        tokens = self.token_store.list_tokens()
        self.assertEqual(tokens, [])

    def test_list_tokens_with_data(self):
        """Test listing tokens with some generated."""
        self.token_store.generate_tokens(3)
        tokens = self.token_store.list_tokens()
        self.assertEqual(len(tokens), 3)
        for info in tokens:
            self.assertIn("token", info)
            self.assertIn("created", info)
            self.assertIn("used", info)

    def test_clear_removes_all_tokens(self):
        """Test that clear removes all tokens."""
        self.token_store.generate_tokens(5)
        self.assertEqual(len(self.token_store.list_tokens()), 5)
        
        self.token_store.clear()
        self.assertEqual(len(self.token_store.list_tokens()), 0)

    def test_token_storage_uses_annotation(self):
        """Test that tokens are stored using annotations."""
        from BTrees.OOBTree import OOBTree
        from zope.annotation.interfaces import IAnnotations
        
        annotations = IAnnotations(self.survey)
        self.assertNotIn(TOKEN_STORE_KEY, annotations)
        
        self.token_store.generate_tokens(1)
        self.assertIn(TOKEN_STORE_KEY, annotations)
        
        storage = annotations[TOKEN_STORE_KEY]
        self.assertIsInstance(storage, OOBTree)

    def test_multiple_generate_calls(self):
        """Test that multiple generate calls accumulate tokens."""
        tokens1 = self.token_store.generate_tokens(3)
        tokens2 = self.token_store.generate_tokens(2)
        
        all_tokens = self.token_store.list_tokens()
        self.assertEqual(len(all_tokens), 5)
        
        # Verify all tokens are tracked
        for token in tokens1 + tokens2:
            self.assertTrue(self.token_store.has_token(token))


if __name__ == "__main__":
    unittest.main()
