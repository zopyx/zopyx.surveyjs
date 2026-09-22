"""Coverage tests for embed_direct.py, embed_security.py and psf.py.

Unit-level driver tests: the views are instantiated without a Plone layer and
driven through their real code paths with a minimal request/response double.
Every test asserts the observable outcome (HTTP status, JSON payload, emitted
HTML, header values or call arguments).
"""

from __future__ import annotations

import base64
import hashlib
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch
from urllib.parse import urlparse as real_urlparse

import orjson

from zopyx.surveyjs.browser import embed_direct as embed_module
from zopyx.surveyjs.browser import embed_security
from zopyx.surveyjs.browser import psf as psf_module
from zopyx.surveyjs.browser.embed_direct import (
    DirectEmbedDemoView,
    EmbedConfigView,
    EmbedDirectTokenView,
    EmbedLoaderView,
    EmbedSurveyJSView,
)
from zopyx.surveyjs.browser.psf import PFSView


class FakeResponse:
    """Minimal IHTTPResponse double that keeps what was written."""

    def __init__(self) -> None:
        self.status = 200
        self.headers: dict[str, str] = {}
        self.body = b""
        self.writes: list[bytes] = []
        self.redirects: list[str] = []

    def setStatus(self, status) -> None:
        self.status = status

    def getStatus(self):
        return self.status

    def setHeader(self, name, value) -> None:
        self.headers[name.lower()] = value

    def getHeader(self, name, default=None):
        return self.headers.get(name.lower(), default)

    def setResult(self, body) -> None:
        self.body = body
        self.writes.append(body)

    def write(self, body) -> None:
        self.body = body
        self.writes.append(body)

    def redirect(self, url) -> None:
        self.redirects.append(url)


class FakeRequest:
    """Request double: querystring/form values, headers and a body."""

    def __init__(self, method="GET", body=b"", headers=None, form=None) -> None:
        self.method = method
        self.body = body
        self.headers = {key.lower(): value for key, value in (headers or {}).items()}
        self.form = dict(form or {})
        self.response = FakeResponse()

    def get(self, key, default=None):
        if key == "REQUEST_METHOD":
            return self.method
        if key == "BODY":
            return self.body
        return self.form.get(key, default)

    def get_header(self, name, default=None):
        return self.headers.get(name.lower(), default)

    def json(self):
        return orjson.loads(self.response.body)


def make_view(cls, context=None, request=None):
    view = cls.__new__(cls)
    view.context = MagicMock() if context is None else context
    view.request = FakeRequest() if request is None else request
    return view


def make_context(**attrs) -> MagicMock:
    context = MagicMock()
    context.absolute_url.return_value = "http://nohost/survey"
    context.getId.return_value = "survey-id"
    context.UID.return_value = "survey-1"
    for name, value in attrs.items():
        setattr(context, name, value)
    return context


def sri_for(filepath: pathlib.Path) -> str:
    digest = hashlib.sha384(filepath.read_bytes()).digest()
    return "sha384-" + base64.b64encode(digest).decode("ascii")


STATIC_DIR = pathlib.Path(embed_module.__file__).parent / "static" / "surveyjs"


