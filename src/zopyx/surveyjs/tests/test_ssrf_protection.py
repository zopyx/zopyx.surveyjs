# -*- coding: utf-8 -*-
"""Unit tests for SSRF protection in POST action URL validation.

This module tests the _validate_post_url function and its integration with
post_submission_payload to ensure SSRF attacks are prevented while allowing
legitimate external webhook URLs.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from BTrees.OOBTree import OOBTree
from plone import api
from plone.app.testing import TEST_USER_ID, setRoles
from plone.registry.interfaces import IRegistry
from zope.annotation.interfaces import IAnnotations
from zope.component import getUtility

from zopyx.surveyjs import subscribers
from zopyx.surveyjs.constants import FORM_VERSIONS_KEY
from zopyx.surveyjs.interfaces import IFormsSettings
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING


class DummyEvent:
    """Dummy event for testing subscribers."""

    def __init__(self, form_data: dict) -> None:
        self.form_data = form_data


class TestValidatePostUrl(unittest.TestCase):
    """Unit tests for _validate_post_url function with allowlist support."""

    def test_allowlist_blocks_by_default(self):
        """Empty allowlist should block all URLs."""
        # Empty allowlist means POST action is disabled
        allowlist = []

        # Use non-localhost URLs to test empty allowlist blocking
        urls_to_test = [
            "https://api.example.com/webhook",
            "https://hooks.zapier.com/hooks/catch/123/abc",
        ]

        for url in urls_to_test:
            is_valid, error = subscribers._validate_post_url(url, allowlist)
            self.assertFalse(is_valid, f"Should block URL with empty allowlist: {url}")
            # Empty allowlist returns "disabled" message
            self.assertIn("disabled", error.lower())

    def test_allowlist_star_allows_all(self):
        """Single '*' in allowlist allows any URL (not recommended for production)."""
        allowlist = ["*"]

        urls_to_test = [
            "https://api.example.com/webhook",
            "http://hooks.zapier.com/hooks/catch/123/abc",
            "https://myapp.herokuapp.com/survey-callback",
        ]

        for url in urls_to_test:
            is_valid, error = subscribers._validate_post_url(url, allowlist)
            self.assertTrue(is_valid, f"Should allow URL with '*' allowlist: {url}")
            self.assertEqual(error, "")

    def test_allowlist_exact_match(self):
        """Exact URL matches pattern."""
        allowlist = [
            "https://api.example.com/webhook",
            "https://hooks.zapier.com/hooks/catch/123/abc",
        ]

        # Should match exact URLs
        is_valid, error = subscribers._validate_post_url(
            "https://api.example.com/webhook", allowlist
        )
        self.assertTrue(is_valid)
        self.assertEqual(error, "")

        is_valid, error = subscribers._validate_post_url(
            "https://hooks.zapier.com/hooks/catch/123/abc", allowlist
        )
        self.assertTrue(is_valid)
        self.assertEqual(error, "")

        # Should not match different URLs
        is_valid, error = subscribers._validate_post_url(
            "https://api.example.com/other", allowlist
        )
        self.assertFalse(is_valid)
        self.assertIn("not in allowlist", error.lower())

        is_valid, error = subscribers._validate_post_url(
            "https://evil.com/webhook", allowlist
        )
        self.assertFalse(is_valid)
        self.assertIn("not in allowlist", error.lower())

    def test_allowlist_wildcard_match(self):
        """URL matches wildcard pattern like https://api.example.com/*."""
        allowlist = [
            "https://api.example.com/*",
            "https://*.webhook.site/*",
            "https://hooks.zapier.com/hooks/catch/*",
        ]

        # Should match wildcard patterns
        is_valid, error = subscribers._validate_post_url(
            "https://api.example.com/webhook", allowlist
        )
        self.assertTrue(is_valid, "Should match https://api.example.com/*")
        self.assertEqual(error, "")

        is_valid, error = subscribers._validate_post_url(
            "https://api.example.com/v1/users/create", allowlist
        )
        self.assertTrue(is_valid, "Should match https://api.example.com/*")
        self.assertEqual(error, "")

        is_valid, error = subscribers._validate_post_url(
            "https://myapp.webhook.site/unique-token", allowlist
        )
        self.assertTrue(is_valid, "Should match https://*.webhook.site/*")
        self.assertEqual(error, "")

        is_valid, error = subscribers._validate_post_url(
            "https://hooks.zapier.com/hooks/catch/123/abc", allowlist
        )
        self.assertTrue(is_valid, "Should match https://hooks.zapier.com/hooks/catch/*")
        self.assertEqual(error, "")

        # Should not match URLs outside the pattern
        is_valid, error = subscribers._validate_post_url(
            "https://api.other.com/webhook", allowlist
        )
        self.assertFalse(is_valid)
        self.assertIn("not in allowlist", error.lower())

        is_valid, error = subscribers._validate_post_url(
            "https://api.example.com", allowlist
        )
        self.assertFalse(is_valid)
        self.assertIn("not in allowlist", error.lower())

    def test_allowlist_block_dangerous_hosts(self):
        """Blocks localhost, 169.254.169.254 even if in allowlist."""
        # These should be blocked even if explicitly in allowlist
        allowlist = [
            "http://localhost:8080/*",
            "http://127.0.0.1/*",
            "http://169.254.169.254/*",
        ]

        blocked_urls = [
            ("http://localhost:8080/webhook", "localhost"),
            ("http://127.0.0.1:8080/admin", "127.0.0.1"),
            ("http://169.254.169.254/latest/meta-data/", "169.254.169.254"),
            ("http://[::1]/api", "::1"),
            ("http://0.0.0.0/server", "0.0.0.0"),
            ("http://metadata.google.internal/computeMetadata/v1/", "metadata.google.internal"),
            ("http://100.100.100.200/latest/meta-data/", "100.100.100.200"),
        ]

        for url, blocked_host in blocked_urls:
            is_valid, error = subscribers._validate_post_url(url, allowlist)
            self.assertFalse(is_valid, f"Should block dangerous URL: {url}")
            self.assertIn("blocked", error.lower())
            self.assertIn(blocked_host, error.lower())

    def test_allowlist_no_match(self):
        """URL not matching any pattern is blocked."""
        allowlist = [
            "https://trusted-api.com/*",
            "https://hooks.zapier.com/*",
        ]

        # URLs that don't match any pattern
        non_matching_urls = [
            "https://evil.com/webhook",
            "https://api.trusted-api.com.evil.com/fake",
            "https://hooks.zapier.com.evil.com/fake",
            "http://untrusted.com/api",
            "https://unknown.com/hooks",
        ]

        for url in non_matching_urls:
            is_valid, error = subscribers._validate_post_url(url, allowlist)
            self.assertFalse(is_valid, f"Should block non-matching URL: {url}")
            self.assertIn("not in allowlist", error.lower())

    def test_blocks_private_ips(self):
        """Private IP ranges should be blocked regardless of allowlist."""
        allowlist = ["*"]  # Even with wildcard, private IPs should be blocked

        blocked_urls = [
            "http://10.0.0.1/internal",      # Private 10.x
            "http://192.168.1.1/config",     # Private 192.168.x
            "http://172.16.0.1/api",         # Private 172.16-31.x
            "http://172.31.255.255/api",     # Private 172.31.x
        ]

        for url in blocked_urls:
            is_valid, error = subscribers._validate_post_url(url, allowlist)
            self.assertFalse(is_valid, f"Should block private IP URL: {url}")
            self.assertIn("blocked", error.lower())

    def test_blocks_invalid_schemes(self):
        """Non-http/https schemes should be blocked."""
        allowlist = ["*"]

        invalid_urls = [
            "file:///etc/passwd",
            "ftp://internal.server/data",
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>",
        ]

        for url in invalid_urls:
            is_valid, error = subscribers._validate_post_url(url, allowlist)
            self.assertFalse(is_valid, f"Should block non-HTTP scheme: {url}")

    def test_empty_url(self):
        """Empty URL should be blocked."""
        allowlist = ["*"]
        is_valid, error = subscribers._validate_post_url("", allowlist)
        self.assertFalse(is_valid)
        self.assertIn("url is required", error.lower())


