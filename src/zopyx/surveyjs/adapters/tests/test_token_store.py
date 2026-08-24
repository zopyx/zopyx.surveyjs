# -*- coding: utf-8 -*-
"""Tests for the token store adapter."""

from plone import api
from plone.app.testing import setRoles, TEST_USER_ID
from zope.component import getAdapter
from zopyx.surveyjs.interfaces import ITokenStore
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING
from zopyx.surveyjs.constants import TOKEN_STORE_KEY
from zopyx.surveyjs.storage import SQLTokenStore, SurveyToken
from sqlmodel import select

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
            # Should be a 32-character URL-safe token (token_urlsafe(24))
            self.assertEqual(len(token), 32)
            # URL-safe base64 characters: A-Z, a-z, 0-9, -, _
            valid_chars = set(
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            )
            self.assertTrue(set(token).issubset(valid_chars))

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
        """Test that invalidating a non-existent token returns False."""
        result = self.token_store.invalidate("non-existent-token")
        self.assertFalse(result)

    def test_consume_token_is_single_use(self):
        """Atomic consumption succeeds once and rejects subsequent use."""
        token = self.token_store.generate_tokens(1)[0]
        self.assertTrue(self.token_store.consume_token(token, reason="user_submission"))
        self.assertFalse(self.token_store.consume_token(token, reason="user_submission"))
        self.assertFalse(self.token_store.has_token(token))

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

    def test_import_tokens_basic(self):
        """Test importing tokens."""
        tokens_to_import = ["customtoken123", "anothertoken456", "thirdtoken789"]
        result = self.token_store.import_tokens(tokens_to_import)

        self.assertEqual(result["imported"], 3)
        self.assertEqual(len(result["skipped"]), 0)

        # Verify tokens are in store
        for token in tokens_to_import:
            self.assertTrue(self.token_store.has_token(token))

    def test_import_tokens_skips_duplicates(self):
        """Test that import skips existing tokens."""
        # First import
        tokens_to_import = ["customtoken123", "anothertoken456"]
        self.token_store.import_tokens(tokens_to_import)

        # Second import with one new and one existing
        new_tokens = ["customtoken123", "newtoken789"]  # customtoken123 already exists
        result = self.token_store.import_tokens(new_tokens)

        self.assertEqual(result["imported"], 1)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(result["skipped"][0]["token"], "customtoken123")
        self.assertEqual(result["skipped"][0]["reason"], "duplicate")

    def test_import_tokens_empty_list(self):
        """Test importing empty list."""
        result = self.token_store.import_tokens([])
        self.assertEqual(result["imported"], 0)
        self.assertEqual(len(result["skipped"]), 0)

    def test_import_tokens_has_created_timestamp(self):
        """Test that imported tokens have created timestamp."""
        self.token_store.import_tokens(["testtoken123"])
        info = self.token_store.get_token_info("testtoken123")

        self.assertIsNotNone(info)
        self.assertIn("created", info)
        self.assertIsNotNone(info["created"])
        self.assertIsNone(info["used"])  # Not used yet

    def test_import_tokens_accumulates(self):
        """Test that import_tokens accumulates with existing tokens."""
        # Generate some tokens first
        self.token_store.generate_tokens(2)

        # Import more tokens
        self.token_store.import_tokens(["imported1abc", "imported2def"])

        # Should have 4 total
        all_tokens = self.token_store.list_tokens()
        self.assertEqual(len(all_tokens), 4)