class EmbedDirectTokenViewTests(unittest.TestCase):
    def make(self, method="GET", body=b"", **context_attrs):
        attrs = {
            "embedding_mode": "direct",
            "embed_direct_origins": ["https://app.example"],
        }
        attrs.update(context_attrs)
        context = make_context(**attrs)
        return make_view(
            EmbedDirectTokenView, context, FakeRequest(method=method, body=body)
        )

    def test_permission_denied_returns_403_json_error(self):
        view = self.make()
        with patch("plone.api.user.has_permission", return_value=False):
            view()
        self.assertEqual(view.request.response.getStatus(), 403)
        self.assertEqual(view.request.json(), {"error": "permission_denied"})
        self.assertEqual(
            view.request.response.getHeader("X-Survey-Error"), "permission_denied"
        )

    def test_feature_disabled_returns_403_with_reason(self):
        view = self.make()
        with (
            patch("plone.api.user.has_permission", return_value=True),
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=False
            ),
        ):
            view()
        self.assertEqual(view.request.response.getStatus(), 403)
        payload = view.request.json()
        self.assertEqual(payload["error"], "feature_disabled")
        self.assertEqual(
            payload["message"], "Direct DOM embedding is not enabled globally"
        )

    def test_wrong_embedding_mode_returns_400(self):
        view = self.make(embedding_mode="iframe")
        with (
            patch("plone.api.user.has_permission", return_value=True),
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=True
            ),
        ):
            view()
        self.assertEqual(view.request.response.getStatus(), 400)
        payload = view.request.json()
        self.assertEqual(payload["error"], "direct_embedding_not_enabled")
        self.assertIn("not configured for Direct DOM embedding", payload["message"])

    def test_unparsable_body_returns_400_invalid_json(self):
        view = self.make(method="POST", body=b"")
        with (
            patch("plone.api.user.has_permission", return_value=True),
            patch.object(embed_module, "CheckAuthenticator"),
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=True
            ),
        ):
            view()
        self.assertEqual(view.request.response.getStatus(), 400)
        self.assertEqual(view.request.json(), {"error": "invalid_json"})

    def test_success_issues_token_bound_to_normalized_origin(self):
        body = orjson.dumps({"origin": "https://app.example/", "ttl_seconds": 120})
        view = self.make(method="POST", body=body)
        token_calls = MagicMock(
            return_value=("token.jwt", {"expires_at": "2026-01-01T00:00:00+00:00"})
        )
        with (
            patch("plone.api.user.has_permission", return_value=True),
            patch.object(embed_module, "CheckAuthenticator") as authenticate,
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=True
            ),
            patch.object(embed_module, "generate_embed_token", side_effect=token_calls),
        ):
            view()

        authenticate.assert_called_once_with(view.request)
        token_calls.assert_called_once_with(
            survey_uid="survey-1",
            origin="https://app.example",
            ttl_seconds=120,
        )
        self.assertEqual(view.request.response.getStatus(), 200)
        self.assertEqual(
            view.request.response.getHeader("content-type"), "application/json"
        )
        payload = view.request.json()
        self.assertEqual(payload["token"], "token.jwt")
        self.assertEqual(payload["origin"], "https://app.example")
        self.assertEqual(payload["survey_uid"], "survey-1")
        self.assertEqual(payload["expires_at"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(payload["embed_url"], "http://nohost/survey/@@embed-loader")

    def test_missing_uid_and_signing_key_failure_are_reported(self):
        context = make_context(
            embedding_mode="direct",
            embed_direct_origins=["https://app.example"],
        )
        context.UID.side_effect = AttributeError("no UID")
        context.getId.return_value = "fallback-id"
        body = orjson.dumps({"origin": "https://app.example"})
        view = make_view(
            EmbedDirectTokenView, context, FakeRequest(method="POST", body=body)
        )
        with (
            patch("plone.api.user.has_permission", return_value=True),
            patch.object(embed_module, "CheckAuthenticator"),
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=True
            ),
            patch.object(
                embed_module,
                "generate_embed_token",
                side_effect=embed_security.EmbedSecurityError("signing key missing"),
            ),
        ):
            view()

        context.UID.assert_called_once()
        self.assertEqual(view.request.response.getStatus(), 500)
        payload = view.request.json()
        self.assertEqual(payload["error"], "token_generation_failed")
        self.assertEqual(payload["message"], "signing key missing")

    def test_uid_fallback_is_used_for_the_token_subject(self):
        context = make_context(
            embedding_mode="direct",
            embed_direct_origins=["https://app.example"],
        )
        context.UID.side_effect = KeyError("no UID")
        context.getId.return_value = "fallback-id"
        body = orjson.dumps({"origin": "https://app.example"})
        view = make_view(
            EmbedDirectTokenView, context, FakeRequest(method="POST", body=body)
        )
        token_calls = MagicMock(return_value=("token.jwt", {"expires_at": "x"}))
        with (
            patch("plone.api.user.has_permission", return_value=True),
            patch.object(embed_module, "CheckAuthenticator"),
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=True
            ),
            patch.object(embed_module, "generate_embed_token", side_effect=token_calls),
        ):
            view()

        self.assertEqual(token_calls.call_args.kwargs["survey_uid"], "fallback-id")
        self.assertEqual(view.request.json()["survey_uid"], "fallback-id")
        self.assertEqual(view.request.response.getStatus(), 200)


