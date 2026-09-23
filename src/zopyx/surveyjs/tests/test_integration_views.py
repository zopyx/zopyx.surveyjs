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
import transaction
from BTrees.OOBTree import OOBTree
from plone import api
from plone.app.testing import setRoles, TEST_USER_ID
from plone.registry.interfaces import IRegistry
from zope.component import getUtility
from zope.annotation.interfaces import IAnnotations
from zope.publisher.browser import TestRequest
from plone.protect.authenticator import createToken

from zopyx.surveyjs import ratelimit
from zopyx.surveyjs.browser.ai import AIView
from zopyx.surveyjs.browser.views import EmbedViewer, Views
from zopyx.surveyjs.browser.survey_results import SurveyResults
from zopyx.surveyjs.browser.survey_versions import SurveyVersions
from zopyx.surveyjs.constants import FORM_VERSIONS_KEY, RESULTS_KEY
from zopyx.surveyjs.security import build_auth_token
from zopyx.surveyjs.utils import ensure_timezone_aware
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING
from zopyx.surveyjs.interfaces import IFormsSettings
from zopyx.surveyjs.storage import get_result_storage
import diskcache

import unittest

__path__ = [os.path.dirname(__file__)]


def _read_auth_marker(cache_path: str, token: str) -> Any:
    """Read the ``received:`` replay marker for ``token`` from the KV store."""
    cache = diskcache.Cache(cache_path)
    try:
        return cache.get(f"auth:received:{token}")
    finally:
        cache.close()


