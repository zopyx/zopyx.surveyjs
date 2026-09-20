from types import SimpleNamespace
import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import transaction

from zopyx.surveyjs.browser.services.auth import AuthService
from zopyx.surveyjs.kv import get_kv_store


class AuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.context = SimpleNamespace(
            access_mode="public",
            trusted_access_ttl_hours=2,
        )
        self.request = MagicMock()
        self.request.form = {}
        self.request.get.return_value = None
        self.service = AuthService(self.context, self.request, lambda: "form-1")
        self.settings = SimpleNamespace(
            authenticity_token_enabled=False,
            authenticity_token_secret="",
            authenticity_token_issuer="issuer",
            authenticity_token_audience="audience",
            authenticity_token_ttl_seconds=600,
            authenticity_token_cache_path="",
        )

    def test_trusted_mode_and_token_extraction(self):
        self.assertFalse(self.service.trusted_access_enabled())
        self.context.access_mode = "trusted"
        self.assertTrue(self.service.trusted_access_enabled())
        self.request.form = {"tt": "  token-1 "}
        self.assertEqual(self.service.trusted_access_token_from_request(), "token-1")
        self.request.form = {"access_token": "fallback"}
        self.assertEqual(self.service.trusted_access_token_from_request(), "fallback")

    def test_ttl_and_cache_helpers_are_safe(self):
        self.context.trusted_access_ttl_hours = "bad"
        self.assertEqual(self.service._trusted_access_ttl_seconds(), 168 * 3600)
        self.assertEqual(self.service._trusted_access_cache_key("x"), "trusted:x")
        cache = MagicMock()
        cache.add.return_value = True
        self.assertTrue(self.service._cache_add(cache, "x", "y"))
        cache.add.side_effect = RuntimeError
        self.assertFalse(self.service._cache_add(cache, "x", "y"))
        cache.set.side_effect = RuntimeError
        self.service._cache_set(cache, "x", "y")

    def test_token_cache_uses_kv_facade_factory(self):
        cache = MagicMock()
        with patch(
            "zopyx.surveyjs.browser.services.auth.get_configured_kv_store",
            return_value=cache,
        ) as factory:
            self.assertIs(self.service._token_cache(self.settings), cache)
        factory.assert_called_once_with(
            self.settings,
            "auth",
            legacy_diskcache_path="var/token_cache.db",
        )

    def test_require_trusted_access_public_and_missing_token(self):
        self.assertTrue(self.service.require_trusted_access())
        self.context.access_mode = "trusted"
        with patch.object(self.service, "_auth_settings", return_value=self.settings):
            self.assertFalse(self.service.require_trusted_access())
        self.request.response.setStatus.assert_called_with(403)

    def test_require_cached_trusted_access_handles_cache_and_metadata(self):
        self.context.access_mode = "trusted"
        self.request.form = {"access_token": "token"}
        cache = MagicMock()
        with (
            patch.object(self.service, "_auth_settings", return_value=self.settings),
            patch.object(self.service, "_token_cache", return_value=cache),
        ):
            cache.get.return_value = None
            self.assertFalse(self.service.require_trusted_access())
            cache.get.return_value = {"state": "REVOKED", "form_id": "form-1"}
            self.assertFalse(self.service.require_trusted_access())
            cache.get.return_value = {"state": "ISSUED", "form_id": "other"}
            self.assertFalse(self.service.require_trusted_access())
            cache.get.return_value = {"state": "ISSUED", "form_id": "form-1"}
            self.assertTrue(self.service.require_trusted_access())

    def test_require_token_store_access_and_consume(self):
        self.context.access_mode = "trusted-tokens"
        self.request.form = {"tt": "token"}
        store = MagicMock()
        store.has_token.return_value = True
        store.consume_token.return_value = True
        with patch(
            "zopyx.surveyjs.browser.services.auth.getAdapter", return_value=store
        ):
            self.assertTrue(self.service.require_trusted_access())
            self.assertTrue(self.service.consume_trusted_access_token())
        store.consume_token.assert_called_once_with("token", reason="user_submission")

        store.has_token.return_value = False
        with patch(
            "zopyx.surveyjs.browser.services.auth.getAdapter", return_value=store
        ):
            self.assertFalse(self.service.require_trusted_access())

    def test_consume_trusted_token_fails_without_token_or_store(self):
        self.context.access_mode = "trusted-tokens"
        self.assertFalse(self.service.consume_trusted_access_token())
        self.request.form = {"tt": "token"}
        with patch(
            "zopyx.surveyjs.browser.services.auth.getAdapter", side_effect=RuntimeError
        ):
            self.assertFalse(self.service.consume_trusted_access_token())

    def test_build_auth_token_is_disabled_or_requires_secret(self):
        with patch.object(self.service, "_auth_settings", return_value=self.settings):
            self.assertEqual(self.service.build_auth_token("v1"), "")
        self.settings.authenticity_token_enabled = True
        with patch.object(self.service, "_auth_settings", return_value=self.settings):
            self.assertEqual(self.service.build_auth_token("v1"), "")

    def test_require_auth_token_fails_closed_and_rejects_bad_token(self):
        self.settings.authenticity_token_enabled = True
        self.settings.authenticity_token_secret = "secret"
        with patch.object(self.service, "_auth_settings", return_value=self.settings):
            self.request.form = {"auth_token": "bad"}
            self.assertFalse(self.service.require_auth_token("v1"))
            self.request.response.setStatus.assert_called()

        self.settings.authenticity_token_secret = ""
        with patch.object(self.service, "_auth_settings", return_value=self.settings):
            self.assertFalse(self.service.require_auth_token("v1"))

    def test_replay_marker_is_released_when_the_attempt_aborts(self):
        """A Zope retry after a ZODB conflict re-runs the view with the same
        token, so the aborted attempt must not leave its marker behind."""
        self.settings.authenticity_token_enabled = True
        self.settings.authenticity_token_secret = "secret"
        with TemporaryDirectory() as tmpdir:
            store = get_kv_store("diskcache", os.path.join(tmpdir, "auth.db"))
            self.addCleanup(store.close)
            with (
                patch.object(
                    self.service, "_auth_settings", return_value=self.settings
                ),
                patch.object(self.service, "_token_cache", return_value=store),
            ):
                token = self.service.build_auth_token("v1")
                self.assertTrue(token)
                marker = f"received:{token}"
                self.request.form = {"auth_token": token}

                self.assertTrue(self.service.require_auth_token("v1"))
                self.assertEqual(store.get(marker), "RECEIVED")

                # A second submission of a consumed token is still a replay
                # as long as the attempt's transaction is alive.
                self.assertFalse(self.service.require_auth_token("v1"))
                self.request.response.setStatus.assert_called_with(403)

                # Zope aborts the conflicted attempt and re-runs the request.
                transaction.abort()
                self.assertIsNone(store.get(marker))

                self.assertTrue(self.service.require_auth_token("v1"))
                self.assertEqual(store.get(marker), "RECEIVED")


if __name__ == "__main__":
    unittest.main()