class EmbedConfigViewTests(unittest.TestCase):
    ORIGIN = "https://app.example"

    def make(self, headers=None):
        context = make_context(embed_direct_origins=[self.ORIGIN])
        return make_view(
            EmbedConfigView,
            context,
            FakeRequest(headers=headers or {}, form={}),
        )

    def test_preflight_short_circuits_without_body(self):
        view = self.make(headers={"Origin": self.ORIGIN})
        with (
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=True
            ),
            patch.object(
                embed_module, "handle_cors_preflight", return_value=True
            ) as ph,
        ):
            view()
        ph.assert_called_once()
        self.assertEqual(view.request.response.getStatus(), 200)
        self.assertEqual(view.request.response.body, b"")

    def test_disabled_feature_and_foreign_origin_are_rejected(self):
        view = self.make(headers={"Origin": self.ORIGIN})
        with patch.object(
            embed_module, "is_embed_direct_globally_enabled", return_value=False
        ):
            view()
        self.assertEqual(view.request.response.getStatus(), 403)
        self.assertEqual(view.request.json()["error"], "feature_disabled")

        view = self.make(headers={"Origin": "https://evil.example"})
        with patch.object(
            embed_module, "is_embed_direct_globally_enabled", return_value=True
        ):
            view()
        self.assertEqual(view.request.response.getStatus(), 403)
        payload = view.request.json()
        self.assertEqual(payload["error"], "invalid_origin")
        self.assertEqual(payload["message"], "Origin not in allowlist")
        # no CORS headers for a rejected origin
        self.assertIsNone(
            view.request.response.getHeader("Access-Control-Allow-Origin")
        )

    def test_missing_token_is_rejected(self):
        view = self.make(headers={"Origin": self.ORIGIN})
        with patch.object(
            embed_module, "is_embed_direct_globally_enabled", return_value=True
        ):
            view()
        self.assertEqual(view.request.response.getStatus(), 403)
        self.assertEqual(view.request.json()["error"], "token_required")

    def test_token_failures_are_mapped_to_specific_errors(self):
        cases = [
            (embed_module.TokenExpiredError("expired"), 403, "token_expired"),
            (
                embed_module.TokenInvalidError("bad signature"),
                403,
                "token_invalid",
            ),
            (
                embed_module.EmbedSecurityError("signing key missing"),
                403,
                "token_validation_failed",
            ),
        ]
        for error, status, name in cases:
            with self.subTest(name=name):
                view = self.make(
                    headers={"Origin": self.ORIGIN, "X-Embed-Token": "jwt"}
                )
                with (
                    patch.object(
                        embed_module,
                        "is_embed_direct_globally_enabled",
                        return_value=True,
                    ),
                    patch.object(
                        embed_module, "validate_embed_token", side_effect=error
                    ),
                ):
                    view()
                self.assertEqual(view.request.response.getStatus(), status)
                self.assertEqual(view.request.json()["error"], name)

    def test_token_for_another_survey_is_rejected(self):
        view = self.make(headers={"Origin": self.ORIGIN, "X-Embed-Token": "jwt"})
        with (
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=True
            ),
            patch.object(
                embed_module,
                "validate_embed_token",
                return_value={"sub": "other-survey"},
            ),
        ):
            view()
        self.assertEqual(view.request.response.getStatus(), 403)
        self.assertEqual(view.request.json()["error"], "survey_mismatch")

    def test_success_serves_form_json_session_and_csrf_token(self):
        context = make_context(embed_direct_origins=[self.ORIGIN])
        context.UID.side_effect = AttributeError("no UID")
        context.getId.return_value = "survey-id"
        view = make_view(
            EmbedConfigView,
            context,
            FakeRequest(headers={"Origin": self.ORIGIN, "X-Embed-Token": "jwt"}),
        )
        versions = [{"id": "version-7", "form_json": {"pages": [{"name": "p1"}]}}]
        with (
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=True
            ),
            patch.object(
                embed_module,
                "validate_embed_token",
                return_value={"sub": "survey-id"},
            ) as validate,
            patch.object(embed_module, "IAnnotations", return_value="annos"),
            patch.object(
                embed_module.forms_service,
                "sorted_form_versions",
                return_value=versions,
            ) as sorted_versions,
            patch(
                "plone.api.portal.get_tool",
                return_value=MagicMock(return_value="http://nohost/plone"),
            ),
            patch(
                "plone.protect.authenticator.createToken",
                return_value="csrf-from-authenticator",
            ),
        ):
            view()

        validate.assert_called_once_with("jwt", self.ORIGIN, secret=None)
        sorted_versions.assert_called_once_with("annos")
        self.assertEqual(
            view.request.response.getHeader("Access-Control-Allow-Origin"), self.ORIGIN
        )
        self.assertEqual(view.request.response.getStatus(), 200)
        payload = view.request.json()
        self.assertEqual(payload["form_json"], {"pages": [{"name": "p1"}]})
        self.assertEqual(payload["form_version"], "version-7")
        self.assertEqual(payload["csrf_token"], "csrf-from-authenticator")
        self.assertEqual(payload["submit_endpoint"], "http://nohost/survey/@@save-poll")
        self.assertGreater(len(payload["session_id"]), 16)

    def test_success_without_versions_and_without_csrf_helper(self):
        context = make_context(embed_direct_origins=[self.ORIGIN])
        view = make_view(
            EmbedConfigView,
            context,
            FakeRequest(headers={"Origin": self.ORIGIN, "X-Embed-Token": "jwt"}),
        )
        with (
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=True
            ),
            patch.object(
                embed_module, "validate_embed_token", return_value={"sub": "survey-1"}
            ),
            patch.object(embed_module, "IAnnotations", return_value="annos"),
            patch.object(
                embed_module.forms_service, "sorted_form_versions", return_value=[]
            ),
            patch(
                "plone.api.portal.get_tool",
                return_value=MagicMock(return_value="http://nohost/plone"),
            ),
            patch(
                "plone.protect.authenticator.createToken",
                side_effect=RuntimeError("no authenticator"),
            ),
        ):
            view()

        payload = view.request.json()
        self.assertEqual(payload["form_json"], {})
        self.assertEqual(payload["form_version"], "")
        self.assertEqual(len(payload["csrf_token"]), 43)


