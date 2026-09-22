# -*- coding: utf-8 -*-
"""Coverage tests for :mod:`zopyx.surveyjs.browser.views`.

The module is mostly driven here through standalone view instances with real
(but hand-rolled) request/response stubs, so the assertions can look at the
actual HTTP status, headers and bytes the view produced instead of at mocks.
"""

from __future__ import annotations

import csv
import io
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import orjson
import plone.api
from BTrees.OOBTree import OOBTree

from zopyx.surveyjs.browser import embed_security as embed_security_module
from zopyx.surveyjs.browser import views as views_module
from zopyx.surveyjs.browser.views import (
    EmbeddedDemoView,
    RootRedirect,
    Views,
    _run_external_validation,
)
from zopyx.surveyjs.constants import FORM_VERSIONS_KEY

SURVEY_URL = "http://nohost/survey"

SURVEY_FORM_JSON = {
    "pages": [{"elements": [{"type": "text", "name": "q1"}]}],
}


# --------------------------------------------------------------------------
# request / response stubs
# --------------------------------------------------------------------------


class _Response:
    """Response stub without ``setResult`` (exercises the ``write`` path)."""

    def __init__(self) -> None:
        self.status = None
        self.headers: dict[str, str] = {}
        self.written = b""
        self.redirected = None
        self.results: list[bytes] = []

    def setStatus(self, status) -> None:
        self.status = status

    def getStatus(self):
        return self.status

    def setHeader(self, name, value) -> None:
        self.headers[name] = value

    def getHeader(self, name, default=None):
        return self.headers.get(name, default)

    def write(self, data) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.written += data

    def redirect(self, target):
        self.redirected = target
        return target

    def json(self):
        return orjson.loads(self.written)


class _ResultResponse(_Response):
    """Response stub with ``setResult`` (exercises the setResult path)."""

    def setResult(self, data) -> None:
        self.results.append(data)
        self.written += data


class _Request:
    def __init__(self, form=None, method="POST", headers=None, environ=None):
        self.form = dict(form or {})
        self.method = method
        self.headers = {key.lower(): value for key, value in (headers or {}).items()}
        self.environ = dict(environ or {})
        self.response = _Response()

    def get(self, key, default=None):
        if key == "REQUEST_METHOD":
            return self.method
        return self.environ.get(key, default)

    def get_header(self, name, default=None):
        return self.headers.get(name.lower(), default)

    def getHeader(self, name, default=None):
        return self.headers.get(name.lower(), default)


class _ExplodingAttribute:
    """Object whose attribute access raises."""

    def __getattr__(self, name):
        raise RuntimeError(f"no attribute {name}")


class _IsoObject:
    def __init__(self, text):
        self._text = text

    def ISO(self):
        return self._text


class _BadIsoformat:
    def isoformat(self, *args, **kwargs):
        raise TypeError("timespec not supported")


def _patch_current_user():
    """Patch ``plone.api.user.get_current`` for standalone view tests."""
    user = MagicMock()
    user.getId.return_value = "admin"
    return patch("plone.api.user.get_current", return_value=user)


def _make_view(context=None, request=None, context_attributes=None):
    view = Views.__new__(Views)
    view.context = context if context is not None else MagicMock()
    if context is None:
        view.context.absolute_url.return_value = SURVEY_URL
        view.context.getId.return_value = "survey"
    for key, value in (context_attributes or {}).items():
        setattr(view.context, key, value)
    view.request = request if request is not None else _Request(method="GET")
    return view


def _survey_annotations(form_json=None):
    """Return an annotations dict holding one stored form version."""
    annos = {}
    annos[FORM_VERSIONS_KEY] = OOBTree()
    annos[FORM_VERSIONS_KEY]["v1"] = {
        "id": "v1",
        "created": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "user": "admin",
        "form_json": SURVEY_FORM_JSON if form_json is None else form_json,
    }
    return annos


# --------------------------------------------------------------------------
# module level helpers
# --------------------------------------------------------------------------


class ExternalValidationEdgeTests(unittest.TestCase):
    def test_unparsable_result_file_is_ignored(self) -> None:
        def fake_run(*, schema_json, form_json, result_json):
            Path(result_json).write_bytes(b"not json at all")
            return 0

        with patch.object(views_module, "run_data_validation", side_effect=fake_run):
            result = _run_external_validation({"pages": []}, {"a": 1}, "hash-x")

        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "external_validation_ok")
        self.assertEqual(result["details"], {})

    def test_nonzero_exit_with_valid_result_is_reported_as_error(self) -> None:
        def fake_run(*, schema_json, form_json, result_json):
            Path(result_json).write_bytes(orjson.dumps({"valid": True}))
            return 3

        with patch.object(views_module, "run_data_validation", side_effect=fake_run):
            result = _run_external_validation({"pages": []}, {"a": 1}, "hash-y")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], 500)
        self.assertEqual(result["reason"], "external_validator_error")


class RootRedirectTests(unittest.TestCase):
    def test_redirects_to_language_root_when_present(self) -> None:
        context = MagicMock()
        target = MagicMock()
        target.absolute_url.return_value = "http://nohost/en"
        context.get.return_value = target
        view = RootRedirect.__new__(RootRedirect)
        view.context = context
        view.request = _Request()

        view()

        self.assertEqual(view.request.response.redirected, "http://nohost/en")

    def test_redirects_to_context_root_without_language_folder(self) -> None:
        context = MagicMock()
        context.get.return_value = None
        context.absolute_url.return_value = SURVEY_URL
        view = RootRedirect.__new__(RootRedirect)
        view.context = context
        view.request = _Request()

        view()

        self.assertEqual(view.request.response.redirected, SURVEY_URL)


# --------------------------------------------------------------------------
# properties and small helpers
# --------------------------------------------------------------------------