class TestPostSubmissionPayloadIntegration(unittest.TestCase):
    """Integration tests for post_submission_payload with SSRF protection."""

    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.survey = api.content.create(
            container=self.portal,
            type="Survey",
            id="survey-ssrf-test",
            title="Survey SSRF Test",
        )
        annos = IAnnotations(self.survey)
        annos[FORM_VERSIONS_KEY] = OOBTree()
        annos[FORM_VERSIONS_KEY]["v1"] = {
            "id": "v1",
            "created": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "form_json": {"pages": []},
        }

    def _set_allowlist(self, allowlist: list) -> None:
        """Helper to set the POST endpoint allowlist in registry."""
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        settings.post_endpoint_allowlist = allowlist

    def test_post_action_blocked_when_not_in_allowlist(self):
        """POST action should be blocked when URL is not in allowlist."""
        self.survey.actions = {"post"}
        self.survey.post_endpoint_url = "https://evil.com/webhook"

        # Set allowlist that doesn't include the URL
        self._set_allowlist(["https://trusted-api.com/*"])

        event = DummyEvent(
            {
                "poll_id": "poll-42",
                "created": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "result": {"q1": "yes"},
            }
        )

        with patch("zopyx.surveyjs.subscribers.httpx.post") as mock_post:
            subscribers.post_submission_payload(self.survey, event)
            # httpx.post should NOT be called
            mock_post.assert_not_called()

    def test_post_action_allowed_when_in_allowlist(self):
        """POST action should proceed when URL is in allowlist."""
        self.survey.actions = {"post"}
        self.survey.post_endpoint_url = "https://trusted-api.com/webhook"

        # Set allowlist that includes the URL
        self._set_allowlist(["https://trusted-api.com/*"])

        event = DummyEvent(
            {
                "poll_id": "poll-42",
                "created": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "result": {"q1": "yes"},
            }
        )

        response = MagicMock()
        response.raise_for_status.return_value = None
        response.status_code = 200

        with patch(
            "zopyx.surveyjs.subscribers.httpx.post", return_value=response
        ) as mock_post:
            subscribers.post_submission_payload(self.survey, event)
            # httpx.post SHOULD be called
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            self.assertEqual(call_args.args[0], "https://trusted-api.com/webhook")

    def test_post_action_blocked_for_localhost_even_in_allowlist(self):
        """POST action should be blocked for localhost even if in allowlist."""
        self.survey.actions = {"post"}
        self.survey.post_endpoint_url = "http://localhost:8080/webhook"

        # Even with localhost in allowlist, it should be blocked
        self._set_allowlist(["http://localhost:8080/*"])

        event = DummyEvent(
            {
                "poll_id": "poll-42",
                "created": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "result": {"q1": "yes"},
            }
        )

        with patch("zopyx.surveyjs.subscribers.httpx.post") as mock_post:
            subscribers.post_submission_payload(self.survey, event)
            # httpx.post should NOT be called
            mock_post.assert_not_called()

    def test_post_action_blocked_for_aws_metadata_even_in_allowlist(self):
        """POST action should be blocked for AWS metadata even if in allowlist."""
        self.survey.actions = {"post"}
        self.survey.post_endpoint_url = "http://169.254.169.254/latest/meta-data/"

        # Even with metadata IP in allowlist, it should be blocked
        self._set_allowlist(["http://169.254.169.254/*"])

        event = DummyEvent(
            {
                "poll_id": "poll-42",
                "created": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "result": {"q1": "yes"},
            }
        )

        with patch("zopyx.surveyjs.subscribers.httpx.post") as mock_post:
            subscribers.post_submission_payload(self.survey, event)
            # httpx.post should NOT be called
            mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
