# -*- coding: utf-8 -*-
"""Coverage tests for the survey add wizard and the survey metadata view.

The tests come in two flavours:

* ``*_FakeObjectTests`` drive the pure helper branches of
  ``SurveyAddView`` with hand written stand-in objects.
* ``*_IntegrationTests`` drive the real views (``__call__``,
  ``handle_submit``, ``_extract_form_data``) inside a Plone site so that
  creation/update of a ``Survey`` object is exercised for real.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import orjson
from plone import api
from plone.app.testing import logout, setRoles, TEST_USER_ID
from zope.annotation.interfaces import IAttributeAnnotatable
from zope.interface import alsoProvides
from zope.publisher.browser import TestRequest

from zopyx.surveyjs.browser.survey_add import SurveyAddView
from zopyx.surveyjs.browser.survey_metadata import SurveyMetadata
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING


class _BrowserRequest(TestRequest):
    """``TestRequest`` grown into the request API Plone relies on.

    ``zope.publisher``'s ``TestRequest`` is missing a few pieces the real
    publishing machinery provides: the login/theme viewlets need
    ``physicalPathToURL`` and ``SERVER_PORT``, and status messages need a
    request that is annotatable.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        alsoProvides(self, IAttributeAnnotatable)

    @property
    def SERVER_URL(self) -> str:
        return self.getURL()

    def physicalPathToURL(self, path) -> str:
        return "%s/%s" % (self.getURL(), "/".join(path))


def _request(form: dict | None = None, method: str = "GET") -> _BrowserRequest:
    """Build a browser request that knows its method and trusts ``nohost``."""
    return _BrowserRequest(
        environ={
            "SERVER_URL": "http://nohost",
            "SERVER_NAME": "nohost",
            "SERVER_PORT": "80",
            "HTTP_HOST": "nohost",
            "REQUEST_METHOD": method,
        },
        form=form or {},
    )


class _Isodate:
    """Object exposing the Zope ``ISO`` protocol."""

    def __init__(self, text: str) -> None:
        self._text = text

    def ISO(self) -> str:
        return self._text


class _IsodateRaises:
    """Object whose ``ISO`` call blows up."""

    def ISO(self) -> str:
        raise RuntimeError("ISO failed")

    def __str__(self) -> str:
        return "not-a-date"


class _IsoformatRaises:
    """Object whose ``isoformat`` call blows up."""

    def isoformat(self, *args, **kwargs) -> str:
        raise RuntimeError("isoformat failed")

    def __str__(self) -> str:
        return "not-a-date"


class _BadYear:
    """Object with a ``year`` attribute that cannot be coerced to int."""

    year = "not-a-year"

    def __str__(self) -> str:
        return "not-a-date"


class _PlainDatedYear:
    """Object that only carries a ``year`` attribute."""

    year = 2024

    def __str__(self) -> str:
        return "2024-11-12T13:14"


class _UndeletableDates:
    """Survey stand-in whose DublinCore values can neither be deleted nor set."""

    def __init__(self) -> None:
        self.effective = "2024-01-01T00:00"
        self.expires = "2024-12-31T00:00"
        self.setter_calls: list[tuple[str, str]] = []

    def __delattr__(self, name: str) -> None:
        raise AttributeError("attribute is locked")

    def setEffectiveDate(self, value) -> None:
        self.setter_calls.append(("effective", value))
        raise RuntimeError("setter failed")

    def setExpirationDate(self, value) -> None:
        self.setter_calls.append(("expires", value))
        raise RuntimeError("setter failed")