class ViewsPropertyTests(unittest.TestCase):
    def test_survey_theme_json_without_site(self) -> None:
        view = _make_view()
        view.context.theme = None
        with patch("zope.component.hooks.getSite", return_value=None):
            self.assertEqual(view.survey_theme_json, {})

    def test_survey_theme_json_falls_back_to_default_theme(self) -> None:
        view = _make_view()
        view.context.theme = None
        with (
            patch("zope.component.hooks.getSite", return_value=MagicMock()),
            patch(
                "zope.annotation.interfaces.IAnnotations",
                return_value={"themes": {}},
            ),
            patch(
                "zopyx.surveyjs.browser.services.themes.get_default_theme_id",
                return_value="default-theme",
            ) as default_id,
            patch(
                "zopyx.surveyjs.browser.services.themes.get_theme",
                return_value={"theme_json": {"color": "red"}},
            ) as get_theme,
        ):
            self.assertEqual(view.survey_theme_json, {"color": "red"})
        default_id.assert_called_once()
        self.assertEqual(get_theme.call_args.args[1], "default-theme")

    def test_survey_theme_json_returns_empty_on_error(self) -> None:
        view = _make_view()
        view.context.theme = "configured"
        with (
            patch("zope.component.hooks.getSite", return_value=MagicMock()),
            patch(
                "zope.annotation.interfaces.IAnnotations",
                side_effect=RuntimeError("annotations unavailable"),
            ),
        ):
            self.assertEqual(view.survey_theme_json, {})

    def test_survey_language_labels_skips_valueless_terms(self) -> None:
        view = _make_view()
        terms = [
            SimpleNamespace(value="de", title="Deutsch"),
            SimpleNamespace(value="", title="Ignored"),
            SimpleNamespace(value="fr"),
        ]
        with patch("zopyx.surveyjs.content.survey.survey_languages_vocabulary", terms):
            labels = view.survey_language_labels
        self.assertEqual(labels, {"de": "Deutsch", "fr": "fr"})

    def test_can_add_survey_delegates_to_permission(self) -> None:
        view = _make_view()
        with patch("plone.api.user.has_permission", return_value=True) as check:
            self.assertTrue(view.can_add_survey)
        self.assertEqual(check.call_args.kwargs["obj"], view.context)

    def test_storage_info_for_zodb_and_rdbms(self) -> None:
        view = _make_view()
        with patch.object(views_module, "_get_storage_location", return_value="zodb"):
            self.assertEqual(view.storage_info, "Plone (ZODB)")
        with patch.object(
            views_module,
            "_get_storage_location",
            return_value="postgresql://user:secret@db/forms",
        ):
            info = view.storage_info
        self.assertTrue(info.startswith("Relational database: postgresql://user:"))
        self.assertNotIn("secret", info)

    def test_plone_api_and_actions_properties(self) -> None:
        view = _make_view()
        self.assertIs(view.plone_api, plone.api)

        mailed = _make_view(
            context_attributes={"actions": {"mail"}, "post_endpoint_url": ""}
        )
        self.assertTrue(mailed.has_mail_action)
        self.assertFalse(mailed.has_post_action)
        self.assertFalse(mailed.storing_enabled)

        posted = _make_view(
            context_attributes={"actions": {"post"}, "post_endpoint_url": "https://x/y"}
        )
        self.assertFalse(posted.has_mail_action)
        self.assertTrue(posted.has_post_action)
        self.assertTrue(posted.storing_enabled is False)

        storing = _make_view(context_attributes={"actions": {"store"}})
        self.assertTrue(storing.storing_enabled)

    def test_embedding_modes(self) -> None:
        iframe = _make_view(context_attributes={"embedding_mode": "iframe"})
        self.assertTrue(iframe.embedding_allowed)
        self.assertFalse(iframe.direct_embedding_allowed)

        direct = _make_view(context_attributes={"embedding_mode": "direct"})
        self.assertFalse(direct.embedding_allowed)
        self.assertTrue(direct.direct_embedding_allowed)
        self.assertEqual(
            direct.embed_direct_demo_url, f"{SURVEY_URL}/@@embed-direct-demo"
        )

    def test_survey_results_count_handles_storage_errors(self) -> None:
        view = _make_view()
        storage = MagicMock()
        storage.list_results.return_value = [{"poll_id": "a"}, {"poll_id": "b"}]
        with patch.object(views_module, "get_result_storage", return_value=storage):
            self.assertEqual(view.survey_results_count(), 2)
            storage.list_results.assert_called_with(view.context)
        with patch.object(
            views_module, "get_result_storage", side_effect=RuntimeError("no storage")
        ):
            self.assertEqual(view.survey_results_count(), 0)

    def test_status_and_effective_display_helpers(self) -> None:
        view = _make_view(context_attributes={"effective": None, "expires": None})
        with patch("plone.api.content.get_state", return_value="published"):
            self.assertEqual(str(view.survey_status_label()), "Published")
        with patch("plone.api.content.get_state", side_effect=RuntimeError("gone")):
            self.assertEqual(str(view.survey_status_label()), "Inactive")
        self.assertIsNone(view.survey_effective_display())
        self.assertIsNone(view.survey_expires_display())

    def test_status_label_reports_inactive_for_drafts(self) -> None:
        view = _make_view()
        with patch("plone.api.content.get_state", return_value="private"):
            self.assertEqual(str(view.survey_status_label()), "Inactive")

    def test_form_settings_and_features(self) -> None:
        view = _make_view()
        with patch(
            "zope.component.getUtility", side_effect=RuntimeError("no registry")
        ):
            self.assertIsNone(view._get_forms_settings())

        with patch.object(view, "_get_forms_settings", return_value=None):
            self.assertEqual(view.features_enabled, set())
            self.assertEqual(view.surveyjs_license_key, "")
            self.assertFalse(view.feature_enabled("chatbot"))

        settings = SimpleNamespace(
            features_enabled=["chatbot", "monitor"],
            surveyjs_license_key="  abc-123  ",
        )
        with patch.object(view, "_get_forms_settings", return_value=settings):
            self.assertEqual(view.features_enabled, {"chatbot", "monitor"})
            self.assertTrue(view.feature_enabled("chatbot"))
            self.assertEqual(view.surveyjs_license_key, "abc-123")

    def test_require_feature_redirects_when_disabled(self) -> None:
        view = _make_view()
        with patch.object(
            type(view),
            "features_enabled",
            new_callable=PropertyMock,
            return_value={"x"},
        ):
            self.assertTrue(view.require_feature("x"))
            self.assertIsNone(view.request.response.redirected)

        with patch.object(
            type(view),
            "features_enabled",
            new_callable=PropertyMock,
            return_value=set(),
        ):
            self.assertFalse(view.require_feature("x"))
        self.assertEqual(
            view.request.response.redirected, f"{SURVEY_URL}/@@feature-disabled"
        )