class _CompatibleTestRequest(TestRequest):
    """Keep legacy test request mutations working on current Zope."""

    def __setitem__(self, key, value):
        self._environ[key] = value
        if key == "REQUEST_METHOD":
            self.method = value

    def get(self, key, default=None):
        if key in self._environ:
            return self._environ[key]
        return super().get(key, default)

    def setHeader(self, name, value):
        key = name.upper().replace("-", "_")
        if key != "CONTENT_LENGTH":
            key = f"HTTP_{key}"
        self._environ[key] = value

    @property
    def SERVER_URL(self):
        return self.getURL()

    def physicalPathToURL(self, path):
        return self.getURL() + "/".join(path)


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
        self.survey.description = "Secret description"
        self.survey.actions = {"store", "mail"}
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        self._original_features = list(getattr(settings, "features_enabled", []) or [])
        settings.authenticity_token_enabled = False
        annos = IAnnotations(self.survey)
        annos[FORM_VERSIONS_KEY] = OOBTree()
        annos[RESULTS_KEY] = OOBTree()

    def tearDown(self) -> None:
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        settings.features_enabled = list(self._original_features)

    def _set_features(self, values: list[str]) -> None:
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        settings.features_enabled = list(values)

    def _make_request(
        self, form: Dict[str, Any] | None = None, body: bytes | None = None
    ):
        request = _CompatibleTestRequest(form=form or {})
        if form and "pollResult" in form:
            request["REQUEST_METHOD"] = "POST"
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

    def _set_kv_cache_directory(self, settings, cache_dir: str) -> None:
        """Point the KV cache at a temporary directory for this test."""
        previous = settings.kv_cache_directory
        settings.kv_cache_directory = cache_dir
        self.addCleanup(setattr, settings, "kv_cache_directory", previous)

    def _enable_auth_tokens(self, cache_dir: str | None = None) -> IFormsSettings:
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        settings.authenticity_token_enabled = True
        settings.authenticity_token_secret = "test-secret"
        settings.authenticity_token_issuer = "test-issuer"
        settings.authenticity_token_audience = "test-audience"
        settings.authenticity_token_ttl_seconds = 600
        if cache_dir:
            self._set_kv_cache_directory(settings, cache_dir)
        return settings

    def _enable_trusted_access(self, cache_dir: str | None = None) -> IFormsSettings:
        self.survey.access_mode = "trusted"
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        if cache_dir:
            self._set_kv_cache_directory(settings, cache_dir)
        return settings

    def _submit_poll(self, token: str):
        """Submit ``@@save-poll`` with an authenticity token."""
        request = self._make_request(
            form={
                "pollResult": orjson.dumps({"q1": "ok"}),
                "auth_token": token,
            }
        )
        Views(self.survey, request).save_poll()
        return request

    def test_ensure_timezone_aware_normalizes(self) -> None:
        aware = ensure_timezone_aware(datetime(2024, 1, 1, tzinfo=timezone.utc))
        self.assertIsNotNone(aware.tzinfo)
        naive = ensure_timezone_aware(datetime(2024, 1, 1))
        self.assertEqual(naive.tzinfo, timezone.utc)

    def test_save_and_get_form_json_roundtrip(self) -> None:
        payload = {"pages": [{"elements": [{"type": "text", "name": "q1"}]}]}
        req = self._make_request(
            form={
                "surveyText": orjson.dumps(payload),
                "_authenticator": createToken(),
            }
        )
        req["REQUEST_METHOD"] = "POST"
        view = Views(self.survey, req)
        view.save_form_json()
        annos = IAnnotations(self.survey)
        self.assertTrue(annos[FORM_VERSIONS_KEY])

        req_get = self._make_request()
        view_get = Views(self.survey, req_get)
        view_get.get_form_json()
        data = orjson.loads(req_get.response.consumeBody())
        self.assertEqual(data["pages"][0]["elements"][0]["name"], "q1")

    def test_get_form_json_rejects_non_get_methods(self) -> None:
        request = self._make_request()
        request["REQUEST_METHOD"] = "POST"

        Views(self.survey, request).get_form_json()

        self.assertEqual(request.response.getStatus(), 405)
        body = orjson.loads(request.response.consumeBody())
        self.assertEqual(body["error"], "method_not_allowed")

    def test_save_poll_rejects_non_post_methods(self) -> None:
        request = self._make_request()
        request["REQUEST_METHOD"] = "GET"

        Views(self.survey, request).save_poll()

        self.assertEqual(request.response.getStatus(), 405)
        body = orjson.loads(request.response.consumeBody())
        self.assertEqual(body["error"], "method_not_allowed")

    def test_save_poll_stores_when_enabled(self) -> None:
        self._add_version()
        req = self._make_request(form={"pollResult": orjson.dumps({"q1": "yes"})})
        view = Views(self.survey, req)
        view.save_poll()
        annos = IAnnotations(self.survey)
        self.assertEqual(len(annos[RESULTS_KEY]), 1)
        stored = next(iter(annos[RESULTS_KEY].values()))
        self.assertEqual(stored.get("site_id"), self.portal.getId())
        body = orjson.loads(req.response.consumeBody())
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
        body = orjson.loads(req.response.consumeBody())
        self.assertFalse(body["stored"])

    def test_save_poll_rejects_unknown_field(self) -> None:
        self._add_version()
        req = self._make_request(form={"pollResult": orjson.dumps({"q2": "no"})})
        Views(self.survey, req).save_poll()
        self.assertEqual(req.response.getStatus(), 400)
        body = orjson.loads(req.response.consumeBody())
        self.assertEqual(body["error"], "unknown_field")
        self.assertEqual(body["field"], "q2")

    def test_save_poll_rejects_script_markup_before_event(self) -> None:
        self._add_version()
        self.survey.actions = {"store"}
        req = self._make_request(
            form={"pollResult": orjson.dumps({"q1": "<script>alert(1)</script>"})}
        )
        with patch("zopyx.surveyjs.browser.views.notify") as notify_mock:
            Views(self.survey, req).save_poll()

        self.assertEqual(req.response.getStatus(), 400)
        body = orjson.loads(req.response.consumeBody())
        self.assertEqual(body["error"], "html_markup")
        notify_mock.assert_not_called()
        self.assertEqual(len(IAnnotations(self.survey)[RESULTS_KEY]), 0)

    def test_save_poll_rejects_unsafe_file_before_event(self) -> None:
        self._add_version(
            payload={"pages": [{"elements": [{"type": "file", "name": "upload"}]}]}
        )
        self.survey.actions = {"store"}
        payload = {
            "upload": [
                {
                    "name": "photo.png",
                    "type": "image/png",
                    "content": 'data:image/png;base64,AAAA" onerror="alert(1)',
                }
            ]
        }
        req = self._make_request(form={"pollResult": orjson.dumps(payload)})
        with patch("zopyx.surveyjs.browser.views.notify") as notify_mock:
            Views(self.survey, req).save_poll()

        self.assertEqual(req.response.getStatus(), 400)
        body = orjson.loads(req.response.consumeBody())
        self.assertEqual(body["error"], "invalid_data_url")
        notify_mock.assert_not_called()
        self.assertEqual(len(IAnnotations(self.survey)[RESULTS_KEY]), 0)

    def test_save_poll_allows_missing_required_when_disabled(self) -> None:
        self._add_version(
            payload={
                "pages": [
                    {"elements": [{"type": "text", "name": "q1", "isRequired": True}]}
                ]
            }
        )
        self.survey.force_server_side_validation = False
        req = self._make_request(form={"pollResult": orjson.dumps({})})
        Views(self.survey, req).save_poll()
        self.assertEqual(req.response.getStatus(), 200)
        body = orjson.loads(req.response.consumeBody())
        self.assertTrue(body["isSuccess"])

    def test_save_poll_rejects_payload_over_max_size(self) -> None:
        self.survey.max_payload_size_mb = 1
        self._add_version()
        req = self._make_request(form={"pollResult": orjson.dumps({"q1": "ok"})})
        req.setHeader("Content-Length", str(1 * 1024 * 1024 + 1))
        Views(self.survey, req).save_poll()
        self.assertEqual(req.response.getStatus(), 413)
        body = orjson.loads(req.response.consumeBody())
        self.assertEqual(body["error"], "request_too_large")

    def test_save_poll_rejects_missing_auth_token_when_enabled(self) -> None:
        settings = self._enable_auth_tokens()
        self._add_version()
        req = self._make_request(form={"pollResult": orjson.dumps({"q1": "ok"})})
        view = Views(self.survey, req)
        try:
            view.save_poll()
            self.assertEqual(req.response.getStatus(), 400)
            body = orjson.loads(req.response.consumeBody())
            self.assertEqual(body["error"], "missing_auth_token")
        finally:
            settings.authenticity_token_enabled = False

    def test_save_poll_accepts_auth_token_when_enabled(self) -> None:
        settings = self._enable_auth_tokens()
        version_id = self._add_version()
        view = Views(self.survey, self._make_request())
        token = build_auth_token(
            form_id=view._form_id(),
            form_version=version_id,
            issuer=settings.authenticity_token_issuer,
            audience=settings.authenticity_token_audience,
            ttl_seconds=settings.authenticity_token_ttl_seconds,
            secret=settings.authenticity_token_secret,
        )
        req = self._make_request(
            form={
                "pollResult": orjson.dumps({"q1": "ok"}),
                "auth_token": token,
            }
        )
        try:
            Views(self.survey, req).save_poll()
            self.assertEqual(req.response.getStatus(), 200)
            body = orjson.loads(req.response.consumeBody())
            self.assertTrue(body["isSuccess"])
        finally:
            settings.authenticity_token_enabled = False

    def test_save_poll_rejects_invalid_auth_token_when_enabled(self) -> None:
        settings = self._enable_auth_tokens()
        version_id = self._add_version()
        view = Views(self.survey, self._make_request())
        token = build_auth_token(
            form_id=view._form_id(),
            form_version=version_id,
            issuer=settings.authenticity_token_issuer,
            audience="other-audience",
            ttl_seconds=settings.authenticity_token_ttl_seconds,
            secret=settings.authenticity_token_secret,
        )
        req = self._make_request(
            form={
                "pollResult": orjson.dumps({"q1": "ok"}),
                "auth_token": token,
            }
        )
        try:
            Views(self.survey, req).save_poll()
            self.assertEqual(req.response.getStatus(), 403)
            body = orjson.loads(req.response.consumeBody())
            self.assertEqual(body["error"], "auth_token_claims_mismatch")
        finally:
            settings.authenticity_token_enabled = False

    def test_auth_token_cache_records_issued(self) -> None:
        self._add_version()
        with TemporaryDirectory() as tmpdir:
            cache_path = os.path.join(tmpdir, "auth")
            settings = self._enable_auth_tokens(cache_dir=tmpdir)
            view = Views(self.survey, self._make_request())
            token = view.auth_token()
            cache = diskcache.Cache(cache_path)
            try:
                self.assertEqual(cache.get(f"auth:issued:{token}"), "ISSUED")
            finally:
                cache.close()
            settings.authenticity_token_enabled = False

    def test_save_poll_rejects_replayed_token(self) -> None:
        version_id = self._add_version()
        with TemporaryDirectory() as tmpdir:
            settings = self._enable_auth_tokens(cache_dir=tmpdir)
            view = Views(self.survey, self._make_request())
            token = build_auth_token(
                form_id=view._form_id(),
                form_version=version_id,
                issuer=settings.authenticity_token_issuer,
                audience=settings.authenticity_token_audience,
                ttl_seconds=settings.authenticity_token_ttl_seconds,
                secret=settings.authenticity_token_secret,
            )
            req = self._make_request(
                form={
                    "pollResult": orjson.dumps({"q1": "ok"}),
                    "auth_token": token,
                }
            )
            try:
                Views(self.survey, req).save_poll()
                self.assertEqual(req.response.getStatus(), 200)
                req2 = self._make_request(
                    form={
                        "pollResult": orjson.dumps({"q1": "ok"}),
                        "auth_token": token,
                    }
                )
                Views(self.survey, req2).save_poll()
                self.assertEqual(req2.response.getStatus(), 403)
                body = orjson.loads(req2.response.consumeBody())
                self.assertEqual(body["error"], "auth_token_replay")
            finally:
                settings.authenticity_token_enabled = False

    def test_save_poll_caches_received_token(self) -> None:
        version_id = self._add_version()
        with TemporaryDirectory() as tmpdir:
            cache_path = os.path.join(tmpdir, "auth")
            settings = self._enable_auth_tokens(cache_dir=tmpdir)
            view = Views(self.survey, self._make_request())
            token = build_auth_token(
                form_id=view._form_id(),
                form_version=version_id,
                issuer=settings.authenticity_token_issuer,
                audience=settings.authenticity_token_audience,
                ttl_seconds=settings.authenticity_token_ttl_seconds,
                secret=settings.authenticity_token_secret,
            )
            req = self._make_request(
                form={
                    "pollResult": orjson.dumps({"q1": "ok"}),
                    "auth_token": token,
                }
            )
            try:
                Views(self.survey, req).save_poll()
                cache = diskcache.Cache(cache_path)
                try:
                    self.assertEqual(cache.get(f"auth:received:{token}"), "RECEIVED")
                finally:
                    cache.close()
            finally:
                settings.authenticity_token_enabled = False

    def test_save_poll_releases_the_replay_marker_when_the_attempt_aborts(self) -> None:
        """A ZODB conflict aborts the request and Zope re-runs ``save_poll``.

        The retry submits the same auth token, so the marker written by the
        aborted attempt must be gone by then — otherwise the retry is rejected
        as a replay (issue #35). The retry's own token check then succeeds
        again, which ``test_auth_services`` pins against a real store.
        """
        version_id = self._add_version()
        with TemporaryDirectory() as tmpdir:
            cache_path = os.path.join(tmpdir, "auth")
            settings = self._enable_auth_tokens(cache_dir=tmpdir)
            view = Views(self.survey, self._make_request())
            token = build_auth_token(
                form_id=view._form_id(),
                form_version=version_id,
                issuer=settings.authenticity_token_issuer,
                audience=settings.authenticity_token_audience,
                ttl_seconds=settings.authenticity_token_ttl_seconds,
                secret=settings.authenticity_token_secret,
            )
            try:
                self.assertEqual(self._submit_poll(token).response.getStatus(), 200)
                self.assertEqual(_read_auth_marker(cache_path, token), "RECEIVED")

                # Zope aborts the conflicted attempt; the aborted attempt's
                # marker is released before the retry runs.
                transaction.abort()
                self.assertIsNone(_read_auth_marker(cache_path, token))
            finally:
                settings.authenticity_token_enabled = False

    # ------------------------------------------------------------------
    # admission control for public submissions
    # ------------------------------------------------------------------

    def _set_rate_limits(
        self,
        settings,
        *,
        enabled: bool = True,
        per_minute: int = 1,
        per_hour: int = 100,
        trust_proxy: bool = False,
    ) -> None:
        """Configure the submission rate limits for this test."""
        previous = (
            settings.submission_rate_limit_enabled,
            settings.submission_rate_limit_per_minute,
            settings.submission_rate_limit_per_hour,
            settings.submission_rate_limit_trust_proxy,
        )
        settings.submission_rate_limit_enabled = enabled
        settings.submission_rate_limit_per_minute = per_minute
        settings.submission_rate_limit_per_hour = per_hour
        settings.submission_rate_limit_trust_proxy = trust_proxy
        self.addCleanup(self._restore_rate_limits, settings, previous)

    @staticmethod
    def _restore_rate_limits(settings, previous) -> None:
        (
            settings.submission_rate_limit_enabled,
            settings.submission_rate_limit_per_minute,
            settings.submission_rate_limit_per_hour,
            settings.submission_rate_limit_trust_proxy,
        ) = previous

    #: Frozen clock for the rate-limit tests.  The bucket key contains the
    #: window index (``int(now // 60)``), so with the wall clock a burst of
    #: submissions can straddle a minute boundary and start a fresh bucket: the
    #: limiter then admits a request the test expects to be refused (this flaked
    #: in CI run 35819976711, test_save_poll_rate_limit_is_scoped_to_....).
    RATE_LIMIT_CLOCK = 1_700_000_000.0

    def _frozen_rate_limit_clock(self, now: float | None = None):
        """Freeze the limiter's clock for the duration of the test body."""
        frozen = self.RATE_LIMIT_CLOCK if now is None else now
        return patch.object(ratelimit, "_current_time", return_value=frozen)

    def _submit(
        self, payload: Dict[str, Any] | None = None, remote_addr: str = "10.0.0.9"
    ):
        """Submit ``@@save-poll`` from ``remote_addr`` and return the request."""
        request = self._make_request(
            form={"pollResult": orjson.dumps(payload or {"q1": "ok"})}
        )
        request["REMOTE_ADDR"] = remote_addr
        Views(self.survey, request).save_poll()
        return request

    def test_save_poll_rate_limit_rejects_attempts_over_the_limit(self) -> None:
        self._add_version()
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        with TemporaryDirectory() as tmpdir, self._frozen_rate_limit_clock():
            self._set_kv_cache_directory(settings, tmpdir)
            self._set_rate_limits(settings, per_minute=2)

            first = self._submit()
            second = self._submit()
            third = self._submit()

            self.assertEqual(first.response.getStatus(), 200)
            self.assertEqual(second.response.getStatus(), 200)
            self.assertEqual(third.response.getStatus(), 429)
            body = orjson.loads(third.response.consumeBody())
            self.assertEqual(body["error"], "rate_limited")
            self.assertFalse(body["isSuccess"])
            self.assertEqual(body["limit"], 2)
            self.assertGreaterEqual(body["retry_after"], 1)
            self.assertLessEqual(body["retry_after"], 60)
            self.assertEqual(
                third.response.getHeader("Retry-After"), str(body["retry_after"])
            )
            # The refused attempt is not stored.
            self.assertEqual(len(IAnnotations(self.survey)[RESULTS_KEY]), 2)

    def test_save_poll_rate_limit_is_scoped_to_the_client_address(self) -> None:
        self._add_version()
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        with TemporaryDirectory() as tmpdir, self._frozen_rate_limit_clock():
            self._set_kv_cache_directory(settings, tmpdir)
            self._set_rate_limits(settings, per_minute=1)

            first = self._submit(remote_addr="10.0.0.1")
            blocked = self._submit(remote_addr="10.0.0.1")
            other = self._submit(remote_addr="10.0.0.2")

            self.assertEqual(first.response.getStatus(), 200)
            self.assertEqual(blocked.response.getStatus(), 429)
            self.assertEqual(other.response.getStatus(), 200)

    def test_save_poll_rate_limit_bucket_ends_with_the_window(self) -> None:
        """The fixed window is part of the bucket key: the next one starts over."""
        self._add_version()
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        window = ratelimit.MINUTE_WINDOW_SECONDS
        last_second = (int(self.RATE_LIMIT_CLOCK) // window + 1) * window - 1
        with TemporaryDirectory() as tmpdir:
            self._set_kv_cache_directory(settings, tmpdir)
            self._set_rate_limits(settings, per_minute=1)

            with self._frozen_rate_limit_clock(last_second):
                first = self._submit(remote_addr="10.0.0.1")
                blocked = self._submit(remote_addr="10.0.0.1")
            with self._frozen_rate_limit_clock(last_second + 2):
                next_window = self._submit(remote_addr="10.0.0.1")

            self.assertEqual(first.response.getStatus(), 200)
            self.assertEqual(blocked.response.getStatus(), 429)
            self.assertEqual(next_window.response.getStatus(), 200)

    def test_save_poll_rate_limit_trust_proxy_uses_forwarded_address(self) -> None:
        self._add_version()
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        with TemporaryDirectory() as tmpdir, self._frozen_rate_limit_clock():
            self._set_kv_cache_directory(settings, tmpdir)
            self._set_rate_limits(settings, per_minute=1, trust_proxy=True)

            first = self._submit(remote_addr="10.0.0.9")
            # Same proxy address, different forwarded client: the limiter
            # must key on the right-most X-Forwarded-For entry.
            second_request = self._make_request(
                form={"pollResult": orjson.dumps({"q1": "ok"})}
            )
            second_request["REMOTE_ADDR"] = "10.0.0.9"
            second_request.setHeader("X-Forwarded-For", "203.0.113.7, 198.51.100.3")
            Views(self.survey, second_request).save_poll()

            self.assertEqual(first.response.getStatus(), 200)
            self.assertEqual(second_request.response.getStatus(), 200)

    def test_save_poll_rate_limit_disabled_admits_repeated_attempts(self) -> None:
        self._add_version()
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        with TemporaryDirectory() as tmpdir:
            self._set_kv_cache_directory(settings, tmpdir)
            self._set_rate_limits(settings, enabled=False, per_minute=1)

            statuses = [self._submit().response.getStatus() for _ in range(3)]

            self.assertEqual(statuses, [200, 200, 200])

    def test_save_poll_fails_closed_when_the_bucket_store_is_unavailable(self) -> None:
        self._add_version()
        with patch(
            "zopyx.surveyjs.ratelimit._open_store",
            side_effect=RuntimeError("store down"),
        ):
            request = self._submit()

        self.assertEqual(request.response.getStatus(), 503)
        body = orjson.loads(request.response.consumeBody())
        self.assertEqual(body["error"], "rate_limit_unavailable")
        self.assertFalse(body["isSuccess"])
        self.assertEqual(len(IAnnotations(self.survey)[RESULTS_KEY]), 0)

    # ------------------------------------------------------------------
    # direct embed token binding
    # ------------------------------------------------------------------

    def _enable_direct_embedding(
        self, settings, *, signing_key: str = "embed-test-secret"
    ) -> None:
        previous = getattr(settings, "embed_direct_global_enabled", False)
        settings.embed_direct_global_enabled = True
        settings.embed_direct_signing_key = signing_key
        self.addCleanup(
            setattr, settings, "embed_direct_global_enabled", previous
        )
        self.survey.embedding_mode = "direct"
        self.survey.embed_direct_origins = ["https://app.example"]

    def _submit_embed(self, token: str, origin: str = "https://app.example"):
        request = self._make_request(form={"pollResult": orjson.dumps({"q1": "ok"})})
        request["REMOTE_ADDR"] = "10.0.0.9"
        request.setHeader("Origin", origin)
        request.setHeader("X-Embed-Token", token)
        Views(self.survey, request).save_poll()
        return request

    def test_save_poll_rejects_embed_token_issued_for_another_survey(self) -> None:
        from zopyx.surveyjs.browser.embed_security import generate_embed_token

        self._add_version()
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        with TemporaryDirectory() as tmpdir:
            self._set_kv_cache_directory(settings, tmpdir)
            self._enable_direct_embedding(settings)

            other_survey = api.content.create(
                container=self.portal,
                type="Survey",
                id="other-embed-survey",
                title="Other embed survey",
            )
            token, _metadata = generate_embed_token(
                other_survey.UID(),
                "https://app.example",
                secret=settings.embed_direct_signing_key,
            )

            request = self._submit_embed(token)

            self.assertEqual(request.response.getStatus(), 403)
            body = orjson.loads(request.response.consumeBody())
            self.assertEqual(body["error"], "survey_mismatch")
            self.assertEqual(len(IAnnotations(self.survey)[RESULTS_KEY]), 0)

    def test_save_poll_accepts_embed_token_issued_for_the_target_survey(self) -> None:
        from zopyx.surveyjs.browser.embed_security import generate_embed_token

        self._add_version()
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        with TemporaryDirectory() as tmpdir:
            self._set_kv_cache_directory(settings, tmpdir)
            self._enable_direct_embedding(settings)

            token, _metadata = generate_embed_token(
                self.survey.UID(),
                "https://app.example",
                secret=settings.embed_direct_signing_key,
            )

            request = self._submit_embed(token)

            self.assertEqual(request.response.getStatus(), 200)
            body = orjson.loads(request.response.consumeBody())
            self.assertTrue(body["isSuccess"])
            self.assertEqual(len(IAnnotations(self.survey)[RESULTS_KEY]), 1)

    def test_save_poll_rejects_embed_submission_without_direct_mode(self) -> None:
        from zopyx.surveyjs.browser.embed_security import generate_embed_token

        self._add_version()
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        with TemporaryDirectory() as tmpdir:
            self._set_kv_cache_directory(settings, tmpdir)
            self._enable_direct_embedding(settings)
            token, _metadata = generate_embed_token(
                self.survey.UID(),
                "https://app.example",
                secret=settings.embed_direct_signing_key,
            )
            # The survey is switched back to iframe embedding after the token
            # was issued: the token must not keep the embed path open.
            self.survey.embedding_mode = "iframe"

            request = self._submit_embed(token)

            self.assertEqual(request.response.getStatus(), 403)
            body = orjson.loads(request.response.consumeBody())
            self.assertEqual(body["error"], "direct_embedding_not_enabled")
            self.assertEqual(len(IAnnotations(self.survey)[RESULTS_KEY]), 0)

    def test_dashboard_view_renders_for_manager(self) -> None:
        view = self.survey.restrictedTraverse("@@dashboard")
        html = view()
        self.assertIn("Survey data dashboard", html)
        chart_asset = html.index("surveyjs/chart.umd.min.js")
        analytics_asset = html.index("surveyjs/survey.analytics.min.js")
        self.assertLess(chart_asset, analytics_asset)

    def test_survey_metadata_view_renders_for_manager(self) -> None:
        view = self.survey.restrictedTraverse("@@survey-metadata")
        html = view()
        self.assertIn("Metadata", html)

    def test_pdf_generator_view_renders_for_manager(self) -> None:
        view = self.survey.restrictedTraverse("@@pfs-generator")
        html = view()
        self.assertIn("PDF generator", html)

    def test_ai_view_renders_empty_chat_panel_without_temp_form(self) -> None:
        view = self.survey.restrictedTraverse("@@ai")
        html = view()
        self.assertIn("Improve Temporary Form", html)
        self.assertIn('id="aiChatForm"', html)
        self.assertIn(
            "Start a temporary SurveyJS draft with a prompt. The first prompt creates the workspace form.",
            html,
        )
        self.assertIn("Generate AI Draft", html)
        self.assertNotIn('id="aiPreviewModal"', html)

    def test_ai_view_enables_chat_panel_when_temp_form_exists(self) -> None:
        annos = IAnnotations(self.survey)
        annos[AIView.TEMP_FORM_ANNOTATION_KEY] = {"pages": []}

        view = self.survey.restrictedTraverse("@@ai")
        html = view()
        self.assertIn("Improve Temporary Form", html)
        self.assertIn(
            "Example: Add a section for contact preferences and make email required.",
            html,
        )
        self.assertNotIn(
            "Start a temporary SurveyJS draft with a prompt. The first prompt creates the workspace form.",
            html,
        )
        self.assertIn("Apply AI Change", html)
        self.assertIn('id="aiPreviewModal"', html)

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
        body = req.response.consumeBody().decode("utf-8")
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
        payload = orjson.loads(req.response.consumeBody())
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["poll_id"], "poll-2")

    def test_download_result_json(self) -> None:
        self._add_version()
        entry = self._add_result()
        req = self._make_request(form={"poll_id": entry["poll_id"], "format": "json"})
        with (
            patch.object(type(req.response), "write") as write,
            patch("plone.api.portal.show_message"),
        ):
            response = SurveyResults(self.survey, req).download_result()
        body = b"".join(call.args[0] for call in write.call_args_list)
        self.assertIn(entry["poll_id"].encode(), body)
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
            patch.object(type(req.response), "redirect"),
            patch(
                "zopyx.surveyjs.converters.cli.SurveyConverter.send_email"
            ) as send_email,
        ):
            SurveyResults(self.survey, req).mail_result()

        send_email.assert_called_once()
        args, kwargs = send_email.call_args
        self.assertIn("primary@example.com", args[0])
        self.assertEqual(kwargs["cc"], ["cc@example.com"])
        self.assertEqual(kwargs["bcc"], ["bcc@example.com"])

    def test_download_and_restore_version(self) -> None:
        version_id = self._add_version()

        req_download = self._make_request(form={"version_id": version_id})
        with (
            patch.object(type(req_download.response), "write"),
            patch("plone.api.portal.show_message"),
        ):
            SurveyVersions(self.survey, req_download).download_version()
        self.assertIn(
            "application/json", req_download.response.getHeader("Content-Type")
        )
        self.assertIn(
            version_id[:8], req_download.response.getHeader("Content-Disposition")
        )

        req_restore = self._make_request(form={"version_id": version_id})
        with (
            patch.object(type(req_restore.response), "redirect"),
            patch("plone.api.portal.show_message"),
        ):
            SurveyVersions(self.survey, req_restore).restore_version()

        annos = IAnnotations(self.survey)
        self.assertGreaterEqual(len(annos[FORM_VERSIONS_KEY]), 2)

    def test_upload_version_and_view_json(self) -> None:
        upload_json = {"pages": [{"elements": [{"type": "text", "name": "new"}]}]}
        upload_file = io.BytesIO(orjson.dumps(upload_json))
        upload_file.filename = "form.json"  # mimic ZPublisher file
        req_upload = self._make_request(form={"json_file": upload_file})
        with (
            patch.object(type(req_upload.response), "redirect"),
            patch("plone.api.portal.show_message"),
        ):
            SurveyVersions(self.survey, req_upload).upload_version()

        annos = IAnnotations(self.survey)
        self.assertEqual(len(annos[FORM_VERSIONS_KEY]), 1)
        version_id = next(iter(annos[FORM_VERSIONS_KEY].keys()))

        req_view = self._make_request(form={"version_id": version_id})
        SurveyVersions(self.survey, req_view).view_version_json()
        payload = orjson.loads(req_view.response.consumeBody())
        self.assertEqual(payload["pages"][0]["elements"][0]["name"], "new")

    def test_view_version_json_missing_returns_error(self) -> None:
        req = self._make_request(form={"version_id": "missing"})
        SurveyVersions(self.survey, req).view_version_json()
        payload = orjson.loads(req.response.consumeBody())
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
        paginated = SurveyResults(self.survey, req).get_paginated_results()
        self.assertEqual(paginated["total"], 1)
        self.assertEqual(paginated["items"][0]["poll_id"], "p2")

    def test_view_result_json_missing_and_existing(self) -> None:
        req_missing = self._make_request(form={"poll_id": "missing"})
        SurveyResults(self.survey, req_missing).view_result_json()
        self.assertEqual(
            orjson.loads(req_missing.response.consumeBody())["error"],
            "Poll result not found",
        )

        self._add_result("available")
        req = self._make_request(form={"poll_id": "available"})
        SurveyResults(self.survey, req).view_result_json()
        payload = orjson.loads(req.response.consumeBody())
        self.assertEqual(payload["q1"], "answer-1")

    def test_delete_results_requires_manager(self) -> None:
        annos = IAnnotations(self.survey)
        annos[RESULTS_KEY]["delete-me"] = {"poll_id": "delete-me"}
        setRoles(self.portal, TEST_USER_ID, ["Member"])

        req = self._make_request(body=b'{"poll_ids": ["delete-me"]}')
        with patch.object(type(req.response), "write") as write:
            SurveyResults(self.survey, req).delete_results()
        self.assertEqual(req.response.getStatus(), 403)
        body = b"".join(call.args[0] for call in write.call_args_list)
        self.assertIn(b"not allowed", body)

    def test_delete_results_removes_entries(self) -> None:
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        annos = IAnnotations(self.survey)
        annos[RESULTS_KEY]["one"] = {"poll_id": "one"}
        annos[RESULTS_KEY]["two"] = {"poll_id": "two"}
        req = self._make_request(body=b'{"poll_ids": ["one", "missing"]}')
        SurveyResults(self.survey, req).delete_results()
        payload = orjson.loads(req.response.consumeBody())
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
            self.assertIn("user:", info)
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

    def test_embed_viewer_denies_when_disabled(self) -> None:
        self.survey.embedding_mode = "none"
        req = self._make_request()
        embed_view = EmbedViewer(self.survey, req)
        embed_view.index = MagicMock(return_value="ok")
        result = embed_view()
        self.assertEqual(req.response.getStatus(), 403)
        self.assertIn("Embedding is disabled", result)

    def test_feature_disabled_view_is_minimal(self) -> None:
        req = self._make_request()
        view = api.content.get_view("feature-disabled", self.survey, req)
        body = view()
        self.assertEqual(req.response.getStatus(), 403)
        self.assertIn("Feature disabled, access forbidden.", body)
        self.assertNotIn(self.survey.title, body)
        self.assertNotIn(self.survey.description, body)