class EmbedSurveyJSViewTests(unittest.TestCase):
    def make(self, name):
        return make_view(EmbedSurveyJSView, None, FakeRequest(form={"name": name}))

    def test_unknown_asset_is_not_served(self):
        view = self.make("evil.js")
        self.assertEqual(view(), "Not found")
        self.assertEqual(view.request.response.getStatus(), 404)

    def test_allowlisted_asset_is_served_with_public_cors_headers(self):
        view = self.make("survey.core.min.js")
        content = view()
        response = view.request.response
        self.assertEqual(content, (STATIC_DIR / "survey.core.min.js").read_bytes())
        self.assertGreater(len(content), 1000)
        self.assertEqual(
            response.getHeader("Content-Type"),
            "application/javascript; charset=utf-8",
        )
        self.assertEqual(response.getHeader("Access-Control-Allow-Origin"), "*")
        self.assertEqual(
            response.getHeader("Cache-Control"), "public, max-age=86400, immutable"
        )
        self.assertEqual(response.getHeader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.getStatus(), 200)

    def test_missing_asset_file_reports_not_found(self):
        view = self.make("survey-js-ui.min.js")
        with patch("builtins.open", side_effect=OSError("gone")):
            self.assertEqual(view(), "Not found")
        self.assertEqual(view.request.response.getStatus(), 404)


class EmbedLoaderViewTests(unittest.TestCase):
    def make(self, headers=None):
        return make_view(
            EmbedLoaderView, make_context(), FakeRequest(headers=headers or {})
        )

    def test_loader_script_contains_hashes_and_portal_urls(self):
        view = self.make(headers={"Origin": "https://app.example"})
        with patch("plone.api.portal.get_tool") as get_tool:
            get_tool.return_value.return_value = "http://nohost/plone"
            script = view()

        get_tool.assert_called_once_with("portal_url")
        response = view.request.response
        self.assertEqual(
            response.getHeader("Access-Control-Allow-Origin"), "https://app.example"
        )
        self.assertEqual(response.getHeader("Vary"), "Origin")
        self.assertEqual(
            response.getHeader("Cache-Control"), "no-cache, no-store, must-revalidate"
        )
        self.assertEqual(response.getHeader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(
            response.getHeader("Content-Type"), "application/javascript; charset=utf-8"
        )
        self.assertIn("http://nohost/plone/@@embed-surveyjs?name", script)
        self.assertIn("http://nohost/survey/@@embed-loader", script)
        self.assertIn(sri_for(STATIC_DIR / "survey.core.min.js"), script)
        self.assertIn(sri_for(STATIC_DIR / "survey-js-ui.min.js"), script)

    def test_loader_script_without_origin_and_without_readable_assets(self):
        view = self.make()
        with (
            patch(
                "plone.api.portal.get_tool",
                return_value=MagicMock(return_value="http://nohost/plone"),
            ),
            patch("builtins.open", side_effect=OSError("unreadable")),
        ):
            script = view()

        self.assertIsNone(
            view.request.response.getHeader("Access-Control-Allow-Origin")
        )
        self.assertIn(
            "loadScript('http://nohost/plone/@@embed-surveyjs?name=survey.core.min.js', '')",
            script,
        )

    def test_sri_hash_returns_none_for_missing_file(self):
        self.assertIsNone(EmbedLoaderView._sri_hash("/no/such/file.js"))
        self.assertEqual(
            EmbedLoaderView._sri_hash(str(STATIC_DIR / "survey.core.min.js")),
            sri_for(STATIC_DIR / "survey.core.min.js"),
        )


class DirectEmbedDemoViewTests(unittest.TestCase):
    ORIGIN = "https://app.example"

    def make(self, **context_attrs):
        attrs = {
            "embedding_mode": "direct",
            "embed_direct_origins": [self.ORIGIN],
            "embed_direct_token_ttl": 300,
            "title": "Demo Survey",
        }
        attrs.update(context_attrs)
        return make_view(DirectEmbedDemoView, make_context(**attrs))

    def test_permission_denied(self):
        view = self.make()
        with patch("plone.api.user.has_permission", return_value=False):
            result = view()
        self.assertEqual(result, "Access denied")
        self.assertEqual(view.request.response.getStatus(), 403)

    def test_configuration_errors_are_rendered_as_html(self):
        cases = [
            ({"embedding_mode": "iframe"}, "Direct embedding not enabled"),
            ({"embed_direct_origins": []}, "No origins configured"),
        ]
        for attrs, expected in cases:
            with self.subTest(expected=expected):
                view = self.make(**attrs)
                with patch("plone.api.user.has_permission", return_value=True):
                    with patch.object(
                        embed_module,
                        "is_embed_direct_globally_enabled",
                        return_value=True,
                    ):
                        html_body = view()
                self.assertIn(expected, html_body)
                self.assertIn("Configuration Error", html_body)
                self.assertIn("http://nohost/survey/edit", html_body)
                self.assertEqual(
                    view.request.response.getHeader("Content-Type"),
                    "text/html; charset=utf-8",
                )

    def test_feature_disabled_is_rendered_as_configuration_error(self):
        view = self.make()
        with (
            patch("plone.api.user.has_permission", return_value=True),
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=False
            ),
        ):
            html_body = view()
        self.assertIn("Feature disabled", html_body)
        self.assertIn("Direct DOM embedding is not enabled globally.", html_body)

    def test_token_generation_failure_is_rendered(self):
        view = self.make()
        with (
            patch("plone.api.user.has_permission", return_value=True),
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=True
            ),
            patch.object(
                embed_module,
                "generate_embed_token",
                side_effect=embed_security.EmbedSecurityError("no signing key"),
            ),
        ):
            html_body = view()
        self.assertIn("Token generation failed", html_body)
        self.assertIn("no signing key", html_body)

    def test_demo_page_escapes_and_embeds_token(self):
        view = self.make()
        token, metadata = 'a"b<c', {"expires_at": "2026-01-01T00:00:00+00:00"}
        generate = MagicMock(return_value=(token, metadata))
        with (
            patch("plone.api.user.has_permission", return_value=True),
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=True
            ),
            patch.object(embed_module, "generate_embed_token", side_effect=generate),
        ):
            html_body = view()

        generate.assert_called_once_with("survey-1", self.ORIGIN, 300)
        self.assertIn(
            "<title>Direct DOM Embedding Demo - Demo Survey</title>", html_body
        )
        self.assertIn("2026-01-01T00:00:00+00:00", html_body)
        self.assertIn(self.ORIGIN, html_body)
        self.assertIn("&lt;c", html_body)
        self.assertNotIn('"a\\"b<c"', html_body)
        self.assertIn("Tokens expire after 300 seconds", html_body)
        self.assertIn('src="http://nohost/survey/@@embed-loader"', html_body)
        self.assertEqual(
            view.request.response.getHeader("Content-Type"),
            "text/html; charset=utf-8",
        )

    def test_demo_page_falls_back_to_content_id(self):
        context = make_context(
            embedding_mode="direct",
            embed_direct_origins=[self.ORIGIN],
            embed_direct_token_ttl=0,
            title="",
        )
        context.UID.side_effect = AttributeError("no UID")
        context.getId.return_value = "fallback-id"
        view = make_view(DirectEmbedDemoView, context)
        generate = MagicMock(return_value=("tok", {"expires_at": "x"}))
        with (
            patch("plone.api.user.has_permission", return_value=True),
            patch.object(
                embed_module, "is_embed_direct_globally_enabled", return_value=True
            ),
            patch.object(embed_module, "generate_embed_token", side_effect=generate),
        ):
            html_body = view()

        self.assertEqual(generate.call_args.args[0], "fallback-id")
        self.assertEqual(generate.call_args.args[2], 300)
        self.assertIn("Tokens expire after 300 seconds", html_body)