class SurveyAddViewFakeObjectTests(unittest.TestCase):
    """Helper level tests for ``SurveyAddView``."""

    def setUp(self) -> None:
        self.view = SurveyAddView.__new__(SurveyAddView)
        self.view.context = MagicMock()
        self.view.request = _request()
        self.view._errors = []
        self.view._form_values = {}

    def test_language_choices_skip_terms_without_value(self) -> None:
        terms = [
            MagicMock(value=""),
            MagicMock(value=None),
            MagicMock(value="en", title="English"),
            MagicMock(value="de", title=None),
        ]
        with patch("zopyx.surveyjs.content.survey.survey_languages_vocabulary", terms):
            choices = self.view._survey_languages_choices()

        self.assertEqual(
            choices,
            [
                {"value": "en", "text": "English"},
                {"value": "de", "text": "de"},
            ],
        )

    def test_language_choices_return_empty_when_vocabulary_is_unavailable(
        self,
    ) -> None:
        with patch.dict(sys.modules, {"zopyx.surveyjs.content.survey": None}):
            self.assertEqual(self.view._survey_languages_choices(), [])

    def test_theme_choices_return_empty_when_site_is_missing(self) -> None:
        # Outside of a Plone site ``getSite()`` yields ``None``.
        self.assertEqual(self.view._survey_themes_choices(), [])

    def test_build_create_kwargs_targets_the_current_context(self) -> None:
        kwargs = self.view._build_create_kwargs({"title": "T", "actions": ["store"]})

        self.assertEqual(kwargs["type"], "Survey")
        self.assertIs(kwargs["container"], self.view.context)
        self.assertEqual(kwargs["title"], "T")
        self.assertEqual(kwargs["actions"], {"store"})
        self.assertEqual(kwargs["max_payload_size_mb"], 1)

    def test_empty_inputs_collapse_to_empty_lists(self) -> None:
        self.assertEqual(self.view._ensure_list(""), [])
        self.assertEqual(self.view._split_lines(None), [])
        self.assertEqual(self.view._split_lines(""), [])

    def test_parse_datetime_value_handles_none_and_datetime_instances(self) -> None:
        self.assertIsNone(self.view._parse_datetime_value(None))

        naive = datetime(2024, 3, 4, 5, 6)
        self.assertEqual(
            self.view._parse_datetime_value(naive),
            datetime(2024, 3, 4, 5, 6, tzinfo=timezone.utc),
        )

        aware = datetime(2024, 3, 4, 5, 6, tzinfo=timezone.utc)
        self.assertIs(self.view._parse_datetime_value(aware), aware)

    def test_format_datetime_value_unwraps_callables(self) -> None:
        self.assertEqual(
            self.view._format_datetime_value(lambda: "2024-05-06T07:08"),
            "2024-05-06T07:08",
        )
        self.assertEqual(self.view._format_datetime_value(lambda: None), "")

    def test_format_datetime_value_drops_falsy_values(self) -> None:
        self.assertEqual(self.view._format_datetime_value(0), "")
        self.assertEqual(self.view._format_datetime_value(""), "")

    def test_format_datetime_value_prefers_the_iso_protocol(self) -> None:
        self.assertEqual(
            self.view._format_datetime_value(_Isodate("2024-07-08T09:10:11")),
            "2024-07-08T09:10",
        )

    def test_format_datetime_value_falls_back_when_isoformat_breaks(self) -> None:
        self.assertEqual(self.view._format_datetime_value(_IsoformatRaises()), "")

    def test_format_datetime_value_uses_str_for_plain_objects(self) -> None:
        self.assertEqual(
            self.view._format_datetime_value(_PlainDatedYear()), "2024-11-12T13:14"
        )

    def test_extract_datetime_year_falls_back_to_none_for_broken_values(self) -> None:
        self.assertIsNone(self.view._extract_datetime_year(_IsoformatRaises()))
        self.assertIsNone(self.view._extract_datetime_year(_IsodateRaises()))
        self.assertIsNone(self.view._extract_datetime_year(_BadYear()))

    def test_extract_datetime_year_reads_plain_year_attributes(self) -> None:
        self.assertEqual(self.view._extract_datetime_year(_PlainDatedYear()), 2024)

    def test_normalize_dublincore_dates_survives_locked_attributes(self) -> None:
        survey = _UndeletableDates()

        self.view._normalize_dublincore_dates(survey)

        self.assertEqual(survey.effective, "2024-01-01T00:00")
        self.assertEqual(survey.expires, "2024-12-31T00:00")
        self.assertEqual(
            [name for name, _value in survey.setter_calls], ["effective", "expires"]
        )


