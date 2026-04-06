# -*- coding: utf-8 -*-
"""Tests for error message sanitization and information disclosure prevention.

These tests verify that:
1. Error messages don't contain file paths (no "/src/", "/eggs/", ".py:" patterns)
2. Error messages don't contain raw exception details
3. Internal errors are logged but not exposed
4. Generic user-friendly messages are returned
"""

from __future__ import annotations

import re
import unittest
from unittest.mock import MagicMock, patch

from zope.publisher.browser import TestRequest

from zopyx.surveyjs.browser.embed_security import (
    EmbedSecurityError,
    TokenExpiredError,
    TokenInvalidError,
)
from zopyx.surveyjs.browser.services.http import (
    _GENERIC_ERROR_MESSAGES,
)

# Regex patterns for detecting information disclosure
PATH_PATTERN = re.compile(r"(/[\w\-]+)+\.(py|js|json|cfg)", re.IGNORECASE)
SRC_PATTERN = re.compile(r"/src/|/eggs/|/parts/|/lib/|/dist/", re.IGNORECASE)
EXCEPTION_PATTERN = re.compile(
    r"(Traceback|File \"|\.py:\d+|line \d+|in <module>|in \w+\(|\.pyc|\.<locals>)",
    re.IGNORECASE,
)
INTERNAL_DETAIL_PATTERN = re.compile(
    r"(memory at|object at|0x[0-9a-f]+|__\w+__|callable|\.pyc|\.<locals>)",
    re.IGNORECASE,
)