class EmbedSecurityCoverageTests(unittest.TestCase):
    ORIGIN = "https://client.example"

    def test_cache_and_signing_key_lookups_fail_safe(self):
        with patch.object(
            embed_security, "getUtility", side_effect=RuntimeError("no registry")
        ):
            self.assertIsNone(embed_security._get_embed_cache())
            self.assertIsNone(embed_security._get_signing_key())

        self.assertIsNone(
            embed_security._get_signing_key(
                SimpleNamespace(embed_direct_signing_key="   ")
            )
        )
        self.assertIsNone(embed_security._get_signing_key(SimpleNamespace()))
        self.assertEqual(
            embed_security._get_signing_key(
                SimpleNamespace(embed_direct_signing_key="  key-1  ")
            ),
            "key-1",
        )

    def test_signing_key_is_read_from_the_registry(self):
        settings = SimpleNamespace(embed_direct_signing_key="registry-key")
        registry = MagicMock()
        registry.forInterface.return_value = settings
        with patch.object(embed_security, "getUtility", return_value=registry):
            self.assertEqual(embed_security._get_signing_key(), "registry-key")
        registry.forInterface.assert_called_once()

    def test_validate_origin_handles_unparsable_input_and_non_http_scheme(self):
        with patch.object(
            embed_security, "urlparse", side_effect=ValueError("cannot parse")
        ):
            self.assertEqual(
                embed_security.validate_origin(self.ORIGIN, [self.ORIGIN]),
                (False, None, "Invalid origin format"),
            )

        self.assertEqual(
            embed_security.validate_origin("ftp://localhost", ["ftp://localhost"]),
            (False, None, "Origin must use HTTP or HTTPS"),
        )

    def test_validate_origin_tolerates_unparsable_allowlist_entries(self):
        calls = {"n": 0}

        def flaky(value):
            calls["n"] += 1
            if calls["n"] == 1:
                return real_urlparse(value)
            raise ValueError("unparsable allowlist entry")

        with patch.object(embed_security, "urlparse", side_effect=flaky):
            valid, normalized, error = embed_security.validate_origin(
                self.ORIGIN, [self.ORIGIN]
            )

        self.assertTrue(valid)
        self.assertEqual(normalized, self.ORIGIN)
        self.assertIsNone(error)
        self.assertGreaterEqual(calls["n"], 2)

    def test_generate_embed_token_requires_registry_signing_key(self):
        with (
            patch.object(embed_security, "_get_signing_key", return_value=None),
            self.assertRaises(embed_security.EmbedSecurityError) as ctx,
        ):
            embed_security.generate_embed_token("survey-1", self.ORIGIN)
        self.assertIn("embed_direct_signing_key", str(ctx.exception))


