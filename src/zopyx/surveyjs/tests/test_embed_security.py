from types import SimpleNamespace
import time
import unittest
from unittest.mock import MagicMock, patch

import jwt

from zopyx.surveyjs.browser import embed_security


SECRET = "test-signing-secret"
ORIGIN = "https://client.example"


class EmbedSecurityTests(unittest.TestCase):
    def test_validate_origin_accepts_allowlisted_https_and_trailing_slash(self):
        valid, normalized, error = embed_security.validate_origin(
            ORIGIN, ["https://client.example/"]
        )
        self.assertTrue(valid)
        self.assertEqual(normalized, ORIGIN)
        self.assertIsNone(error)

    def test_validate_origin_rejects_missing_insecure_path_and_unknown(self):
        cases = [
            (None, "Origin header required"),
            ("http://remote.example", "HTTPS required"),
            ("https://client.example/path", "must not contain path"),
            ("https://unknown.example", "not in allowlist"),
            ("ftp://client.example", "HTTPS required"),
        ]
        for origin, expected in cases:
            with self.subTest(origin=origin):
                valid, normalized, error = embed_security.validate_origin(
                    origin, [ORIGIN]
                )
                self.assertFalse(valid)
                self.assertIsNone(normalized)
                self.assertIn(expected, error)

    def test_validate_origin_allows_localhost_http(self):
        valid, normalized, error = embed_security.validate_origin(
            "http://localhost:8080", ["http://localhost:8080"]
        )
        self.assertTrue(valid)
        self.assertEqual(normalized, "http://localhost:8080")
        self.assertIsNone(error)

    def test_validate_embed_token_accepts_valid_token_and_checks_claims(self):
        payload = {
            "iss": "privacyforms.studio",
            "aud": "embed-client",
            "sub": "survey-1",
            "origin": ORIGIN,
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "jti": "jti-1",
        }
        token = embed_security.build_embed_token(payload, SECRET)
        self.assertEqual(
            embed_security.validate_embed_token(token, ORIGIN, SECRET)["sub"],
            "survey-1",
        )

    def test_validate_embed_token_rejects_expired_tampered_and_wrong_origin(self):
        expired = {
            "iss": "privacyforms.studio",
            "aud": "embed-client",
            "sub": "survey-1",
            "origin": ORIGIN,
            "iat": 1,
            "exp": 2,
            "jti": "expired",
        }
        with self.assertRaises(embed_security.TokenExpiredError):
            embed_security.validate_embed_token(
                embed_security.build_embed_token(expired, SECRET), ORIGIN, SECRET
            )

        valid = {
            "iss": "privacyforms.studio",
            "aud": "embed-client",
            "sub": "survey-1",
            "origin": ORIGIN,
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "jti": "jti-2",
        }
        token = embed_security.build_embed_token(valid, SECRET)
        with self.assertRaises(embed_security.TokenInvalidError):
            embed_security.validate_embed_token(token + "tampered", ORIGIN, SECRET)
        with self.assertRaises(embed_security.EmbedSecurityError) as ctx:
            embed_security.validate_embed_token(token, "https://other.example", SECRET)
        self.assertEqual(ctx.exception.reason, "origin_mismatch")

    def test_validate_embed_token_requires_configured_key(self):
        with patch(
            "zopyx.surveyjs.browser.embed_security._get_signing_key",
            return_value=None,
        ), self.assertRaises(embed_security.EmbedSecurityError):
            embed_security.validate_embed_token("token", ORIGIN)

    def test_embed_cache_uses_configured_kv_facade_factory(self):
        settings = SimpleNamespace(kv_cache_backend="diskcache")
        registry = MagicMock()
        registry.forInterface.return_value = settings
        with patch(
            "zopyx.surveyjs.browser.embed_security.getUtility",
            return_value=registry,
        ), patch(
            "zopyx.surveyjs.browser.embed_security.get_configured_kv_store",
            return_value="cache",
        ) as factory:
            self.assertEqual(embed_security._get_embed_cache(), "cache")
        factory.assert_called_once_with(settings, "embed")

    def test_generate_embed_token_fails_closed_without_tracking_cache(self):
        with patch(
            "zopyx.surveyjs.browser.embed_security._get_embed_cache",
            return_value=None,
        ), self.assertRaises(embed_security.EmbedSecurityError):
            embed_security.generate_embed_token("survey-1", ORIGIN, secret=SECRET)

    def test_generate_embed_token_clamps_ttl_and_records_cache_metadata(self):
        cache = MagicMock()
        with patch(
            "zopyx.surveyjs.browser.embed_security._get_embed_cache",
            return_value=cache,
        ), patch(
            "zopyx.surveyjs.browser.embed_security.time.time",
            return_value=2000000000,
        ), patch(
            "zopyx.surveyjs.browser.embed_security.secrets.token_urlsafe",
            side_effect=["jti-generated", "nonce-generated"],
        ):
            token, metadata = embed_security.generate_embed_token(
                "survey-1", ORIGIN, ttl_seconds=1, secret=SECRET
            )

        claims = jwt.decode(
            token,
            SECRET,
            algorithms=["HS256"],
            audience="embed-client",
            issuer="privacyforms.studio",
            options={"verify_iat": False},
        )
        self.assertEqual(claims["exp"], 2000000060)
        self.assertEqual(metadata["jti"], "jti-generated")
        cache.set.assert_called_once()
        cache.close.assert_called_once()

    def test_mark_token_used_is_fail_closed_without_cache_and_atomic_with_cache(self):
        with patch(
            "zopyx.surveyjs.browser.embed_security._get_embed_cache",
            return_value=None,
        ):
            self.assertFalse(embed_security.mark_token_used("jti"))

        cache = MagicMock()
        cache.add.side_effect = [True, False]
        with patch(
            "zopyx.surveyjs.browser.embed_security._get_embed_cache",
            return_value=cache,
        ):
            self.assertTrue(embed_security.mark_token_used("jti"))
            self.assertFalse(embed_security.mark_token_used("jti"))
        self.assertEqual(cache.close.call_count, 2)

    def test_cors_headers_and_preflight(self):
        response = MagicMock()
        embed_security.set_cors_headers(response, ORIGIN)
        response.setHeader.assert_any_call("Access-Control-Allow-Origin", ORIGIN)
        response.setHeader.assert_any_call("X-Content-Type-Options", "nosniff")

        request = {"REQUEST_METHOD": "GET"}
        self.assertFalse(
            embed_security.handle_cors_preflight(request, response, [ORIGIN])
        )

        request = MagicMock()
        request.get.side_effect = lambda name: "OPTIONS" if name == "REQUEST_METHOD" else None
        request.get_header.return_value = ORIGIN
        self.assertTrue(
            embed_security.handle_cors_preflight(request, response, [ORIGIN])
        )
        response.setStatus.assert_called_with(204)

    def test_registry_helpers_are_fail_safe_and_clamped(self):
        with patch(
            "zopyx.surveyjs.browser.embed_security.getUtility",
            side_effect=RuntimeError,
        ):
            self.assertFalse(embed_security.is_embed_direct_globally_enabled())
            self.assertEqual(embed_security.get_embed_direct_max_origins(), 10)

        settings = SimpleNamespace(
            embed_direct_global_enabled=True,
            embed_direct_max_origins=500,
        )
        registry = MagicMock()
        registry.forInterface.return_value = settings
        with patch(
            "zopyx.surveyjs.browser.embed_security.getUtility",
            return_value=registry,
        ):
            self.assertTrue(embed_security.is_embed_direct_globally_enabled())
            self.assertEqual(embed_security.get_embed_direct_max_origins(), 100)


if __name__ == "__main__":
    unittest.main()