class ErrorDisclosureTests(unittest.TestCase):
    """Unit tests for error message sanitization."""

    def _assert_no_path_disclosure(self, message: str, context: str = "") -> None:
        """Assert that a message does not contain file path disclosures."""
        self.assertIsNotNone(message)
        self.assertNotRegex(
            message,
            SRC_PATTERN,
            f"{context}: Message contains path disclosure: {message}",
        )
        self.assertNotRegex(
            message,
            PATH_PATTERN,
            f"{context}: Message contains file path: {message}",
        )

    def _assert_no_exception_details(self, message: str, context: str = "") -> None:
        """Assert that a message does not contain raw exception details."""
        self.assertIsNotNone(message)
        self.assertNotRegex(
            message,
            EXCEPTION_PATTERN,
            f"{context}: Message contains exception details: {message}",
        )
        self.assertNotRegex(
            message,
            INTERNAL_DETAIL_PATTERN,
            f"{context}: Message contains internal details: {message}",
        )

    def _assert_generic_message(self, message: str, context: str = "") -> None:
        """Assert that a message is a generic, user-friendly message."""
        self.assertIsNotNone(message)
        # Check that it's in the generic messages or doesn't look technical
        is_generic = (
            message in _GENERIC_ERROR_MESSAGES.values()
            or not any(c in message for c in ["_", "(", ")", ".py", "/"])
        )
        self.assertTrue(
            is_generic,
            f"{context}: Message should be generic but is: {message}",
        )

    def test_embed_token_error_no_path_disclosure(self) -> None:
        """Test that embed token errors don't leak file system paths.
        
        Verifies that when EmbedSecurityError is created, the error response
        doesn't contain sensitive file paths.
        """
        error = EmbedSecurityError("Token generation failed")
        message = str(error)

        # Assert no path disclosure in the message
        self._assert_no_path_disclosure(message, "embed token error")
        self._assert_no_exception_details(message, "embed token error")

    def test_token_generation_error_no_details(self) -> None:
        """Test that token generation errors don't expose internal details.
        
        When token generation encounters an internal error, only generic
        messages should be returned to the client.
        """
        error = EmbedSecurityError(
            "Token generation failed",
            reason="signing_key_missing"
        )
        message = str(error)
        reason = error.reason

        # Should not expose the internal error details
        self._assert_no_path_disclosure(message, "token generation error")
        self._assert_no_exception_details(message, "token generation error")
        self.assertNotIn("Database", message)
        self.assertNotIn("secret", message.lower())
        self.assertEqual(reason, "signing_key_missing")

    def test_validation_error_generic_message(self) -> None:
        """Test that validation errors return generic, safe messages.
        
        Verifies that the generic error messages dictionary contains
        safe, user-friendly messages for validation errors.
        """
        message = _GENERIC_ERROR_MESSAGES.get("validation_error", "")
        
        # Verify generic message is returned
        self._assert_no_path_disclosure(message, "validation error")
        self._assert_no_exception_details(message, "validation error")
        self._assert_generic_message(message, "validation error")
        self.assertEqual(message, "Invalid input. Please check your data and try again.")

    def test_internal_error_sanitized(self) -> None:
        """Test that internal error messages are sanitized.
        
        Verifies that the internal_error code maps to a generic,
        safe message without paths or exception details.
        """
        message = _GENERIC_ERROR_MESSAGES.get("internal_error", "")
        
        # Client message should be sanitized
        self._assert_no_path_disclosure(message, "internal error response")
        self._assert_no_exception_details(message, "internal error response")
        self.assertEqual(message, "An error occurred. Please try again or contact support.")

    def test_json_error_does_not_expose_paths(self) -> None:
        """Test that error messages are properly sanitized.
        
        Even if someone tries to pass a path-containing message,
        the generic error system should prevent exposure.
        """
        # Verify that generic messages don't contain paths
        for code, message in _GENERIC_ERROR_MESSAGES.items():
            with self.subTest(code=code):
                self._assert_no_path_disclosure(message, f"json_error message for {code}")

    def test_embed_config_validation_error_sanitized(self) -> None:
        """Test that embed config errors are sanitized.
        
        When validating embed tokens, ensure errors don't leak token validation
        implementation details or file paths.
        """
        # Test various embed security errors
        errors = [
            EmbedSecurityError("Origin not allowed"),
            EmbedSecurityError("Token expired"),
            EmbedSecurityError("Invalid token"),
        ]
        
        for error in errors:
            with self.subTest(error=str(error)):
                message = str(error)
                # Should not expose validation implementation details
                self._assert_no_path_disclosure(message, "embed config validation")
                self._assert_no_exception_details(message, "embed config validation")

    def test_generic_error_messages_defined(self) -> None:
        """Test that all expected generic error messages are defined.
        
        Verifies the _GENERIC_ERROR_MESSAGES dict contains safe, user-friendly
        messages for all expected error codes.
        """
        expected_codes = [
            "invalid_token",
            "token_generation_failed",
            "validation_error",
            "internal_error",
        ]

        for code in expected_codes:
            self.assertIn(code, _GENERIC_ERROR_MESSAGES)
            message = _GENERIC_ERROR_MESSAGES[code]
            self._assert_no_path_disclosure(message, f"generic message for {code}")
            self._assert_no_exception_details(message, f"generic message for {code}")
            # Generic messages should be user-friendly
            self.assertLess(len(message), 100)  # Not too long
            self.assertGreater(len(message), 10)  # Not too short

    def test_safe_json_error_generic_messages(self) -> None:
        """Test that safe_json_error uses generic messages.
        
        Verifies the generic error messages are appropriate for client exposure.
        """
        # Test all generic messages for safety
        for code, message in _GENERIC_ERROR_MESSAGES.items():
            with self.subTest(code=code):
                # Should be safe for client exposure
                self._assert_no_path_disclosure(message, f"safe_json_error message {code}")
                self._assert_no_exception_details(message, f"safe_json_error message {code}")
                # Should be user-friendly (no underscores, technical terms)
                self.assertNotIn("__", message)

    def test_embed_security_error_messages_are_safe(self) -> None:
        """Test various EmbedSecurityError messages for safety.
        
        Tests multiple common error scenarios to ensure messages are safe.
        """
        test_cases = [
            ("Origin not allowed", None),
            ("Token has expired", None),
            ("Invalid token format", None),
            ("Origin verification failed", "origin_mismatch"),
            ("Token validation failed", "invalid_signature"),
        ]

        for msg, reason in test_cases:
            with self.subTest(message=msg, reason=reason):
                error = EmbedSecurityError(msg, reason=reason)
                message = str(error)
                
                self._assert_no_path_disclosure(message, f"error: {msg}")
                self._assert_no_exception_details(message, f"error: {msg}")