class SurveyAddViewIntegrationTests(unittest.TestCase):
    """Browser level tests for ``SurveyAddView.__call__`` and ``handle_submit``."""

    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.addCleanup(logout)

    def test_call_is_denied_for_anonymous_visitors(self) -> None:
        logout()
        view = SurveyAddView(self.portal, _request())

        self.assertFalse(view.can_add)
        result = view()

        self.assertEqual(view.request.response.getStatus(), 403)
        self.assertEqual(str(result), "You are not allowed to add surveys here.")

    def test_get_renders_the_add_wizard_with_initial_data(self) -> None:
        view = self.portal.restrictedTraverse("@@survey-add")

        self.assertTrue(view.can_add)
        html = view()

        self.assertIn('id="survey-add-initial-data"', html)
        self.assertIn('id="survey-add-submit"', html)
        self.assertIn("access_mode", html)
        self.assertNotIn("survey-add-errors", html)

    def test_post_creates_the_survey_and_redirects_to_the_editor(self) -> None:
        created: dict = {}
        real_create = api.content.create

        def _record_create(**kwargs):
            survey = real_create(**kwargs)
            created["kwargs"] = kwargs
            created["survey"] = survey
            return survey

        payload = orjson.dumps(
            {
                "title": "Coverage add survey",
                "description": "Created by the coverage tests",
                "actions": ["store", "mail"],
                "email_cc": "cc1@example.com\ncc2@example.com",
                "email_bcc": "bcc@example.com",
                "email_formats": ["csv"],
                "max_payload_size_mb": "4",
                "trusted_access_ttl_hours": "24",
                "effective": "2024-01-01T08:00",
                "expires": "2024-12-31T18:00",
                "access_mode": "trusted",
                "embedding_mode": "iframe",
            }
        ).decode()
        request = _request(form={"payload": payload}, method="POST")

        with (
            patch("plone.api.content.create", side_effect=_record_create),
            patch("plone.api.portal.show_message") as show_message,
        ):
            result = SurveyAddView(self.portal, request)()

        survey = created["survey"]
        editor_url = f"{survey.absolute_url()}/@@editor"
        self.assertEqual(result, editor_url)
        self.assertIn(request.response.getStatus(), (302, 303))
        kwargs = created["kwargs"]
        self.assertIs(kwargs["container"], self.portal)
        self.assertEqual(kwargs["type"], "Survey")
        self.assertEqual(kwargs["title"], "Coverage add survey")
        self.assertEqual(kwargs["description"], "Created by the coverage tests")
        self.assertEqual(kwargs["actions"], {"store", "mail"})
        self.assertEqual(kwargs["email_cc"], ["cc1@example.com", "cc2@example.com"])
        self.assertEqual(kwargs["email_bcc"], ["bcc@example.com"])
        self.assertEqual(kwargs["email_formats"], {"csv"})
        self.assertEqual(kwargs["max_payload_size_mb"], 4)
        self.assertEqual(kwargs["trusted_access_ttl_hours"], 24)
        self.assertEqual(kwargs["access_mode"], "trusted")
        self.assertEqual(kwargs["embedding_mode"], "iframe")

        self.assertEqual(request.response.getHeader("Location"), editor_url)
        args, kwargs = show_message.call_args
        self.assertEqual(len(args), 1)
        self.assertEqual(str(args[0]), "Survey created. Let's build it!")
        self.assertIs(kwargs["request"], request)
        self.assertEqual(kwargs["type"], "info")
        effective = survey.effective()
        expires = survey.expires()
        self.assertEqual(
            (effective.year(), effective.month(), effective.day()), (2024, 1, 1)
        )
        self.assertEqual(
            (expires.year(), expires.month(), expires.day()), (2024, 12, 31)
        )
        self.assertEqual(set(survey.actions), {"store", "mail"})

    def test_post_without_title_reports_a_validation_error(self) -> None:
        payload = orjson.dumps({"title": "   ", "actions": ["store"]}).decode()
        request = _request(form={"payload": payload}, method="POST")
        view = SurveyAddView(self.portal, request)
        view.index = MagicMock(return_value="<form>")

        result = view()

        self.assertEqual(result, "<form>")
        view.index.assert_called_once_with()
        self.assertEqual(request.response.getStatus(), 400)
        self.assertEqual(
            [str(error) for error in view.errors],
            ["Please provide a title for your survey."],
        )
        self.assertIsNone(self.portal.get("no-title"))

    def test_post_without_actions_reports_a_validation_error(self) -> None:
        payload = orjson.dumps({"title": "No actions", "actions": []}).decode()
        request = _request(form={"payload": payload}, method="POST")
        view = SurveyAddView(self.portal, request)
        view.index = MagicMock(return_value="<form>")

        result = view()

        self.assertEqual(result, "<form>")
        self.assertEqual(request.response.getStatus(), 400)
        self.assertEqual(
            [str(error) for error in view.errors],
            ["Select at least one submission handling option."],
        )
        self.assertIsNone(self.portal.get("no-actions"))

    def test_post_creation_failure_is_reported_as_server_error(self) -> None:
        payload = orjson.dumps(
            {"title": "Failing survey", "actions": ["store"]}
        ).decode()
        request = _request(form={"payload": payload}, method="POST")

        view = SurveyAddView(self.portal, request)
        view.index = MagicMock(return_value="<form>")

        with (
            patch("plone.api.content.create", side_effect=RuntimeError("boom")),
            self.assertLogs("zopyx.surveyjs.browser.survey_add", level="ERROR"),
        ):
            result = view()

        self.assertEqual(result, "<form>")
        self.assertEqual(request.response.getStatus(), 500)
        self.assertEqual(
            [str(error) for error in view.errors],
            ["We could not create the survey at the moment. Please try again."],
        )
        self.assertIsNone(self.portal.get("failing-survey"))

    def test_theme_choices_return_empty_when_the_theme_service_fails(self) -> None:
        view = SurveyAddView(self.portal, _request())

        with patch(
            "zopyx.surveyjs.browser.services.themes.list_themes",
            side_effect=RuntimeError("themes unavailable"),
        ):
            self.assertEqual(view._survey_themes_choices(), [])


