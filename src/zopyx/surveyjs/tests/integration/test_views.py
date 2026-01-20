# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch
from tempfile import TemporaryDirectory

import orjson
from BTrees.OOBTree import OOBTree
from plone import api
from plone.app.testing import setRoles, TEST_USER_ID
from plone.registry.interfaces import IRegistry
from zope.component import getUtility
from zope.annotation.interfaces import IAnnotations
from zope.publisher.browser import TestRequest
from zope.security.interfaces import Unauthorized

from zopyx.surveyjs.browser import views
from zopyx.surveyjs.browser.views import EmbedViewer, Views
from zopyx.surveyjs.constants import FORM_VERSIONS_KEY, RESULTS_KEY
from zopyx.surveyjs.utils import ensure_timezone_aware
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING
from zopyx.surveyjs.interfaces import IFormsSettings
from zopyx.surveyjs.storage import get_result_storage

import unittest

__path__ = [os.path.dirname(__file__)]


class SurveyViewIntegrationTests(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.survey = api.content.create(
            container=self.portal,
            type="Survey",
            id="survey-view",
            title="Survey View",
        )
        self.survey.actions = {"store", "mail"}
        annos = IAnnotations(self.survey)
        annos[FORM_VERSIONS_KEY] = OOBTree()
        annos[RESULTS_KEY] = OOBTree()

    def _make_request(
        self, form: Dict[str, Any] | None = None, body: bytes | None = None
    ):
        request = TestRequest(form=form or {})
        if body is not None:
            request["BODY"] = body
        return request

    def _add_version(self, payload: Dict[str, Any] | None = None) -> str:
        annos = IAnnotations(self.survey)
        version_id = "version-1"
        annos[FORM_VERSIONS_KEY][version_id] = {
            "id": version_id,
            "created": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "user": TEST_USER_ID,
            "form_json": payload
            or {
                "pages": [
                    {
                        "elements": [
                            {"type": "text", "name": "q1", "title": "Question 1"}
                        ]
                    }
                ]
            },
        }
        return version_id

    def _add_result(self, poll_id: str = "poll-1") -> Dict[str, Any]:
        annos = IAnnotations(self.survey)
        entry = {
            "poll_id": poll_id,
            "created": datetime(2024, 2, 2, tzinfo=timezone.utc),
            "user": TEST_USER_ID,
            "form_version": "version-1",
            "result": {"q1": "answer-1", "uuid": poll_id},
        }
        annos[RESULTS_KEY][poll_id] = entry
        return entry

    def test_ensure_timezone_aware_normalizes(self) -> None:
        aware = ensure_timezone_aware(datetime(2024, 1, 1, tzinfo=timezone.utc))
        self.assertIsNotNone(aware.tzinfo)
        naive = ensure_timezone_aware(datetime(2024, 1, 1))
        self.assertEqual(naive.tzinfo, timezone.utc)

    def test_save_and_get_form_json_roundtrip(self) -> None:
        payload = {"pages": [{"elements": [{"type": "text", "name": "q1"}]}]}
        req = self._make_request(form={"surveyText": orjson.dumps(payload)})
        view = Views(self.survey, req)
        view.save_form_json()
        annos = IAnnotations(self.survey)
        self.assertTrue(annos[FORM_VERSIONS_KEY])

        req_get = self._make_request()
        view_get = Views(self.survey, req_get)
        view_get.get_form_json()
        data = orjson.loads(req_get.response.getBody())
        self.assertEqual(data["pages"][0]["elements"][0]["name"], "q1")

    def test_save_poll_stores_when_enabled(self) -> None:
        self._add_version()
        req = self._make_request(form={"pollResult": orjson.dumps({"q1": "yes"})})
        view = Views(self.survey, req)
        view.save_poll()
        annos = IAnnotations(self.survey)
        self.assertEqual(len(annos[RESULTS_KEY]), 1)
        stored = next(iter(annos[RESULTS_KEY].values()))
        self.assertEqual(stored.get("site_id"), self.portal.getId())
        body = orjson.loads(req.response.getBody())
        self.assertTrue(body["isSuccess"])

    def test_save_poll_uses_sql_backend(self) -> None:
        self._add_version()
        self.survey.actions = {"store"}
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        with TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "results.db")
            original_backend = settings.result_storage_backend
            original_uri = settings.database_uri
            settings.result_storage_backend = "rdbms"
            settings.database_uri = f"sqlite:///{db_path}"
            try:
                req = self._make_request(
                    form={"pollResult": orjson.dumps({"q1": "yes"})}
                )
                view = Views(self.survey, req)
                view.save_poll()
                storage = get_result_storage(self.survey)
                results = storage.list_results(self.survey)
                self.assertEqual(len(results), 1)
                annos = IAnnotations(self.survey)
                self.assertEqual(len(annos[RESULTS_KEY]), 0)
            finally:
                settings.result_storage_backend = original_backend
                settings.database_uri = original_uri

    def test_save_poll_skips_storage_when_disabled(self) -> None:
        self.survey.actions = {"mail"}
        self._add_version()
        req = self._make_request(form={"pollResult": orjson.dumps({"q1": "no"})})
        view = Views(self.survey, req)
        view.save_poll()
        annos = IAnnotations(self.survey)
        self.assertEqual(len(annos[RESULTS_KEY]), 0)
        body = orjson.loads(req.response.getBody())
        self.assertFalse(body["stored"])

    def test_save_poll_rejects_unknown_field(self) -> None:
        self._add_version()
        req = self._make_request(form={"pollResult": orjson.dumps({"q2": "no"})})
        Views(self.survey, req).save_poll()
        self.assertEqual(req.response.getStatus(), 400)
        body = orjson.loads(req.response.getBody())
        self.assertEqual(body["error"], "unknown_field")
        self.assertEqual(body["field"], "q2")

    def test_save_poll_rejects_missing_required(self) -> None:
        self._add_version(
            payload={
                "pages": [
                    {"elements": [{"type": "text", "name": "q1", "isRequired": True}]}
                ]
            }
        )
        req = self._make_request(form={"pollResult": orjson.dumps({})})
        Views(self.survey, req).save_poll()
        self.assertEqual(req.response.getStatus(), 400)
        body = orjson.loads(req.response.getBody())
        self.assertEqual(body["error"], "missing_required")
        self.assertEqual(body["field"], "q1")

    def test_save_poll_rejects_payload_over_max_size(self) -> None:
        self.survey.max_payload_size_mb = 1
        self._add_version()
        req = self._make_request(form={"pollResult": orjson.dumps({"q1": "ok"})})
        req.setHeader("Content-Length", str(1 * 1024 * 1024 + 1))
        Views(self.survey, req).save_poll()
        self.assertEqual(req.response.getStatus(), 413)
        body = orjson.loads(req.response.getBody())
        self.assertEqual(body["error"], "request_too_large")

    def test_parse_json_loose_fallback(self) -> None:
        req = self._make_request()
        view = Views(self.survey, req)
        parsed = view._parse_json_loose('prefix {"answer": 42} suffix')
        self.assertEqual(parsed, {"answer": 42})

    def test_dashboard_view_renders_for_manager(self) -> None:
        view = self.survey.restrictedTraverse("@@dashboard")
        html = view()
        self.assertIn("Survey data dashboard", html)

    def test_dashboard_view_forbidden_for_non_manager(self) -> None:
        setRoles(self.portal, TEST_USER_ID, ["Member"])
        with self.assertRaises(Unauthorized):
            self.survey.restrictedTraverse("@@dashboard")()

    def test_pdf_generator_view_renders_for_manager(self) -> None:
        view = self.survey.restrictedTraverse("@@pdf-generator")
        html = view()
        self.assertIn("PDF generator", html)

    def test_pdf_generator_view_forbidden_for_non_manager(self) -> None:
        setRoles(self.portal, TEST_USER_ID, ["Member"])
        with self.assertRaises(Unauthorized):
            self.survey.restrictedTraverse("@@pdf-generator")()

    def test_download_polls_csv_exports_results(self) -> None:
        storage = get_result_storage(self.survey)
        storage.store_result(
            self.survey,
            {
                "poll_id": "poll-1",
                "created": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "result": {"q1": "a"},
            },
        )
        storage.store_result(
            self.survey,
            {
                "poll_id": "poll-2",
                "created": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "result": {"q2": "b"},
            },
        )
        req = self._make_request()
        view = Views(self.survey, req)
        view.download_polls_csv()
        body = req.response.getBody().decode("utf-8")
        rows = list(csv.reader(io.StringIO(body)))
        header = rows[0]
        self.assertEqual(header[:4], ["poll_id", "user", "created", "form_version"])
        self.assertIn("q1", header)
        self.assertIn("q2", header)

    def test_download_polls_json_exports_results(self) -> None:
        storage = get_result_storage(self.survey)
        storage.store_result(
            self.survey,
            {
                "poll_id": "poll-1",
                "created": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "result": {"q1": "a"},
            },
        )
        storage.store_result(
            self.survey,
            {
                "poll_id": "poll-2",
                "created": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "result": {"q2": "b"},
            },
        )
        req = self._make_request()
        Views(self.survey, req).download_polls_json()
        payload = orjson.loads(req.response.getBody())
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["poll_id"], "poll-2")

    def test_download_result_json(self) -> None:
        self._add_version()
        entry = self._add_result()
        req = self._make_request(form={"poll_id": entry["poll_id"], "format": "json"})
        with patch("plone.api.portal.show_message"):
            response = Views(self.survey, req).download_result()
        body = orjson.loads(req.response.getBody())
        self.assertEqual(body[0]["poll_id"], entry["poll_id"])
        self.assertIn("application/json", req.response.getHeader("Content-Type"))
        self.assertIsNotNone(response)

    def test_mail_result_sends_email(self) -> None:
        self._add_version()
        entry = self._add_result("mail-poll")
        self.survey.email_to = "primary@example.com"
        self.survey.email_subject = "Subject {poll_id}"
        self.survey.email_body = "Body {creator}"
        self.survey.email_cc = ["cc@example.com"]
        self.survey.email_bcc = ["bcc@example.com"]

        req = self._make_request(form={"poll_id": entry["poll_id"], "format": "text"})
        with (
            patch("plone.api.portal.show_message"),
            patch.object(views.SurveyConverter, "send_email") as send_email,
        ):
            Views(self.survey, req).mail_result()

        send_email.assert_called_once()
        args, kwargs = send_email.call_args
        self.assertIn("primary@example.com", args[0])
        self.assertEqual(kwargs["cc"], ["cc@example.com"])
        self.assertEqual(kwargs["bcc"], ["bcc@example.com"])

    def test_download_and_restore_version(self) -> None:
        version_id = self._add_version()

        req_download = self._make_request(form={"version_id": version_id})
        with patch("plone.api.portal.show_message"):
            Views(self.survey, req_download).download_version()
        self.assertIn(
            "application/json", req_download.response.getHeader("Content-Type")
        )
        self.assertIn(
            version_id[:8], req_download.response.getHeader("Content-Disposition")
        )

        req_restore = self._make_request(form={"version_id": version_id})
        with patch("plone.api.portal.show_message"):
            Views(self.survey, req_restore).restore_version()

        annos = IAnnotations(self.survey)
        self.assertGreaterEqual(len(annos[FORM_VERSIONS_KEY]), 2)

    def test_upload_version_and_view_json(self) -> None:
        upload_json = {"pages": [{"elements": [{"type": "text", "name": "new"}]}]}
        upload_file = io.BytesIO(orjson.dumps(upload_json))
        upload_file.filename = "form.json"  # mimic ZPublisher file
        req_upload = self._make_request(form={"json_file": upload_file})
        with patch("plone.api.portal.show_message"):
            Views(self.survey, req_upload).upload_version()

        annos = IAnnotations(self.survey)
        self.assertEqual(len(annos[FORM_VERSIONS_KEY]), 1)
        version_id = next(iter(annos[FORM_VERSIONS_KEY].keys()))

        req_view = self._make_request(form={"version_id": version_id})
        Views(self.survey, req_view).view_version_json()
        payload = orjson.loads(req_view.response.getBody())
        self.assertEqual(payload["pages"][0]["elements"][0]["name"], "new")

    def test_view_version_json_missing_returns_error(self) -> None:
        req = self._make_request(form={"version_id": "missing"})
        Views(self.survey, req).view_version_json()
        payload = orjson.loads(req.response.getBody())
        self.assertEqual(payload["error"], "Version not found")

    def test_get_paginated_results_filters(self) -> None:
        annos = IAnnotations(self.survey)
        annos[RESULTS_KEY]["p1"] = {
            "poll_id": "p1",
            "created": datetime(2024, 3, 1, tzinfo=timezone.utc),
            "user": "alice",
            "result": {"uuid": "alpha"},
        }
        annos[RESULTS_KEY]["p2"] = {
            "poll_id": "p2",
            "created": datetime(2024, 3, 2, tzinfo=timezone.utc),
            "user": "bob",
            "result": {"uuid": "beta"},
        }
        req = self._make_request(form={"q": "beta"})
        paginated = Views(self.survey, req).get_paginated_results()
        self.assertEqual(paginated["total"], 1)
        self.assertEqual(paginated["items"][0]["poll_id"], "p2")

    def test_view_result_json_missing_and_existing(self) -> None:
        req_missing = self._make_request(form={"poll_id": "missing"})
        Views(self.survey, req_missing).view_result_json()
        self.assertEqual(
            orjson.loads(req_missing.response.getBody())["error"],
            "Poll result not found",
        )

        self._add_result("available")
        req = self._make_request(form={"poll_id": "available"})
        Views(self.survey, req).view_result_json()
        payload = orjson.loads(req.response.getBody())
        self.assertEqual(payload["q1"], "answer-1")

    def test_delete_results_requires_manager(self) -> None:
        annos = IAnnotations(self.survey)
        annos[RESULTS_KEY]["delete-me"] = {"poll_id": "delete-me"}
        setRoles(self.portal, TEST_USER_ID, ["Member"])

        req = self._make_request(body=b'{"poll_ids": ["delete-me"]}')
        Views(self.survey, req).delete_results()
        self.assertEqual(req.response.getStatus(), 403)
        self.assertIn("not allowed", req.response.getBody().decode("utf-8"))

    def test_delete_results_removes_entries(self) -> None:
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        annos = IAnnotations(self.survey)
        annos[RESULTS_KEY]["one"] = {"poll_id": "one"}
        annos[RESULTS_KEY]["two"] = {"poll_id": "two"}
        req = self._make_request(body=b'{"poll_ids": ["one", "missing"]}')
        Views(self.survey, req).delete_results()
        payload = orjson.loads(req.response.getBody())
        self.assertEqual(payload["deleted"], ["one"])
        self.assertEqual(payload["missing"], ["missing"])
        self.assertNotIn("one", annos[RESULTS_KEY])

    def test_storage_info_masks_rdbms_password(self) -> None:
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        original_backend = settings.result_storage_backend
        original_uri = settings.database_uri
        settings.result_storage_backend = "rdbms"
        settings.database_uri = "postgresql://user:secret@localhost/db"
        try:
            view = Views(self.survey, self._make_request())
            info = view.storage_info
            self.assertIn("Relational database", info)
            self.assertIn("****", info)
            self.assertNotIn("secret", info)
        finally:
            settings.result_storage_backend = original_backend
            settings.database_uri = original_uri

    def test_embed_viewer_sets_headers_when_allowed(self) -> None:
        self.survey.embedding_mode = "iframe"
        req = self._make_request()
        embed_view = EmbedViewer(self.survey, req)
        embed_view.index = MagicMock(return_value="ok")
        embed_view()
        self.assertEqual(req.response.getHeader("X-Frame-Options"), "")
        self.assertEqual(
            req.response.getHeader("Content-Security-Policy"), "frame-ancestors *"
        )

    def test_save_ai_form_validation_errors(self) -> None:
        req = self._make_request(form={"form_json": ""})
        Views(self.survey, req).save_ai_form()
        self.assertEqual(req.response.getStatus(), 500)
        self.assertIn("Save failed", req.response.getBody().decode("utf-8"))

    def test_generate_ai_form_missing_prompt(self) -> None:
        req = self._make_request(form={"prompt": ""})
        Views(self.survey, req).generate_ai_form()
        self.assertEqual(req.response.getStatus(), 400)
        self.assertIn("No prompt", req.response.getBody().decode("utf-8"))

    def test_refine_ai_form_missing_prompt(self) -> None:
        req = self._make_request(form={"current_json": "{}", "refinement_prompt": ""})
        Views(self.survey, req).refine_ai_form()
        self.assertEqual(req.response.getStatus(), 400)
        self.assertIn("No refinement prompt", req.response.getBody().decode("utf-8"))
