# -*- coding: utf-8 -*-
"""Tests for the token store browser view."""

from plone import api
from plone.app.testing import setRoles, TEST_USER_ID
from zope.component import getAdapter
from zopyx.surveyjs.interfaces import ITokenStore
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING

import io
import unittest


class TokenStoreViewTest(unittest.TestCase):
    """Test the token store browser view."""

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

        # Get the view
        self.request = self.layer["request"]
        self.view = api.content.get_view(
            name="token-store",
            context=self.survey,
            request=self.request,
        )

    def tearDown(self):
        """Clean up after tests."""
        if "test-survey" in self.portal.objectIds():
            api.content.delete(obj=self.survey)

    def test_view_exists(self):
        """Test that the view exists and is accessible."""
        self.assertIsNotNone(self.view)
        # The view class name may be wrapped by Five when template is used
        self.assertIn("TokenStoreView", str(self.view.__class__.__mro__))
        # Check the view has the expected attributes
        self.assertTrue(hasattr(self.view, "get_stats"))
        self.assertTrue(hasattr(self.view, "download_valid_tokens"))
        self.assertTrue(hasattr(self.view, "download_all_tokens"))

    def test_get_stats_empty(self):
        """Test stats with no tokens."""
        stats = self.view.get_stats()
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["used"], 0)
        self.assertEqual(stats["unused"], 0)

    def test_get_stats_with_tokens(self):
        """Test stats with tokens."""
        # Generate some tokens
        self.token_store.generate_tokens(5)

        stats = self.view.get_stats()
        self.assertEqual(stats["total"], 5)
        self.assertEqual(stats["used"], 0)
        self.assertEqual(stats["unused"], 5)

        # Use one token
        tokens = self.token_store.list_tokens()
        self.token_store.invalidate(tokens[0]["token"])

        stats = self.view.get_stats()
        self.assertEqual(stats["total"], 5)
        self.assertEqual(stats["used"], 1)
        self.assertEqual(stats["unused"], 4)

    def test_get_survey_url(self):
        """Test getting survey URL."""
        url = self.view.get_survey_url()
        self.assertEqual(url, self.survey.absolute_url())

    def test_download_valid_tokens_only_unused(self):
        """Test CSV download only includes unused (valid) tokens."""
        # Generate tokens
        tokens = self.token_store.generate_tokens(5)

        # Use 2 tokens
        self.token_store.invalidate(tokens[0])
        self.token_store.invalidate(tokens[1])

        # Get CSV content
        csv_content = self.view.download_valid_tokens()

        # Check CSV structure (handle Windows line endings)
        lines = csv_content.strip().replace("\r\n", "\n").split("\n")
        # Header + 3 unused tokens (5 generated - 2 used = 3)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], "token,url")

        # Verify used tokens are NOT in CSV
        for line in lines[1:]:
            parts = line.split(",")
            self.assertEqual(len(parts), 2)
            token, url = parts
            self.assertNotIn(token, [tokens[0], tokens[1]])
            self.assertTrue(url.startswith(self.survey.absolute_url()))
            self.assertIn("?tt=", url)
            self.assertIn(token, url)

    def test_download_all_tokens(self):
        """Test CSV download includes all tokens with metadata."""
        # Generate tokens
        tokens = self.token_store.generate_tokens(5)

        # Use 2 tokens
        self.token_store.invalidate(tokens[0])
        self.token_store.invalidate(tokens[1])

        # Get CSV content
        csv_content = self.view.download_all_tokens()

        # Check CSV structure (handle Windows line endings)
        lines = csv_content.strip().replace("\r\n", "\n").split("\n")
        # Header + all 5 tokens
        self.assertEqual(len(lines), 6)
        self.assertEqual(lines[0], "token,url,created,used,status")

        # Verify all tokens are in CSV
        token_values_in_csv = []
        for line in lines[1:]:
            parts = line.split(",")
            self.assertEqual(len(parts), 5)
            token, url, created, used, status = parts
            token_values_in_csv.append(token)
            self.assertTrue(url.startswith(self.survey.absolute_url()))
            self.assertIn("?tt=", url)
            self.assertIn(token, url)
            self.assertIn(status, ["used", "unused"])

        # All tokens should be present
        for token in tokens:
            self.assertIn(token, token_values_in_csv)

    def test_import_csv_valid_tokens(self):
        """Test importing valid tokens from CSV."""
        # Create CSV content
        csv_content = "token\ntoken12345\ntoken67890\ntoken11111"

        # Create file upload mock
        class MockFileUpload:
            def __init__(self, content, filename="test.csv", content_type="text/csv"):
                self.file = io.BytesIO(content.encode("utf-8"))
                self.filename = filename
                self.contentType = content_type

            def read(self):
                return self.file.read()

        csv_file = MockFileUpload(csv_content)
        self.request.form["csv_file"] = csv_file
        self.request.form["import_csv"] = "Import"

        # Call the view - should redirect on success
        self.view()

        # Check tokens were imported
        tokens = self.token_store.list_tokens()
        self.assertEqual(len(tokens), 3)

        # Verify token values
        token_values = [t["token"] for t in tokens]
        self.assertIn("token12345", token_values)
        self.assertIn("token67890", token_values)
        self.assertIn("token11111", token_values)

    def test_import_csv_missing_column(self):
        """Test importing CSV without token column."""
        # Create CSV content without token column
        csv_content = "id,name\n1,test"

        class MockFileUpload:
            def __init__(self, content, filename="test.csv", content_type="text/csv"):
                self.file = io.BytesIO(content.encode("utf-8"))
                self.filename = filename
                self.contentType = content_type

            def read(self):
                return self.file.read()

        csv_file = MockFileUpload(csv_content)
        self.request.form["csv_file"] = csv_file
        self.request.form["import_csv"] = "Import"

        # Call the view - should redirect with error
        self.view()

        # No tokens should be imported
        tokens = self.token_store.list_tokens()
        self.assertEqual(len(tokens), 0)

    def test_import_csv_token_too_short(self):
        """Test importing CSV with tokens that are too short."""
        # Create CSV content with short tokens
        csv_content = "token\nshort\nab\nvalidtoken123"

        class MockFileUpload:
            def __init__(self, content, filename="test.csv", content_type="text/csv"):
                self.file = io.BytesIO(content.encode("utf-8"))
                self.filename = filename
                self.contentType = content_type

            def read(self):
                return self.file.read()

        csv_file = MockFileUpload(csv_content)
        self.request.form["csv_file"] = csv_file
        self.request.form["import_csv"] = "Import"

        # Call the view - should redirect with error
        self.view()

        # No tokens should be imported due to validation errors
        tokens = self.token_store.list_tokens()
        self.assertEqual(len(tokens), 0)

    def test_import_csv_duplicate_tokens(self):
        """Test importing CSV with duplicate tokens (skip existing)."""
        # First, generate a token
        self.token_store.generate_tokens(1)
        existing_token = self.token_store.list_tokens()[0]["token"]

        # Create CSV with the existing token and a new one
        csv_content = f"token\n{existing_token}\nnewtoken123"

        class MockFileUpload:
            def __init__(self, content, filename="test.csv", content_type="text/csv"):
                self.file = io.BytesIO(content.encode("utf-8"))
                self.filename = filename
                self.contentType = content_type

            def read(self):
                return self.file.read()

        csv_file = MockFileUpload(csv_content)
        self.request.form["csv_file"] = csv_file
        self.request.form["import_csv"] = "Import"

        # Call the view - should redirect
        self.view()

        # Should have 2 tokens total (1 original + 1 new)
        tokens = self.token_store.list_tokens()
        self.assertEqual(len(tokens), 2)


if __name__ == "__main__":
    unittest.main()