class SurveyMetadataIntegrationTests(unittest.TestCase):
    """Browser level tests for ``SurveyMetadata``."""

    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.addCleanup(logout)
        self.survey = api.content.create(
            container=self.portal,
            type="Survey",
            id="coverage-metadata-survey",
            title="Metadata survey",
        )
        self.survey.email_cc = ["old-cc@example.com"]

    def _view(self, form: dict | None = None, method: str = "GET"):
        request = _request(form=form, method=method)
        return SurveyMetadata(self.survey, request), request

    def test_call_is_denied_for_anonymous_visitors(self) -> None:
        logout()
        view, request = self._view()

        self.assertFalse(view.can_edit)
        result = view()

        self.assertEqual(request.response.getStatus(), 403)
        self.assertEqual(str(result), "You are not allowed to edit this survey.")

    def test_metadata_form_values_come_from_the_context(self) -> None:
        view, _ = self._view()
        view._form_values = {}

        values = view.form_values

        self.assertEqual(values["title"], "Metadata survey")
        self.assertEqual(values["email_cc"], "old-cc@example.com")
        self.assertEqual(values["access_mode"], "public")
        self.assertEqual(values["trusted_access_ttl_hours"], 168)

    def test_post_with_payload_updates_the_survey(self) -> None:
        payload = orjson.dumps(
            {
                "title": "Coverage metadata survey",
                "description": "Updated by the coverage tests",
                "actions": ["store"],
                "email_cc": "cc@example.com",
                "email_formats": ["json"],
                "effective": "2024-01-01T08:00",
                "expires": "2024-12-31T18:00",
                "max_payload_size_mb": "3",
                "trusted_access_ttl_hours": "12",
            }
        ).decode()
        view, request = self._view(form={"payload": payload}, method="POST")

        with patch("plone.api.portal.show_message") as show_message:
            result = view()

        self.assertEqual(result, self.survey.absolute_url())
        self.assertIn(request.response.getStatus(), (302, 303))
        self.assertEqual(
            request.response.getHeader("Location"), self.survey.absolute_url()
        )
        args, kwargs = show_message.call_args
        self.assertEqual(len(args), 1)
        self.assertEqual(str(args[0]), "Survey updated.")
        self.assertIs(kwargs["request"], request)
        self.assertEqual(kwargs["type"], "info")
        self.assertEqual(self.survey.title, "Coverage metadata survey")
        self.assertEqual(self.survey.description, "Updated by the coverage tests")
        self.assertEqual(set(self.survey.actions), {"store"})
        self.assertEqual(list(self.survey.email_cc), ["cc@example.com"])
        self.assertEqual(set(self.survey.email_formats), {"json"})
        self.assertEqual(self.survey.max_payload_size_mb, 3)
        self.assertEqual(self.survey.trusted_access_ttl_hours, 12)
        effective = self.survey.effective()
        expires = self.survey.expires()
        self.assertEqual(
            (effective.year(), effective.month(), effective.day()), (2024, 1, 1)
        )
        self.assertEqual(
            (expires.year(), expires.month(), expires.day()), (2024, 12, 31)
        )

    def test_post_without_payload_uses_the_raw_form_values(self) -> None:
        view, request = self._view(
            form={"title": " Raw title ", "description": " Raw description "},
            method="POST",
        )

        view()

        self.assertIn(request.response.getStatus(), (302, 303))
        self.assertEqual(self.survey.title, "Raw title")
        self.assertEqual(self.survey.description, "Raw description")

    def test_post_with_invalid_payload_json_keeps_the_survey_untouched(self) -> None:
        view, request = self._view(form={"payload": "not-json"}, method="POST")
        view.index = MagicMock(return_value="<form>")

        result = view()

        self.assertEqual(result, "<form>")
        view.index.assert_called_once_with()
        self.assertEqual(request.response.getStatus(), 400)
        self.assertEqual(
            [str(error) for error in view.errors],
            ["We could not read the submitted form data."],
        )
        self.assertEqual(self.survey.title, "Metadata survey")

    def test_post_without_title_reports_a_validation_error(self) -> None:
        payload = orjson.dumps({"title": " ", "actions": ["store"]}).decode()
        view, request = self._view(form={"payload": payload}, method="POST")
        view.index = MagicMock(return_value="<form>")

        result = view()

        self.assertEqual(result, "<form>")
        self.assertEqual(request.response.getStatus(), 400)
        self.assertEqual(
            [str(error) for error in view.errors],
            ["Please provide a title for your survey."],
        )
        self.assertEqual(self.survey.title, "Metadata survey")

    def test_post_without_actions_reports_a_validation_error(self) -> None:
        payload = orjson.dumps({"title": "No actions", "actions": []}).decode()
        view, request = self._view(form={"payload": payload}, method="POST")
        view.index = MagicMock(return_value="<form>")

        result = view()

        self.assertEqual(result, "<form>")
        self.assertEqual(request.response.getStatus(), 400)
        self.assertEqual(
            [str(error) for error in view.errors],
            ["Select at least one submission handling option."],
        )
        self.assertEqual(self.survey.title, "Metadata survey")

    def test_post_update_failure_is_reported_as_server_error(self) -> None:
        payload = orjson.dumps(
            {"title": "Failing update", "actions": ["store"]}
        ).decode()
        view, request = self._view(form={"payload": payload}, method="POST")

        view.index = MagicMock(return_value="<form>")

        with (
            patch(
                "zopyx.surveyjs.browser.survey_metadata.notify",
                side_effect=RuntimeError("event bus down"),
            ),
            self.assertLogs("zopyx.surveyjs.browser.survey_metadata", level="ERROR"),
        ):
            result = view()

        self.assertEqual(result, "<form>")
        self.assertEqual(request.response.getStatus(), 500)
        self.assertEqual(
            [str(error) for error in view.errors],
            ["We could not update the survey at the moment. Please try again."],
        )
        # The attribute loop ran before the failure was detected.
        self.assertEqual(self.survey.title, "Failing update")


if __name__ == "__main__":
    unittest.main()