class ViewsAuthDelegationTests(unittest.TestCase):
    def test_require_trusted_access_short_circuits_for_managers(self) -> None:
        view = _make_view()
        with patch.object(
            type(view),
            "can_manage_portal_content",
            new_callable=PropertyMock,
            return_value=True,
        ):
            auth = MagicMock()
            with patch.object(view, "_auth", return_value=auth):
                self.assertTrue(view._require_trusted_access())
        auth.require_trusted_access.assert_not_called()

    def test_require_trusted_access_delegates_to_auth_service(self) -> None:
        view = _make_view()
        auth = MagicMock()
        auth.require_trusted_access.return_value = False
        with (
            patch.object(
                type(view),
                "can_manage_portal_content",
                new_callable=PropertyMock,
                return_value=False,
            ),
            patch.object(view, "_auth", return_value=auth),
        ):
            self.assertFalse(view._require_trusted_access())
        self.assertIs(
            auth.require_trusted_access.call_args.kwargs["logger"], views_module.logger
        )

    def test_consume_trusted_access_token_paths(self) -> None:
        view = _make_view()
        with patch.object(
            type(view),
            "can_manage_portal_content",
            new_callable=PropertyMock,
            return_value=True,
        ):
            auth = MagicMock()
            with patch.object(view, "_auth", return_value=auth):
                self.assertTrue(view._consume_trusted_access_token())
        auth.consume_trusted_access_token.assert_not_called()

        view = _make_view()
        auth = MagicMock()
        auth.consume_trusted_access_token.return_value = False
        with (
            patch.object(
                type(view),
                "can_manage_portal_content",
                new_callable=PropertyMock,
                return_value=False,
            ),
            patch.object(view, "_auth", return_value=auth),
        ):
            self.assertFalse(view._consume_trusted_access_token())
        auth.consume_trusted_access_token.assert_called_once()

    def test_trusted_access_token_reports_unavailable_cache(self) -> None:
        view = _make_view()
        auth = MagicMock()
        auth.issue_trusted_access_token.return_value = ("", None)
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value={}),
            patch.object(view, "_latest_form_version_id", return_value="v1"),
            patch.object(view, "_auth", return_value=auth),
        ):
            view.trusted_access_token()

        self.assertEqual(view.request.response.status, 503)
        body = view.request.response.json()
        self.assertEqual(body["error"], "trusted_access_cache_unavailable")
        auth.issue_trusted_access_token.assert_called_once_with("v1")

    def test_trusted_access_token_returns_url(self) -> None:
        view = _make_view()
        auth = MagicMock()
        auth.issue_trusted_access_token.return_value = (
            "tok-1",
            {"expires_at": "2030-01-01T00:00:00+00:00"},
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value={}),
            patch.object(view, "_latest_form_version_id", return_value="v1"),
            patch.object(view, "_auth", return_value=auth),
        ):
            view.trusted_access_token()

        self.assertEqual(view.request.response.status, 200)
        body = view.request.response.json()
        self.assertTrue(body["isSuccess"])
        self.assertEqual(body["token"], "tok-1")
        self.assertEqual(body["url"], f"{SURVEY_URL}/@@viewer?access_token=tok-1")
        self.assertEqual(body["expires_at"], "2030-01-01T00:00:00+00:00")