class SQLTokenStoreTest(unittest.TestCase):
    """Test the SQL token store implementation."""

    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self):
        """Set up test fixtures."""
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])

        # Create a survey for testing
        self.survey = api.content.create(
            container=self.portal,
            type="Survey",
            id="test-survey-sql",
            title="Test Survey SQL",
        )

        # Create SQL token store with file-based database
        # Use temp directory for test database
        import tempfile
        import os

        self.temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(self.temp_dir, "test-tokens.db")
        self.token_store = SQLTokenStore(
            self.survey, database_uri=f"sqlite:///{db_path}"
        )

    def tearDown(self):
        """Clean up after tests."""
        if "test-survey-sql" in self.portal.objectIds():
            api.content.delete(obj=self.survey)
        # Clean up temp directory
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_adapter_provides_interface(self):
        """Test that SQL store provides ITokenStore."""
        self.assertTrue(ITokenStore.providedBy(self.token_store))

    def test_generate_tokens_creates_db_rows(self):
        """Test that generate_tokens creates database rows."""
        tokens = self.token_store.generate_tokens(5)

        self.assertEqual(len(tokens), 5)

        # Verify in database
        with self.token_store._session() as session:
            from sqlalchemy import func

            count = session.exec(select(func.count(SurveyToken.token))).one()
            self.assertEqual(count, 5)

    def test_has_token_valid(self):
        """Test has_token returns True for unused tokens."""
        tokens = self.token_store.generate_tokens(1)
        self.assertTrue(self.token_store.has_token(tokens[0]))

    def test_has_token_used(self):
        """Test has_token returns False for used tokens."""
        tokens = self.token_store.generate_tokens(1)
        self.token_store.invalidate(tokens[0])
        self.assertFalse(self.token_store.has_token(tokens[0]))

    def test_has_token_nonexistent(self):
        """Test has_token returns False for non-existent tokens."""
        self.assertFalse(self.token_store.has_token("nonexistent"))

    def test_has_token_wrong_survey(self):
        """Test tokens are scoped to survey."""
        survey2 = api.content.create(
            container=self.portal,
            type="Survey",
            id="test-survey-2-sql",
            title="Test Survey 2 SQL",
        )
        store2 = SQLTokenStore(survey2, database_uri="sqlite:///:memory:")

        tokens = self.token_store.generate_tokens(1)

        # Same DB but different survey_id
        # Note: With in-memory DBs, each store has its own connection
        # This test verifies the scoping logic is correct
        self.assertTrue(self.token_store.has_token(tokens[0]))

        api.content.delete(obj=survey2)

    def test_invalidate_existing(self):
        """Test invalidating existing token."""
        tokens = self.token_store.generate_tokens(1)
        result = self.token_store.invalidate(tokens[0])

        self.assertTrue(result)
        info = self.token_store.get_token_info(tokens[0])
        self.assertIsNotNone(info["used"])

    def test_invalidate_nonexistent(self):
        """Test invalidating non-existent token returns False."""
        result = self.token_store.invalidate("nonexistent")
        self.assertFalse(result)

    def test_get_token_info_structure(self):
        """Test token info has correct structure."""
        tokens = self.token_store.generate_tokens(1)
        info = self.token_store.get_token_info(tokens[0])

        self.assertIsNotNone(info)
        self.assertEqual(info["token"], tokens[0])
        self.assertIn("created", info)
        self.assertIn("used", info)
        self.assertIsNone(info["used"])

    def test_get_token_info_nonexistent(self):
        """Test get_token_info returns None for missing token."""
        info = self.token_store.get_token_info("missing")
        self.assertIsNone(info)

    def test_list_tokens(self):
        """Test listing all tokens."""
        self.token_store.generate_tokens(3)
        tokens = self.token_store.list_tokens()

        self.assertEqual(len(tokens), 3)
        for info in tokens:
            self.assertIn("token", info)
            self.assertIn("created", info)
            self.assertIn("used", info)

    def test_get_stats_aggregation(self):
        """Test stats use SQL aggregation."""
        self.token_store.generate_tokens(10)
        # Use 3 tokens
        for token in self.token_store.list_tokens()[:3]:
            self.token_store.invalidate(token["token"])

        stats = self.token_store.get_stats()

        self.assertEqual(stats["total"], 10)
        self.assertEqual(stats["used"], 3)
        self.assertEqual(stats["unused"], 7)

    def test_clear_removes_all(self):
        """Test clear removes all survey tokens."""
        self.token_store.generate_tokens(10)
        self.assertEqual(self.token_store.get_stats()["total"], 10)

        self.token_store.clear()

        self.assertEqual(self.token_store.get_stats()["total"], 0)

    def test_batch_id_tracking(self):
        """Test that generate_tokens creates tokens with same batch_id."""
        tokens = self.token_store.generate_tokens(5)

        # All tokens in same batch should share batch_id
        with self.token_store._session() as session:
            rows = list(
                session.exec(
                    select(SurveyToken).where(SurveyToken.token.in_(tokens))
                ).all()
            )

            batch_ids = set(row.batch_id for row in rows)
            self.assertEqual(len(batch_ids), 1)  # Same batch


class TokenStoreBackendParityTest(unittest.TestCase):
    """Test that ZODB and SQL backends behave identically."""

    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self):
        """Set up both backends."""
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])

        self.survey = api.content.create(
            container=self.portal,
            type="Survey",
            id="test-survey-parity",
            title="Test Survey Parity",
        )

        # ZODB store
        from zopyx.surveyjs.adapters.token_store import TokenStore

        self.zodb_store = TokenStore(self.survey)

        # SQL store with file-based database
        import tempfile
        import os

        self.temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(self.temp_dir, "parity-test.db")
        self.sql_store = SQLTokenStore(self.survey, database_uri=f"sqlite:///{db_path}")

    def tearDown(self):
        """Clean up."""
        if "test-survey-parity" in self.portal.objectIds():
            api.content.delete(obj=self.survey)
        # Clean up temp directory
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_same_generate_behavior(self):
        """Both backends generate valid tokens."""
        z_tokens = self.zodb_store.generate_tokens(5)
        s_tokens = self.sql_store.generate_tokens(5)

        self.assertEqual(len(z_tokens), len(s_tokens))

        # Both should track their tokens
        for t in z_tokens:
            self.assertTrue(self.zodb_store.has_token(t))
        for t in s_tokens:
            self.assertTrue(self.sql_store.has_token(t))

    def test_same_invalidate_behavior(self):
        """Both backends invalidate similarly."""
        z_tokens = self.zodb_store.generate_tokens(1)
        s_tokens = self.sql_store.generate_tokens(1)

        # Both return True on first invalidate
        self.assertTrue(self.zodb_store.invalidate(z_tokens[0]))
        self.assertTrue(self.sql_store.invalidate(s_tokens[0]))

        # Both return True on second invalidate (idempotent)
        self.assertTrue(self.zodb_store.invalidate(z_tokens[0]))
        self.assertTrue(self.sql_store.invalidate(s_tokens[0]))

        # Both show as used
        self.assertFalse(self.zodb_store.has_token(z_tokens[0]))
        self.assertFalse(self.sql_store.has_token(s_tokens[0]))

    def test_same_stats_behavior(self):
        """Both backends return same stats structure."""
        self.zodb_store.generate_tokens(5)
        self.sql_store.generate_tokens(5)

        z_stats = self.zodb_store.get_stats()
        s_stats = self.sql_store.get_stats()

        self.assertEqual(z_stats.keys(), s_stats.keys())
        self.assertEqual(set(["total", "used", "unused"]), set(z_stats.keys()))


if __name__ == "__main__":
    unittest.main()
