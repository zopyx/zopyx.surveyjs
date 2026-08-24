# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from zopyx.surveyjs.security import (
    AuthTokenError,
    build_auth_token,
    validate_auth_token,
)
from zopyx.surveyjs.utils import html_safe_json


class AuthTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.form_id = "form-1"
        self.form_version = "version-1"
        self.issuer = "issuer"
        self.audience = "audience"
        self.secret = "secret"
        self.now = 1700000000

    def test_roundtrip_valid_token(self) -> None:
        token = build_auth_token(
            form_id=self.form_id,
            form_version=self.form_version,
            issuer=self.issuer,
            audience=self.audience,
            ttl_seconds=60,
            secret=self.secret,
            now=self.now,
        )
        payload = validate_auth_token(
            token=token,
            form_id=self.form_id,
            form_version=self.form_version,
            issuer=self.issuer,
            audience=self.audience,
            secret=self.secret,
            now=self.now,
        )
        self.assertEqual(payload["form_id"], self.form_id)

    def test_rejects_expired_token(self) -> None:
        token = build_auth_token(
            form_id=self.form_id,
            form_version=self.form_version,
            issuer=self.issuer,
            audience=self.audience,
            ttl_seconds=1,
            secret=self.secret,
            now=self.now,
        )
        with self.assertRaises(AuthTokenError) as ctx:
            validate_auth_token(
                token=token,
                form_id=self.form_id,
                form_version=self.form_version,
                issuer=self.issuer,
                audience=self.audience,
                secret=self.secret,
                now=self.now + 10,
                skew_seconds=0,
            )
        self.assertEqual(ctx.exception.reason, "auth_token_expired")

    def test_rejects_wrong_audience(self) -> None:
        token = build_auth_token(
            form_id=self.form_id,
            form_version=self.form_version,
            issuer=self.issuer,
            audience=self.audience,
            ttl_seconds=60,
            secret=self.secret,
            now=self.now,
        )
        with self.assertRaises(AuthTokenError) as ctx:
            validate_auth_token(
                token=token,
                form_id=self.form_id,
                form_version=self.form_version,
                issuer=self.issuer,
                audience="other",
                secret=self.secret,
                now=self.now,
            )
        self.assertEqual(ctx.exception.reason, "auth_token_claims_mismatch")

    def test_rejects_wrong_form_version(self) -> None:
        token = build_auth_token(
            form_id=self.form_id,
            form_version=self.form_version,
            issuer=self.issuer,
            audience=self.audience,
            ttl_seconds=60,
            secret=self.secret,
            now=self.now,
        )
        with self.assertRaises(AuthTokenError) as ctx:
            validate_auth_token(
                token=token,
                form_id=self.form_id,
                form_version="other-version",
                issuer=self.issuer,
                audience=self.audience,
                secret=self.secret,
                now=self.now,
            )
        self.assertEqual(ctx.exception.reason, "auth_token_claims_mismatch")

    def test_html_safe_json_escapes_script_terminator(self) -> None:
        encoded = html_safe_json({"value": "</script><script>alert(1)</script>"})
        self.assertNotIn("</script>", encoded)
        self.assertIn("\\u003c/script\\u003e", encoded)