class ViewsSmallHelperTests(unittest.TestCase):
    def test_format_portal_time_variants(self) -> None:
        view = _make_view()
        with patch(
            "plone.api.portal.get_localized_time", return_value="Jan 1, 2024"
        ) as localize:
            self.assertEqual(view._format_portal_time("2024-01-01"), "Jan 1, 2024")
        self.assertEqual(localize.call_args.kwargs, {"long_format": True})
        with patch(
            "plone.api.portal.get_localized_time", side_effect=RuntimeError("boom")
        ):
            self.assertEqual(view._format_portal_time("2024-01-01"), "2024-01-01")
        self.assertIsNone(view._format_portal_time(None))

    def test_extract_year_variants(self) -> None:
        view = _make_view()
        self.assertIsNone(view._extract_year(_ExplodingAttribute()))

        no_year = MagicMock()
        no_year.year = None
        self.assertIsNone(view._extract_year(no_year))

        numeric = MagicMock()
        numeric.year = "2024"
        self.assertEqual(view._extract_year(numeric), 2024)

        broken = MagicMock()
        broken.year = "twenty"
        self.assertIsNone(view._extract_year(broken))

        callable_ok = MagicMock()
        callable_ok.year = lambda: "2025"
        self.assertEqual(view._extract_year(callable_ok), 2025)

        callable_bad = MagicMock()
        callable_bad.year = lambda: "nope"
        self.assertIsNone(view._extract_year(callable_bad))

    def test_is_reasonable_date(self) -> None:
        view = _make_view()
        self.assertTrue(view._is_reasonable_date(_ExplodingAttribute()))
        good = MagicMock()
        good.year = 2024
        self.assertTrue(view._is_reasonable_date(good))
        ancient = MagicMock()
        ancient.year = 1500
        self.assertFalse(view._is_reasonable_date(ancient))

    def test_parse_download_date_variants(self) -> None:
        view = _make_view()
        self.assertIsNone(view._parse_download_date(None))
        self.assertIsNone(view._parse_download_date("   "))

        start = view._parse_download_date("2024-01-02")
        self.assertEqual(start.tzinfo, timezone.utc)
        self.assertEqual((start.hour, start.minute), (0, 0))
        self.assertEqual(start.date().isoformat(), "2024-01-02")

        end = view._parse_download_date("2024-01-02", is_end=True)
        self.assertEqual(end, start + timedelta(days=1))

        zulu = view._parse_download_date("2024-01-02T10:30:00Z")
        self.assertEqual(zulu.tzinfo, timezone.utc)
        self.assertEqual((zulu.hour, zulu.minute), (10, 30))

        offset = view._parse_download_date("2024-01-02T10:30:00+02:00")
        self.assertIsNotNone(offset.tzinfo)
        self.assertEqual(offset.utcoffset(), timedelta(hours=2))

        self.assertIsNone(view._parse_download_date("not-a-date"))

    def test_filter_results_by_date(self) -> None:
        view = _make_view()
        view.request = _Request(method="GET")
        view.request.form = {"from": "2024-01-01", "to": "2024-02-01"}
        results = [
            {"poll_id": "in-range", "created": "2024-01-15T10:00:00Z"},
            {
                "poll_id": "too-late",
                "created": datetime(2024, 3, 1, tzinfo=timezone.utc),
            },
            {"poll_id": "no-date", "created": None},
            {"poll_id": "numeric-date", "created": 20240101},
            {"poll_id": "missing-date"},
            {
                "poll_id": "too-early",
                "created": datetime(2023, 12, 31, tzinfo=timezone.utc),
            },
            {"poll_id": "naive", "created": datetime(2024, 1, 20, 12, 0)},
        ]
        with patch.object(views_module, "logger") as logger:
            filtered = view._filter_results_by_date(results)

        self.assertEqual(
            [entry["poll_id"] for entry in filtered], ["in-range", "naive"]
        )
        self.assertEqual(
            logger.info.call_args.args[0],
            "Applying export filter (from=%s, to=%s) for %s",
        )

        view.request.form = {"from": "2024-01-01"}
        self.assertEqual(
            [entry["poll_id"] for entry in view._filter_results_by_date(results)],
            ["in-range", "too-late", "naive"],
        )

        view.request.form = {}
        self.assertEqual(view._filter_results_by_date(results), results)

    def test_ensure_private_transitions(self) -> None:
        view = _make_view()
        with patch(
            "plone.api.content.get_state", side_effect=RuntimeError("no workflow")
        ):
            self.assertFalse(view._ensure_private(MagicMock()))

        with patch("plone.api.content.get_state", return_value="private"):
            self.assertTrue(view._ensure_private(MagicMock()))

        # plone.api 3.0 has no ``get_transitions``; the AttributeError is
        # swallowed and the object stays published.
        with patch("plone.api.content.get_state", return_value="published"):
            self.assertFalse(view._ensure_private(MagicMock()))

        with (
            patch("plone.api.content.get_state", return_value="published"),
            patch(
                "plone.api.content.get_transitions",
                create=True,
                return_value=[{"id": "retract"}, {"id": None}],
            ),
            patch("plone.api.content.transition") as transition,
        ):
            self.assertTrue(view._ensure_private(MagicMock()))
        self.assertEqual(transition.call_args.kwargs["transition"], "retract")

        with (
            patch("plone.api.content.get_state", return_value="published"),
            patch(
                "plone.api.content.get_transitions",
                create=True,
                side_effect=RuntimeError("no transitions"),
            ),
        ):
            self.assertFalse(view._ensure_private(MagicMock()))

        obj = MagicMock()
        with (
            patch("plone.api.content.get_state", return_value="published"),
            patch(
                "plone.api.content.get_transitions",
                create=True,
                return_value=[{"id": "hide"}],
            ),
            patch(
                "plone.api.content.transition",
                side_effect=RuntimeError("transition denied"),
            ),
        ):
            self.assertFalse(view._ensure_private(obj))

    def test_format_catalog_date_and_iso(self) -> None:
        view = _make_view()
        with patch(
            "plone.api.portal.get_localized_time", return_value="Jan 2, 2024 10:30"
        ):
            self.assertEqual(
                view._format_catalog_date(lambda: "2024-01-02"),
                "Jan 2, 2024 10:30",
            )
        self.assertEqual(view._format_catalog_date(datetime(1500, 1, 1)), "")
        self.assertEqual(view._format_catalog_date(None), "")

        self.assertEqual(
            view._format_catalog_iso(_IsoObject("2024-01-02T10:30:00")),
            "2024-01-02 10:30",
        )
        self.assertEqual(
            view._format_catalog_iso(lambda: datetime(2024, 1, 2, 10, 30)),
            "2024-01-02 10:30",
        )
        self.assertEqual(
            view._format_catalog_iso(datetime(2024, 1, 2, 10, 30, 15)),
            "2024-01-02 10:30",
        )
        bad = _BadIsoformat()
        self.assertEqual(view._format_catalog_iso(bad), str(bad))
        self.assertEqual(view._format_catalog_iso(None), "")
        self.assertEqual(view._format_catalog_iso("not-a-date"), "not-a-date")
        self.assertEqual(view._format_catalog_iso(datetime(1500, 1, 1)), "")

    def test_translate_label_variants(self) -> None:
        view = _make_view()
        self.assertEqual(view._translate_label(""), "")
        with patch.object(views_module, "translate", return_value="Übersetzt") as tr:
            self.assertEqual(view._translate_label("Translated"), "Übersetzt")
        self.assertEqual(tr.call_args.kwargs["context"], view.request)
        with patch.object(
            views_module, "translate", side_effect=RuntimeError("no translator")
        ):
            self.assertEqual(view._translate_label("Fallback"), "Fallback")

    def test_vocabulary_title_variants(self) -> None:
        view = _make_view()
        self.assertEqual(view._vocabulary_title(None, 4), "4")

        named = SimpleNamespace(vocabulary=None, vocabularyName="zopyx.surveyjs.vocab")
        with patch.object(
            views_module, "getUtility", side_effect=RuntimeError("unknown vocabulary")
        ):
            self.assertEqual(view._vocabulary_title(named, "x"), "x")

        no_name = SimpleNamespace(vocabulary=None, vocabularyName=None)
        self.assertEqual(view._vocabulary_title(no_name, "y"), "y")

        vocab = MagicMock()
        vocab.getTerm.return_value = SimpleNamespace(title="Titel")
        with patch.object(views_module, "translate", return_value="Titel"):
            self.assertEqual(
                view._vocabulary_title(SimpleNamespace(vocabulary=vocab), "de"),
                "Titel",
            )
        vocab.getTerm.assert_called_once_with("de")

        empty_vocab = MagicMock()
        empty_vocab.getTerm.return_value = None
        with patch.object(views_module, "translate", side_effect=lambda v, **k: str(v)):
            self.assertEqual(
                view._vocabulary_title(SimpleNamespace(vocabulary=empty_vocab), "en"),
                "en",
            )

        broken_vocab = MagicMock()
        broken_vocab.getTerm.side_effect = LookupError("unknown term")
        self.assertEqual(
            view._vocabulary_title(SimpleNamespace(vocabulary=broken_vocab), "xx"),
            "xx",
        )

    def test_vocabulary_title_resolves_named_factory(self) -> None:
        view = _make_view()
        vocab = MagicMock()
        vocab.getTerm.return_value = SimpleNamespace(title="Titel")
        field = SimpleNamespace(vocabulary=None, vocabularyName="some.vocabulary")
        with (
            patch.object(views_module, "getUtility", return_value=lambda ctx: vocab),
            patch.object(views_module, "translate", return_value="Titel"),
        ):
            self.assertEqual(view._vocabulary_title(field, "de"), "Titel")

    def test_field_value_text_variants(self) -> None:
        view = _make_view()
        field = MagicMock()
        self.assertEqual(
            view._survey_field_value_text(SimpleNamespace(), "x", field), ""
        )

        raising = SimpleNamespace(value=lambda: 1 / 0)
        self.assertEqual(view._survey_field_value_text(raising, "value", field), "")

        self.assertEqual(
            view._survey_field_value_text(SimpleNamespace(value=None), "value", field),
            "",
        )

        with (
            patch.object(views_module.ICollection, "providedBy", return_value=True),
            patch.object(views_module.IChoice, "providedBy", return_value=False),
            patch.object(view, "_vocabulary_title", side_effect=lambda f, v: str(v)),
        ):
            empty = SimpleNamespace(value=[])
            self.assertEqual(view._survey_field_value_text(empty, "value", field), "")
            as_set = SimpleNamespace(value={"b", "a", "a"})
            self.assertEqual(
                view._survey_field_value_text(as_set, "value", field), "a, b"
            )
            mixed = SimpleNamespace(value=["x", None, 0, ""])
            self.assertEqual(
                view._survey_field_value_text(mixed, "value", field), "x, 0"
            )

        with (
            patch.object(views_module.ICollection, "providedBy", return_value=False),
            patch.object(views_module.IChoice, "providedBy", return_value=True),
            patch.object(view, "_vocabulary_title", return_value="Choice") as vt,
        ):
            choice = SimpleNamespace(value="a")
            self.assertEqual(
                view._survey_field_value_text(choice, "value", field), "Choice"
            )
        self.assertEqual(vt.call_args.args[0], field)

        with (
            patch.object(views_module.ICollection, "providedBy", return_value=False),
            patch.object(views_module.IChoice, "providedBy", return_value=False),
        ):
            sequence = SimpleNamespace(value=("a", "", 0, "b"))
            self.assertEqual(
                view._survey_field_value_text(sequence, "value", field), "a, 0, b"
            )
            scalar = SimpleNamespace(value=42)
            self.assertEqual(
                view._survey_field_value_text(scalar, "value", field), "42"
            )

    def test_form_id_fallbacks(self) -> None:
        view = _make_view(context=SimpleNamespace(id="raw-id"))
        self.assertEqual(view._form_id(), "raw-id")

        view = _make_view(context=SimpleNamespace(UID=lambda: "uid-1"))
        self.assertEqual(view._form_id(), "uid-1")

        view = _make_view(context=SimpleNamespace())
        self.assertEqual(view._form_id(), "")

    def test_interpolate_text_without_template(self) -> None:
        view = _make_view()
        self.assertEqual(view._interpolate_text("", {"a": 1}), "")
        self.assertIsNone(view._interpolate_text(None, {"a": 1}))

    def test_embedded_demo_iframe_url(self) -> None:
        portal = MagicMock()
        portal.absolute_url.return_value = "http://nohost/plone"
        view = EmbeddedDemoView.__new__(EmbeddedDemoView)
        with patch("plone.api.portal.get", return_value=portal):
            self.assertEqual(
                view.iframe_url,
                "http://nohost/plone/de/demos/mental-health-survey-de/@@viewer-embed",
            )