class PFSViewCoverageTests(unittest.TestCase):
    def make(self, **context_attrs):
        context = make_context(**context_attrs)
        context.getPhysicalPath.return_value = ("", "folder")
        return make_view(PFSView, context)

    def test_post_with_create_action_dispatches_to_template_handler(self):
        request = FakeRequest(
            method="POST", form={"pfs_action": "create_from_template"}
        )
        view = make_view(PFSView, make_context(), request)
        with (
            patch.object(psf_module, "CheckAuthenticator") as authenticate,
            patch.object(
                view, "_handle_create_from_template", return_value="created"
            ) as handler,
        ):
            self.assertEqual(view(), "created")
        authenticate.assert_called_once_with(request)
        handler.assert_called_once()

    def test_post_with_other_action_renders_the_index(self):
        request = FakeRequest(method="POST", form={"pfs_action": "nothing"})
        view = make_view(PFSView, make_context(), request)
        with (
            patch.object(psf_module, "CheckAuthenticator"),
            patch.object(view, "index", return_value="index-html"),
        ):
            self.assertEqual(view(), "index-html")

    def test_get_renders_the_index(self):
        view = self.make()
        with patch.object(view, "index", return_value="index-html"):
            self.assertEqual(view(), "index-html")

    def test_permission_properties_use_the_security_manager(self):
        view = self.make()
        manager = MagicMock()
        manager.checkPermission.return_value = True
        with (
            patch("plone.api.user.is_anonymous", return_value=False),
            patch.object(psf_module, "getSecurityManager", return_value=manager),
        ):
            self.assertTrue(view.can_add_survey)
            self.assertTrue(view.can_view_forms_overview)
            self.assertFalse(view.is_anonymous)
        manager.checkPermission.assert_any_call(psf_module.AddSurvey, view.context)
        manager.checkPermission.assert_any_call(psf_module.ManagePortal, view.context)

        manager.checkPermission.return_value = False
        with (
            patch("plone.api.user.is_anonymous", return_value=False),
            patch.object(psf_module, "getSecurityManager", return_value=manager),
        ):
            self.assertFalse(view.can_add_survey)
            self.assertFalse(view.can_view_forms_overview)

    def test_anonymous_visitors_have_no_permissions(self):
        view = self.make()
        with patch("plone.api.user.is_anonymous", return_value=True):
            self.assertFalse(view.can_add_survey)
            self.assertFalse(view.can_view_forms_overview)
            self.assertFalse(view.has_templates)
            self.assertEqual(view.cards, [])

    def test_create_from_template_requires_add_permission_and_options(self):
        view = self.make()
        with (
            patch.object(
                type(view),
                "can_add_survey",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(
                type(view),
                "template_options",
                new_callable=PropertyMock,
                return_value=[{"uid": "uid-1"}],
            ),
        ):
            self.assertTrue(view.can_create_from_template)
        with patch.object(
            type(view), "can_add_survey", new_callable=PropertyMock, return_value=False
        ):
            self.assertFalse(view.can_create_from_template)

    def test_url_properties(self):
        portal = MagicMock()
        portal.absolute_url.return_value = "http://nohost/plone"
        view = self.make()
        with patch("plone.api.portal.get", return_value=portal):
            self.assertEqual(
                view.administration_url, "http://nohost/plone/@@forms-settings"
            )
            self.assertEqual(view.monitor_url, "http://nohost/plone/@@survey-monitor")
            self.assertEqual(view.login_url, "http://nohost/plone/login")
        self.assertEqual(view.add_survey_url, "http://nohost/survey/@@survey-add")
        self.assertEqual(
            view.forms_overview_url, "http://nohost/survey/@@survey-overview"
        )
        self.assertEqual(
            view.templates_overview_url,
            "http://nohost/survey/@@survey-templates-overview",
        )

    def test_cards_reflect_permissions_and_available_templates(self):
        view = self.make()
        portal = MagicMock()
        portal.absolute_url.return_value = "http://nohost/plone"
        with (
            patch("plone.api.portal.get", return_value=portal),
            patch.object(
                type(view),
                "can_add_survey",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(
                type(view),
                "can_view_forms_overview",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(
                type(view),
                "has_templates",
                new_callable=PropertyMock,
                return_value=True,
            ),
        ):
            cards = view.cards
        urls = [card["url"] for card in cards]
        self.assertEqual(
            urls,
            [
                "http://nohost/survey/@@survey-add",
                "http://nohost/survey/@@survey-overview",
                "http://nohost/survey/@@survey-templates-overview",
                "http://nohost/plone/@@survey-monitor",
                "http://nohost/plone/@@forms-settings",
            ],
        )
        self.assertEqual(
            [card["accent"] for card in cards][-2:], ["manager", "manager"]
        )

    def test_cards_without_forms_overview_and_without_templates(self):
        view = self.make()
        with (
            patch.object(
                type(view),
                "can_add_survey",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(
                type(view),
                "can_view_forms_overview",
                new_callable=PropertyMock,
                return_value=False,
            ),
        ):
            cards = view.cards
        self.assertEqual(
            [card["url"] for card in cards], ["http://nohost/survey/@@survey-add"]
        )

        view = self.make()
        portal = MagicMock()
        portal.absolute_url.return_value = "http://nohost/plone"
        with (
            patch("plone.api.portal.get", return_value=portal),
            patch.object(
                type(view),
                "can_add_survey",
                new_callable=PropertyMock,
                return_value=False,
            ),
            patch.object(
                type(view),
                "can_view_forms_overview",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(
                type(view),
                "has_templates",
                new_callable=PropertyMock,
                return_value=False,
            ),
        ):
            cards = view.cards
        self.assertEqual(len(cards), 3)
        self.assertNotIn(
            "http://nohost/survey/@@survey-templates-overview",
            [card["url"] for card in cards],
        )

    def test_template_options_and_has_templates_query_the_catalog(self):
        brain = MagicMock(UID="uid-1", Title="Tpl", Description="Desc")
        brain.getURL.return_value = "http://nohost/survey/tpl"
        catalog = MagicMock()
        catalog.searchResults.return_value = [brain]
        view = self.make()
        with (
            patch("plone.api.user.is_anonymous", return_value=False),
            patch("plone.api.portal.get_tool", return_value=catalog),
        ):
            options = view.template_options
            self.assertTrue(view.has_templates)

        self.assertEqual(
            options,
            [
                {
                    "uid": "uid-1",
                    "title": "Tpl",
                    "description": "Desc",
                    "url": "http://nohost/survey/tpl",
                }
            ],
        )
        catalog.searchResults.assert_any_call(
            portal_type="SurveyTemplate", sort_on="sortable_title"
        )
        catalog.searchResults.assert_any_call(
            portal_type="SurveyTemplate",
            path={"query": "/folder", "depth": -1},
            sort_limit=1,
        )

        catalog.searchResults.return_value = []
        with (
            patch("plone.api.user.is_anonymous", return_value=False),
            patch("plone.api.portal.get_tool", return_value=catalog),
        ):
            self.assertEqual(view.template_options, [])
            self.assertFalse(view.has_templates)

    def test_create_from_template_denied_without_permission(self):
        request = FakeRequest(form={"template_uid": "uid-1"})
        view = make_view(PFSView, make_context(), request)
        with patch.object(
            type(view), "can_add_survey", new_callable=PropertyMock, return_value=False
        ):
            message = view._handle_create_from_template()
        self.assertEqual(message, "You are not allowed to add surveys here.")
        self.assertEqual(request.response.getStatus(), 403)
        self.assertEqual(request.response.redirects, [])

    def test_create_from_template_requires_a_template_uid(self):
        request = FakeRequest(form={})
        view = make_view(PFSView, make_context(), request)
        with (
            patch.object(
                type(view),
                "can_add_survey",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch("plone.api.portal.show_message") as show_message,
        ):
            view._handle_create_from_template()
        self.assertEqual(show_message.call_args.args[0], "Please select a template.")
        self.assertEqual(request.response.redirects, ["http://nohost/survey/@@pfs"])

    def test_create_from_template_reports_missing_template_and_json(self):
        cases = [
            (None, "Template not found."),
            (MagicMock(template_json=""), "Template JSON is missing."),
        ]
        for template, expected in cases:
            with self.subTest(expected=expected):
                request = FakeRequest(form={"template_uid": "uid-1"})
                view = make_view(PFSView, make_context(), request)
                with (
                    patch.object(
                        type(view),
                        "can_add_survey",
                        new_callable=PropertyMock,
                        return_value=True,
                    ),
                    patch("plone.api.content.get", return_value=template),
                    patch("plone.api.portal.show_message") as show_message,
                ):
                    view._handle_create_from_template()
                self.assertEqual(show_message.call_args.args[0], expected)
                self.assertEqual(
                    request.response.redirects, ["http://nohost/survey/@@pfs"]
                )

    def test_create_from_template_reports_invalid_json(self):
        request = FakeRequest(form={"template_uid": "uid-1"})
        view = make_view(PFSView, make_context(), request)
        template = MagicMock(template_json="{not json")
        with (
            patch.object(
                type(view),
                "can_add_survey",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch("plone.api.content.get", return_value=template),
            patch("plone.api.portal.show_message") as show_message,
        ):
            view._handle_create_from_template()
        message = show_message.call_args.args[0]
        self.assertIn("Template JSON is invalid", message)
        self.assertEqual(request.response.redirects, ["http://nohost/survey/@@pfs"])

    def _run_create_success(self, survey, template, form={"template_uid": "uid-1"}):
        request = FakeRequest(form=form)
        view = make_view(PFSView, make_context(), request)
        with (
            patch.object(
                type(view),
                "can_add_survey",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch("plone.api.content.get", return_value=template),
            patch("plone.api.content.create", return_value=survey) as create,
            patch("plone.api.portal.show_message") as show_message,
            patch("plone.api.user.get_current") as get_current,
            patch.object(psf_module, "IAnnotations", return_value="annos") as annos,
            patch.object(psf_module.forms_service, "save_form_version") as save_version,
        ):
            get_current.return_value.getId.return_value = "user-1"
            result = view._handle_create_from_template()
        return {
            "view": view,
            "request": request,
            "result": result,
            "create": create,
            "show_message": show_message,
            "annos": annos,
            "save_version": save_version,
        }

    def test_create_from_template_creates_survey_and_stores_version(self):
        template = MagicMock()
        template.template_json = orjson.dumps({"pages": []})
        template.Title = lambda: "Template Title"
        template.Description = lambda: "Template description"
        survey = MagicMock()
        outcome = self._run_create_success(survey, template)

        self.assertEqual(
            outcome["create"].call_args.kwargs,
            {
                "container": outcome["view"].context,
                "type": "Survey",
                "title": "Template Title",
                "description": "Template description",
            },
        )
        outcome["annos"].assert_called_once_with(survey)
        self.assertEqual(
            outcome["save_version"].call_args.args, ("annos", {"pages": []}, "user-1")
        )
        self.assertEqual(outcome["save_version"].call_args.kwargs, {"locked": False})
        self.assertEqual(
            [call.args[0] for call in outcome["show_message"].call_args_list],
            ["Survey created from template."],
        )
        self.assertEqual(outcome["save_version"].call_count, 1)
        outcome["save_version"].assert_called_once()
        self.assertEqual(outcome["request"].response.redirects, [survey.absolute_url()])
        self.assertIsNone(outcome["result"])

    def test_create_from_template_skips_unassignable_fields_and_uses_title_fallback(
        self,
    ):
        template = MagicMock()
        template.template_json = orjson.dumps({"pages": [1]})
        template.Title = lambda: ""
        template.Description = None
        template.description = "From description"
        # spec_set: every ISurvey field assignment raises -> the loop's
        # ``except Exception: continue`` branch runs for each field.
        survey = MagicMock(spec_set=["absolute_url"])
        outcome = self._run_create_success(
            survey, template, form={"template_uid": "uid-1"}
        )

        self.assertEqual(
            outcome["create"].call_args.kwargs["description"], "From description"
        )
        self.assertEqual(outcome["create"].call_args.kwargs["title"], "New Survey")
        self.assertEqual(
            outcome["save_version"].call_args.args, ("annos", {"pages": [1]}, "user-1")
        )

    def test_create_from_template_skips_fields_absent_from_template(self):
        # A template lacking (some) ISurvey fields: the ``continue`` guard runs.
        template = MagicMock(spec_set=["template_json", "Title"])
        template.template_json = orjson.dumps({"pages": []})
        template.Title = lambda: "Limited Template"
        outcome = self._run_create_success(MagicMock(), template)

        self.assertEqual(
            outcome["create"].call_args.kwargs["title"], "Limited Template"
        )
        self.assertEqual(outcome["create"].call_args.kwargs["description"], "")
        self.assertEqual(
            outcome["save_version"].call_args.args, ("annos", {"pages": []}, "user-1")
        )

    def test_create_from_template_reports_creation_failure(self):
        template = MagicMock()
        template.template_json = orjson.dumps({"pages": []})
        template.Title = lambda: "T"
        template.Description = lambda: "D"
        request = FakeRequest(form={"template_uid": "uid-1"})
        view = make_view(PFSView, make_context(), request)
        with (
            patch.object(
                type(view),
                "can_add_survey",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch("plone.api.content.get", return_value=template),
            patch(
                "plone.api.content.create", side_effect=ValueError("container is full")
            ),
            patch("plone.api.portal.show_message") as show_message,
        ):
            view._handle_create_from_template()

        message = show_message.call_args.args[0]
        self.assertEqual(str(message), "Failed to create survey: ${error}")
        self.assertEqual(message.mapping["error"], "container is full")
        self.assertEqual(show_message.call_args.kwargs["type"], "error")
        self.assertEqual(request.response.redirects, ["http://nohost/survey/@@pfs"])


if __name__ == "__main__":
    unittest.main()