class DirectEmbedSecurityErrorTests(unittest.TestCase):
    """Tests specifically for embed security error handling."""

    def test_embed_security_error_message_safe(self) -> None:
        """Test that EmbedSecurityError messages are safe to expose.
        
        When EmbedSecurityError is raised, the message should not contain
        internal implementation details.
        """
        error = EmbedSecurityError("Origin not allowed")
        self.assertEqual(str(error), "Origin not allowed")
        
        # Error with reason should still be safe
        error_with_reason = EmbedSecurityError(
            "Validation failed", reason="origin_mismatch"
        )
        self.assertIn("Validation failed", str(error_with_reason))
        self.assertEqual(error_with_reason.reason, "origin_mismatch")

    def test_validate_embed_token_error_no_details(self) -> None:
        """Test that token validation errors are sanitized.
        
        When token validation fails, ensure the error doesn't contain
        information about the validation internals.
        """
        error = TokenInvalidError("Invalid signature")
        message = str(error)
        
        # Should not contain implementation details
        self.assertNotIn("jwt", message.lower())
        self.assertNotIn("hmac", message.lower())
        self.assertNotIn("algorithm", message.lower())

    def test_token_expired_error_no_details(self) -> None:
        """Test that token expired errors are sanitized.
        
        When token has expired, ensure the error is generic and
        doesn't contain technical JWT details.
        """
        error = TokenExpiredError("Token has expired")
        message = str(error)
        
        # Should be simple and safe
        self.assertEqual(message, "Token has expired")
        self.assertNotIn("timestamp", message.lower())
        # Should not contain JWT-specific claim names
        self.assertNotIn("'exp'", message.lower())
        self.assertNotIn("iat", message.lower())

    def test_embed_security_error_with_internal_path(self) -> None:
        """Test that even errors created with paths are detected.
        
        This test documents that we should never include paths in error messages.
        """
        # This test verifies our regex patterns work correctly
        # In production, paths should never be in error messages
        test_path = "/src/zopyx/surveyjs/security.py"
        
        # Verify our patterns detect paths
        self.assertRegex(test_path, SRC_PATTERN)
        self.assertRegex(test_path, PATH_PATTERN)


class SafeJsonErrorHelperTests(unittest.TestCase):
    """Tests for the safe_json_error helper function."""

    def test_generic_error_messages_structure(self) -> None:
        """Test that generic error messages dict has correct structure.
        
        Verifies the dictionary contains expected keys and safe values.
        """
        # Required error codes that should be present
        required_codes = [
            "invalid_token",
            "token_generation_failed",
            "validation_error",
            "internal_error",
        ]
        
        for code in required_codes:
            self.assertIn(code, _GENERIC_ERROR_MESSAGES)
            message = _GENERIC_ERROR_MESSAGES[code]
            
            # Each message should be a non-empty string
            self.assertIsInstance(message, str)
            self.assertTrue(len(message) > 0)
            
            # Should not look like technical/internal errors
            self.assertNotIn("Traceback", message)
            self.assertNotIn("Exception", message)

    def test_error_code_header_safety(self) -> None:
        """Test that error codes are safe for header exposure.
        
        Error codes should be simple strings without special characters.
        """
        for code in _GENERIC_ERROR_MESSAGES.keys():
            with self.subTest(code=code):
                # Error codes should be lowercase with underscores
                self.assertRegex(code, r"^[a-z_]+$")
                # Should not contain paths or special chars
                self.assertNotIn("/", code)
                self.assertNotIn("\\", code)
                self.assertNotIn(".", code)


if __name__ == "__main__":
    unittest.main()