# --------------------------------------------------------------------------
# JSON / download views
# --------------------------------------------------------------------------


class ViewsJSONTests(unittest.TestCase):
    def test_get_form_json_denied_without_trusted_access(self) -> None:
        view = _make_view(request=_Request(method="GET"))
        with patch.object(view, "_require_trusted_access", return_value=False):
            self.assertIsNone(view.get_form_json())
        self.assertEqual(view.request.response.written, b"")

    def test_get_form_json_returns_latest_version(self) -> None:
        view = _make_view(request=_Request(method="GET"))
        annos = _survey_annotations()
        with (
            patch.object(view, "_require_trusted_access", return_value=True),
            patch.object(views_module, "IAnnotations", return_value=annos),
        ):
            view.get_form_json()
        self.assertEqual(view.request.response.json(), SURVEY_FORM_JSON)

    def test_save_form_json_permission_denied(self) -> None:
        view = _make_view(request=_Request(method="POST"))
        with patch("plone.api.user.has_permission", return_value=False):
            view.save_form_json()
        self.assertEqual(view.request.response.status, 403)
        self.assertEqual(view.request.response.json()["error"], "permission_denied")

    def test_save_form_json_rejects_non_post(self) -> None:
        view = _make_view(request=_Request(method="GET"))
        with patch("plone.api.user.has_permission", return_value=True):
            view.save_form_json()
        self.assertEqual(view.request.response.status, 405)
        self.assertEqual(view.request.response.json()["error"], "method_not_allowed")

    def test_save_form_json_stores_and_audits(self) -> None:
        request = _Request(
            form={"surveyText": orjson.dumps(SURVEY_FORM_JSON).decode()},
            method="POST",
        )
        view = _make_view(request=request)
        annos = {}
        current_user = MagicMock()
        current_user.getId.return_value = "admin"
        with (
            patch("plone.api.user.has_permission", return_value=True),
            patch.object(views_module, "CheckAuthenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch("plone.api.user.get_current", return_value=current_user),
            patch.object(views_module, "audit_form_version_change") as audit,
        ):
            view.save_form_json()

        self.assertEqual(request.response.json(), {"isSuccess": True})
        versions = form_versions(annos)
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["form_json"], SURVEY_FORM_JSON)
        self.assertEqual(audit.call_args.kwargs["source"], "editor")
        self.assertIsNone(audit.call_args.kwargs["previous_version_id"])

    def test_clear_results_wipes_storage_and_redirects(self) -> None:
        view = _make_view(request=_Request(method="POST"))
        storage = MagicMock()
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "get_result_storage", return_value=storage),
            patch("plone.api.portal.show_message") as show_message,
        ):
            view.clear_results()

        storage.clear_results.assert_called_once_with(view.context)
        self.assertEqual(show_message.call_args.args[0], "Results cleared")
        self.assertEqual(view.request.response.redirected, f"{SURVEY_URL}/view")

    def test_get_polls_json2_returns_result_payloads(self) -> None:
        view = _make_view(request=_Request(method="GET"))
        storage = MagicMock()
        storage.list_results.return_value = [
            {"poll_id": "p1", "result": {"q1": "a"}},
            {"poll_id": "p2", "result": {"q1": "b"}},
            {"poll_id": "p3"},
        ]
        with patch.object(views_module, "get_result_storage", return_value=storage):
            view.get_polls_json2()
        self.assertEqual(view.request.response.json(), [{"q1": "a"}, {"q1": "b"}, None])

    def test_download_form_json_writes_attachment(self) -> None:
        view = _make_view(request=_Request(method="GET"))
        view.context.getId.return_value = "survey"
        annos = _survey_annotations()
        with patch.object(views_module, "IAnnotations", return_value=annos):
            view.download_form_json()

        response = view.request.response
        self.assertEqual(response.headers["Content-Type"], "application/json")
        self.assertEqual(
            response.headers["Content-Disposition"],
            'attachment; filename="survey-survey-form.json"',
        )
        self.assertEqual(response.json(), SURVEY_FORM_JSON)

    def test_download_form_json_uses_set_result_when_available(self) -> None:
        request = _Request(method="GET")
        request.response = _ResultResponse()
        view = _make_view(request=request)
        view.context.getId.return_value = "survey"
        with patch.object(
            views_module, "IAnnotations", return_value=_survey_annotations()
        ):
            view.download_form_json()
        self.assertEqual(len(request.response.results), 1)
        self.assertEqual(orjson.loads(request.response.results[0]), SURVEY_FORM_JSON)

    def test_download_form_json_without_versions(self) -> None:
        view = _make_view(request=_Request(method="GET"))
        view.context.getId.return_value = "survey"
        with patch.object(views_module, "IAnnotations", return_value={}):
            view.download_form_json()
        self.assertEqual(view.request.response.json(), {})

    def test_download_polls_csv_serializes_mixed_values(self) -> None:
        view = _make_view(request=_Request(method="GET"))
        storage = MagicMock()
        storage.list_results.return_value = [
            {
                "poll_id": "p1",
                "user": "alice",
                "created": datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
                "form_version": "v1",
                "result": {
                    "q1": "a",
                    "q2": {"nested": 1},
                    "q3": None,
                    "q4": {1: 2},
                    "q5": ["x", "y"],
                },
            },
            {
                "poll_id": "p2",
                "created": None,
                "result": {"q1": "b"},
            },
        ]
        with patch.object(views_module, "get_result_storage", return_value=storage):
            view.download_polls_csv()

        response = view.request.response
        self.assertEqual(response.headers["Content-Type"], "text/csv")
        self.assertEqual(
            response.headers["Content-Disposition"],
            'attachment; filename="survey-survey-data.csv"',
        )
        rows = list(csv.reader(io.StringIO(response.written.decode("utf-8"))))
        header = rows[0]
        self.assertEqual(header[:4], ["poll_id", "user", "created", "form_version"])
        self.assertEqual(set(header[4:]), {"q1", "q2", "q3", "q4", "q5"})

        first = dict(zip(header, rows[1]))
        self.assertEqual(first["q1"], "a")
        self.assertEqual(orjson.loads(first["q2"]), {"nested": 1})
        self.assertEqual(first["q3"], "")
        self.assertEqual(first["q4"], "{1: 2}")
        self.assertEqual(orjson.loads(first["q5"]), ["x", "y"])
        self.assertEqual(first["created"], "2024-01-15T10:30:00+00:00")

        second = dict(zip(header, rows[2]))
        self.assertEqual(second["poll_id"], "p2")
        self.assertEqual(second["created"], "")

    def test_download_polls_csv_uses_set_result_when_available(self) -> None:
        request = _Request(method="GET")
        request.response = _ResultResponse()
        view = _make_view(request=request)
        storage = MagicMock()
        storage.list_results.return_value = [
            {"poll_id": "p1", "created": None, "result": {"q1": "a"}}
        ]
        with patch.object(views_module, "get_result_storage", return_value=storage):
            view.download_polls_csv()
        self.assertEqual(len(request.response.results), 1)
        self.assertIn(b"p1", request.response.results[0])

    def test_download_polls_json_writes_attachment(self) -> None:
        view = _make_view(request=_Request(method="GET"))
        storage = MagicMock()
        storage.list_results.return_value = [
            {
                "poll_id": "p1",
                "created": datetime(2024, 1, 15, tzinfo=timezone.utc),
                "result": {"q1": "a"},
            }
        ]
        with patch.object(views_module, "get_result_storage", return_value=storage):
            view.download_polls_json()

        response = view.request.response
        self.assertEqual(response.headers["Content-Type"], "application/json")
        self.assertEqual(
            response.headers["Content-Disposition"],
            'attachment; filename="survey-survey-data.json"',
        )
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["poll_id"], "p1")

    def test_download_polls_json_uses_set_result_when_available(self) -> None:
        request = _Request(method="GET")
        request.response = _ResultResponse()
        view = _make_view(request=request)
        storage = MagicMock()
        storage.list_results.return_value = [{"poll_id": "p1", "result": {"q1": "a"}}]
        with patch.object(views_module, "get_result_storage", return_value=storage):
            view.download_polls_json()
        self.assertEqual(len(request.response.results), 1)
        self.assertEqual(orjson.loads(request.response.results[0])[0]["poll_id"], "p1")


def form_versions(annos):
    return list(annos[FORM_VERSIONS_KEY].values())


# --------------------------------------------------------------------------
# save_poll
# --------------------------------------------------------------------------


class SavePollGuardTests(unittest.TestCase):
    def _view(self, form=None, method="POST", headers=None, annos=None, **attrs):
        request = _Request(form=form, method=method, headers=headers)
        context = MagicMock()
        context.absolute_url.return_value = SURVEY_URL
        context.actions = set(attrs.pop("actions", ("store",)))
        context.embed_direct_origins = []
        context.max_payload_size_mb = attrs.pop("max_payload_size_mb", 1)
        context.force_server_side_validation = attrs.pop(
            "force_server_side_validation", False
        )
        for key, value in attrs.items():
            setattr(context, key, value)
        view = _make_view(context=context, request=request)
        return view, request, (annos if annos is not None else _survey_annotations())

    def test_invalid_max_payload_setting_falls_back_to_one_megabyte(self) -> None:
        view, request, _ = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})},
            max_payload_size_mb="not-a-number",
            annos={},
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "CheckAuthenticator"),
            patch.object(views_module, "IAnnotations", return_value={}),
            patch.object(view, "_require_trusted_access", return_value=True),
            patch.object(view, "_require_auth_token", return_value=True),
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 400)
        self.assertEqual(request.response.json()["error"], "missing_form_schema")

    def test_non_numeric_content_length_is_ignored(self) -> None:
        view, request, annos = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})},
            headers={"Content-Length": "not-a-number"},
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify"),
            patch.object(views_module, "record_submission_duration"),
            patch.object(view, "_require_trusted_access", return_value=True),
            patch.object(view, "_require_auth_token", return_value=True),
            patch.object(view, "_consume_trusted_access_token", return_value=True),
            _patch_current_user(),
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 200)
        self.assertTrue(request.response.json()["isSuccess"])

    def test_payload_without_content_length_over_limit(self) -> None:
        view, request, annos = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})},
            max_payload_size_mb=0.001,
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "CheckAuthenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(view, "_require_trusted_access", return_value=True),
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 413)
        self.assertEqual(request.response.json()["error"], "request_too_large")

    def test_body_larger_than_limit_reports_json_too_large(self) -> None:
        view, request, annos = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})},
            headers={"Content-Length": "0"},
            max_payload_size_mb=0.5,
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(view, "_require_trusted_access", return_value=True),
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 413)
        self.assertEqual(request.response.json()["error"], "json_too_large")

    def test_missing_form_schema_is_rejected(self) -> None:
        view, request, _ = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})}, annos={}
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value={}),
            patch.object(view, "_require_trusted_access", return_value=True),
            patch.object(view, "_require_auth_token", return_value=True),
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 400)
        self.assertEqual(request.response.json()["error"], "missing_form_schema")

    def test_trusted_access_denied_stops_processing(self) -> None:
        view, request, annos = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})}
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify") as notify,
            patch.object(view, "_require_trusted_access", return_value=False),
        ):
            view.save_poll()

        notify.assert_not_called()
        self.assertEqual(request.response.status, None)
        self.assertEqual(request.response.written, b"")

    def test_auth_token_missing_stops_processing(self) -> None:
        view, request, annos = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})}
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify") as notify,
            patch.object(view, "_require_trusted_access", return_value=True),
            patch.object(view, "_require_auth_token", return_value=False),
        ):
            view.save_poll()

        notify.assert_not_called()
        self.assertEqual(request.response.written, b"")

    def test_exhausted_trusted_token_aborts_before_notify(self) -> None:
        view, request, annos = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})}
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify") as notify,
            patch.object(views_module, "json_response") as response,
            patch.object(view, "_require_trusted_access", return_value=True),
            patch.object(view, "_require_auth_token", return_value=True),
            patch.object(view, "_consume_trusted_access_token", return_value=False),
        ):
            view.save_poll()

        notify.assert_not_called()
        response.assert_not_called()

    def test_successful_submission_is_reported(self) -> None:
        view, request, annos = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})}
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify") as notify,
            patch.object(views_module, "record_submission_duration") as record,
            patch.object(view, "_require_trusted_access", return_value=True),
            patch.object(view, "_require_auth_token", return_value=True),
            patch.object(view, "_consume_trusted_access_token", return_value=True),
            _patch_current_user(),
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 200)
        body = request.response.json()
        self.assertTrue(body["isSuccess"])
        self.assertNotIn("stored", body)
        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[0].form_data["result"], {"q1": "a"})
        self.assertEqual(record.call_args.args[0], view.context)
        self.assertIsInstance(record.call_args.args[1], float)

    def test_submission_without_store_action_reports_not_persisted(self) -> None:
        view, request, annos = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})}, actions=("mail",)
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify"),
            patch.object(views_module, "record_submission_duration"),
            patch.object(view, "_require_trusted_access", return_value=True),
            patch.object(view, "_require_auth_token", return_value=True),
            patch.object(view, "_consume_trusted_access_token", return_value=True),
            _patch_current_user(),
        ):
            view.save_poll()

        body = request.response.json()
        self.assertFalse(body["stored"])
        self.assertIn("not persisted", body["message"])

    def test_monitoring_failure_does_not_break_submission(self) -> None:
        view, request, annos = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})}
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify"),
            patch.object(views_module, "logger") as logger,
            patch.object(
                views_module,
                "record_submission_duration",
                side_effect=RuntimeError("cache down"),
            ),
            patch.object(view, "_require_trusted_access", return_value=True),
            patch.object(view, "_require_auth_token", return_value=True),
            patch.object(view, "_consume_trusted_access_token", return_value=True),
            _patch_current_user(),
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 200)
        logger.debug.assert_called_once()
        self.assertEqual(
            logger.debug.call_args.args[0], "Failed to record submission duration"
        )

    def test_external_validation_failure_is_returned_to_client(self) -> None:
        view, request, annos = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})},
            force_server_side_validation=True,
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify") as notify,
            patch.object(views_module, "record_submission_duration"),
            patch.object(
                views_module,
                "_run_external_validation",
                return_value={
                    "ok": False,
                    "status": 400,
                    "reason": "external_validation_failed",
                    "details": {"errors": ["bad"]},
                },
            ),
            patch.object(view, "_require_trusted_access", return_value=True),
            patch.object(view, "_require_auth_token", return_value=True),
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 400)
        body = request.response.json()
        self.assertFalse(body["isSuccess"])
        self.assertEqual(body["error"], "external_validation_failed")
        self.assertEqual(body["details"], {"errors": ["bad"]})
        notify.assert_not_called()

    def test_external_validation_failure_without_details(self) -> None:
        view, request, annos = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})},
            force_server_side_validation=True,
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify"),
            patch.object(views_module, "record_submission_duration"),
            patch.object(
                views_module,
                "_run_external_validation",
                return_value={
                    "ok": False,
                    "status": 503,
                    "reason": "external_validator_missing",
                },
            ),
            patch.object(view, "_require_trusted_access", return_value=True),
            patch.object(view, "_require_auth_token", return_value=True),
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 503)
        body = request.response.json()
        self.assertEqual(body["error"], "external_validator_missing")
        self.assertNotIn("details", body)

    def test_external_validation_success_continues(self) -> None:
        view, request, annos = self._view(
            form={"pollResult": orjson.dumps({"q1": "a"})},
            force_server_side_validation=True,
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify") as notify,
            patch.object(views_module, "record_submission_duration"),
            patch.object(
                views_module,
                "_run_external_validation",
                return_value={"ok": True, "status": 200, "reason": "ok"},
            ),
            patch.object(view, "_require_trusted_access", return_value=True),
            patch.object(view, "_require_auth_token", return_value=True),
            patch.object(view, "_consume_trusted_access_token", return_value=True),
            _patch_current_user(),
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 200)
        notify.assert_called_once()

    def test_validation_error_returns_field(self) -> None:
        view, request, annos = self._view(
            form={"pollResult": orjson.dumps({"q9": "a"})}
        )
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify") as notify,
            patch.object(view, "_require_trusted_access", return_value=True),
            patch.object(view, "_require_auth_token", return_value=True),
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 400)
        body = request.response.json()
        self.assertEqual(body["error"], "unknown_field")
        self.assertEqual(body["field"], "q9")
        self.assertFalse(body["isSuccess"])
        notify.assert_not_called()


class SavePollEmbedTests(unittest.TestCase):
    EMBED_HEADERS = {
        "Origin": "https://app.example",
        "X-Embed-Token": "token-value",
    }

    def _view(self, annos=None, form=None, **attrs):
        request = _Request(
            form=form
            if form is not None
            else {"pollResult": orjson.dumps({"q1": "a"})},
            method="POST",
            headers=self.EMBED_HEADERS,
            environ={"REMOTE_ADDR": "10.0.0.9"},
        )
        context = MagicMock()
        context.absolute_url.return_value = SURVEY_URL
        context.actions = {"store"}
        context.embed_direct_origins = ["https://app.example"]
        context.max_payload_size_mb = 1
        context.force_server_side_validation = False
        for key, value in attrs.items():
            setattr(context, key, value)
        view = _make_view(context=context, request=request)
        return view, request, (annos if annos is not None else _survey_annotations())

    def test_embed_direct_disabled_globally(self) -> None:
        view, request, annos = self._view()
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify"),
            patch.object(views_module, "record_submission_duration"),
            _patch_current_user(),
            patch.object(
                embed_security_module,
                "is_embed_direct_globally_enabled",
                return_value=False,
            ),
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 403)
        body = request.response.json()
        self.assertEqual(body["error"], "feature_disabled")
        self.assertEqual(
            body["message"], "Direct DOM embedding is not enabled globally"
        )

    def test_embed_invalid_origin_is_audited_and_rejected(self) -> None:
        view, request, annos = self._view()
        audit = MagicMock()
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify"),
            patch.object(views_module, "record_submission_duration"),
            patch.object(
                embed_security_module,
                "is_embed_direct_globally_enabled",
                return_value=True,
            ),
            patch.object(
                embed_security_module,
                "validate_origin",
                return_value=(False, None, "origin not allowed"),
            ),
            patch("logging.getLogger", return_value=audit),
            patch.object(embed_security_module, "set_cors_headers") as cors,
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 403)
        self.assertEqual(request.response.json()["error"], "invalid_origin")
        self.assertEqual(request.response.json()["message"], "origin not allowed")
        cors.assert_not_called()
        self.assertEqual(audit.info.call_args.args[0], "embed.submission.rejected")
        self.assertEqual(
            audit.info.call_args.kwargs["extra"]["reason"], "invalid_origin"
        )
        self.assertEqual(
            audit.info.call_args.kwargs["extra"]["remote_addr"], "10.0.0.9"
        )

    def test_embed_invalid_token_is_audited_and_rejected(self) -> None:
        view, request, annos = self._view()
        audit = MagicMock()
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify"),
            patch.object(views_module, "record_submission_duration"),
            patch.object(
                embed_security_module,
                "is_embed_direct_globally_enabled",
                return_value=True,
            ),
            patch.object(
                embed_security_module,
                "validate_origin",
                return_value=(True, "https://app.example", ""),
            ),
            patch.object(embed_security_module, "set_cors_headers") as cors,
            patch.object(
                embed_security_module,
                "validate_embed_token",
                side_effect=embed_security_module.TokenInvalidError("bad token"),
            ),
            patch("logging.getLogger", return_value=audit),
        ):
            view.save_poll()

        cors.assert_called_once()
        self.assertEqual(cors.call_args.args[1], "https://app.example")
        self.assertEqual(request.response.status, 403)
        self.assertEqual(request.response.json()["error"], "invalid_token")
        self.assertEqual(request.response.json()["message"], "bad token")
        self.assertEqual(
            audit.info.call_args.kwargs["extra"]["reason"], "invalid_token"
        )

    def test_embed_replayed_token_is_rejected(self) -> None:
        view, request, annos = self._view()
        audit = MagicMock()
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "notify"),
            patch.object(views_module, "record_submission_duration"),
            _patch_current_user(),
            patch.object(
                embed_security_module,
                "is_embed_direct_globally_enabled",
                return_value=True,
            ),
            patch.object(
                embed_security_module,
                "validate_origin",
                return_value=(True, "https://app.example", ""),
            ),
            patch.object(embed_security_module, "set_cors_headers"),
            patch.object(
                embed_security_module,
                "validate_embed_token",
                return_value={"jti": "jti-1"},
            ),
            patch.object(embed_security_module, "mark_token_used", return_value=False),
            patch("logging.getLogger", return_value=audit),
        ):
            view.save_poll()

        self.assertEqual(request.response.status, 403)
        body = request.response.json()
        self.assertEqual(body["error"], "token_already_used")
        self.assertEqual(body["message"], "Token already used")
        self.assertEqual(
            audit.info.call_args.kwargs["extra"]["reason"], "token_replayed"
        )

    def test_embed_accepted_submission_is_audited(self) -> None:
        view, request, annos = self._view()
        audit = MagicMock()
        with (
            patch.object(view, "_check_post_authenticator"),
            patch.object(views_module, "IAnnotations", return_value=annos),
            patch.object(views_module, "record_submission_duration"),
            patch.object(views_module, "notify") as notify,
            _patch_current_user(),
            patch.object(
                embed_security_module,
                "is_embed_direct_globally_enabled",
                return_value=True,
            ),
            patch.object(
                embed_security_module,
                "validate_origin",
                return_value=(True, "https://app.example", ""),
            ),
            patch.object(embed_security_module, "set_cors_headers"),
            patch.object(
                embed_security_module,
                "validate_embed_token",
                return_value={"jti": "jti-2"},
            ),
            patch.object(
                embed_security_module,
                "mark_token_used",
                return_value=True,
            ) as mark,
            patch("logging.getLogger", return_value=audit),
        ):
            view.save_poll()

        mark.assert_called_once_with("jti-2")
        self.assertEqual(request.response.status, 200)
        self.assertTrue(request.response.json()["isSuccess"])
        notify.assert_called_once()
        self.assertEqual(audit.info.call_args.args[0], "embed.submission.accepted")
        self.assertEqual(audit.info.call_args.kwargs["extra"]["jti"], "jti-2")
        self.assertEqual(
            audit.info.call_args.kwargs["extra"]["remote_addr"], "10.0.0.9"
        )


if __name__ == "__main__":
    unittest.main()
