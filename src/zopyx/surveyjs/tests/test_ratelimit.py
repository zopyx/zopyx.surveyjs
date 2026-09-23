# -*- coding: utf-8 -*-
"""Tests for the public submission rate limiter (:mod:`zopyx.surveyjs.ratelimit`).

These tests drive the limiter against an in-memory KV store so the window
arithmetic, the identity, the fail-closed behaviour and the reported
``Retry-After`` values can be asserted without a Plone site.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from zopyx.surveyjs import ratelimit
from zopyx.surveyjs.ratelimit import (
    HOUR_WINDOW_SECONDS,
    MINUTE_WINDOW_SECONDS,
    RateLimitSettings,
    check_submission_rate_limit,
    client_address,
    load_rate_limit_settings,
)


class _FakeStore:
    """Minimal in-memory KV store that records write expiries."""

    def __init__(self) -> None:
        self.data: dict = {}
        self.expiries: dict = {}
        self.closed = False
        self.fail_get = False
        self.fail_set = False
        self.fail_close = False

    def get(self, key, default=None):
        if self.fail_get:
            raise RuntimeError("store read failed")
        return self.data.get(key, default)

    def set(self, key, value, expire=None):
        if self.fail_set:
            raise RuntimeError("store write failed")
        self.data[key] = value
        self.expiries[key] = expire
        return True

    def close(self):
        self.closed = True
        if self.fail_close:
            raise RuntimeError("store close failed")


class _FakeRequest:
    def __init__(self, environ=None, headers=None) -> None:
        self.environ = dict(environ or {})
        self.headers = dict(headers or {})

    def get(self, key, default=None):
        return self.environ.get(key, default)

    def get_header(self, name, default=None):
        return self.headers.get(name, default)


def _context(uid="survey-uid"):
    context = MagicMock()
    context.UID.return_value = uid
    context.getId.return_value = uid
    return context


class LoadRateLimitSettingsTests(unittest.TestCase):
    def test_registry_settings_are_read(self) -> None:
        settings = load_rate_limit_settings(
            SimpleNamespace(
                submission_rate_limit_enabled=False,
                submission_rate_limit_per_minute=5,
                submission_rate_limit_per_hour=50,
                submission_rate_limit_trust_proxy=True,
            )
        )
        self.assertEqual(
            settings, RateLimitSettings(False, 5, 50, True)
        )

    def test_missing_or_invalid_values_fall_back_to_defaults(self) -> None:
        settings = load_rate_limit_settings(SimpleNamespace())
        self.assertEqual(settings, RateLimitSettings(True, 120, 1200, False))

        settings = load_rate_limit_settings(
            SimpleNamespace(
                submission_rate_limit_per_minute="not-a-number",
                submission_rate_limit_per_hour=0,
                submission_rate_limit_trust_proxy=None,
            )
        )
        self.assertEqual(settings, RateLimitSettings(True, 120, 1200, False))

    def test_unreadable_registry_falls_back_to_defaults(self) -> None:
        with patch.object(ratelimit, "getUtility", side_effect=RuntimeError("no site")):
            settings = load_rate_limit_settings()
        self.assertEqual(settings, RateLimitSettings(True, 120, 1200, False))


class ClientAddressTests(unittest.TestCase):
    def test_remote_addr_is_used_by_default(self) -> None:
        request = _FakeRequest({"REMOTE_ADDR": "10.0.0.9"})
        self.assertEqual(client_address(request), "10.0.0.9")

    def test_forwarded_for_is_ignored_without_trust_proxy(self) -> None:
        request = _FakeRequest(
            {"REMOTE_ADDR": "10.0.0.9"},
            {"X-Forwarded-For": "203.0.113.7, 198.51.100.2"},
        )
        self.assertEqual(client_address(request), "10.0.0.9")

    def test_rightmost_forwarded_for_entry_is_used_with_trust_proxy(self) -> None:
        request = _FakeRequest(
            {"REMOTE_ADDR": "10.0.0.9"},
            {"X-Forwarded-For": "203.0.113.7, 198.51.100.2"},
        )
        self.assertEqual(
            client_address(request, trust_proxy=True), "198.51.100.2"
        )

    def test_empty_forwarded_for_falls_back_to_remote_addr(self) -> None:
        request = _FakeRequest(
            {"REMOTE_ADDR": "10.0.0.9"}, {"X-Forwarded-For": "  "}
        )
        self.assertEqual(client_address(request, trust_proxy=True), "10.0.0.9")

    def test_broken_header_lookup_is_tolerated(self) -> None:
        request = MagicMock()
        request.get_header.side_effect = RuntimeError("no headers")
        request.get.return_value = "10.0.0.9"
        self.assertEqual(client_address(request), "10.0.0.9")


class CheckSubmissionRateLimitTests(unittest.TestCase):
    """Admission decisions of :func:`check_submission_rate_limit`."""

    def setUp(self) -> None:
        self.store = _FakeStore()
        opener = patch.object(ratelimit, "_open_store", return_value=self.store)
        opener.start()
        self.addCleanup(opener.stop)
        self.request = _FakeRequest({"REMOTE_ADDR": "10.0.0.9"})
        self.context = _context()
        self.settings = RateLimitSettings(True, 2, 10, False)

    def check(self):
        return check_submission_rate_limit(self.context, self.request, self.settings)

    def test_attempts_are_admitted_up_to_the_limit(self) -> None:
        first = self.check()
        second = self.check()
        third = self.check()

        self.assertTrue(first.allowed)
        self.assertEqual(first.reason, ratelimit.REASON_OK)
        self.assertEqual((first.minute_count, first.hour_count), (1, 1))
        self.assertTrue(second.allowed)
        self.assertEqual((second.minute_count, second.hour_count), (2, 2))
        self.assertFalse(third.allowed)
        self.assertEqual(third.reason, ratelimit.REASON_LIMIT_EXCEEDED)
        self.assertEqual(third.limit, 2)
        self.assertEqual(third.count, 3)
        self.assertEqual((third.minute_count, third.hour_count), (3, 3))
        self.assertTrue(self.store.closed)

    def test_retry_after_is_bounded_by_the_minute_window(self) -> None:
        self.check()
        self.check()
        decision = self.check()

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.limit, self.settings.per_minute)
        self.assertGreaterEqual(decision.retry_after, 1)
        self.assertLessEqual(decision.retry_after, MINUTE_WINDOW_SECONDS)

    def test_hourly_budget_reports_the_hour_window(self) -> None:
        self.settings = RateLimitSettings(True, per_minute=100, per_hour=2)
        self.check()
        self.check()
        decision = self.check()

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.limit, 2)
        self.assertEqual(decision.count, 3)
        self.assertGreaterEqual(decision.retry_after, 1)
        self.assertLessEqual(decision.retry_after, HOUR_WINDOW_SECONDS)

    def test_counter_resets_in_the_next_window(self) -> None:
        with patch.object(ratelimit.time, "time", return_value=1_000.0):
            self.check()
            self.check()
            self.assertFalse(self.check().allowed)
        with patch.object(ratelimit.time, "time", return_value=1_100.0):
            decision = self.check()
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.minute_count, 1)

    def test_buckets_expire_one_window_after_the_window_they_count(self) -> None:
        self.check()
        minute_keys = [key for key in self.store.expiries if key.startswith("m:")]
        hour_keys = [key for key in self.store.expiries if key.startswith("h:")]
        self.assertEqual(
            [self.store.expiries[key] for key in minute_keys],
            [MINUTE_WINDOW_SECONDS * 2],
        )
        self.assertEqual(
            [self.store.expiries[key] for key in hour_keys],
            [HOUR_WINDOW_SECONDS * 2],
        )

    def test_limits_are_per_client_address(self) -> None:
        self.check()
        self.check()
        self.assertFalse(self.check().allowed)

        other = _FakeRequest({"REMOTE_ADDR": "198.51.100.2"})
        decision = check_submission_rate_limit(self.context, other, self.settings)
        self.assertTrue(decision.allowed)

    def test_limits_are_per_survey(self) -> None:
        self.check()
        self.check()
        self.assertFalse(self.check().allowed)

        other_context = _context(uid="other-survey")
        decision = check_submission_rate_limit(
            other_context, self.request, self.settings
        )
        self.assertTrue(decision.allowed)

    def test_client_address_is_not_stored_in_clear(self) -> None:
        self.check()
        self.assertNotIn("10.0.0.9", " ".join(self.store.data))

    def test_trust_proxy_uses_the_proxy_appended_address(self) -> None:
        self.settings = RateLimitSettings(True, 1, 10, True)
        request = _FakeRequest(
            {"REMOTE_ADDR": "10.0.0.9"},
            {"X-Forwarded-For": "203.0.113.7, 198.51.100.2"},
        )
        self.assertTrue(
            check_submission_rate_limit(self.context, request, self.settings).allowed
        )
        self.assertFalse(
            check_submission_rate_limit(self.context, request, self.settings).allowed
        )

    def test_disabled_limiter_admits_without_touching_the_store(self) -> None:
        self.settings = RateLimitSettings(False, 1, 1, False)
        decision = self.check()

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, ratelimit.REASON_DISABLED)
        self.assertEqual(self.store.data, {})

    def test_unavailable_store_fails_closed(self) -> None:
        with patch.object(
            ratelimit, "_open_store", side_effect=RuntimeError("no store")
        ):
            decision = self.check()

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, ratelimit.REASON_STORE_UNAVAILABLE)

    def test_store_read_failure_fails_closed(self) -> None:
        self.store.fail_get = True
        decision = self.check()

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, ratelimit.REASON_STORE_UNAVAILABLE)
        self.assertTrue(self.store.closed)

    def test_store_write_failure_fails_closed(self) -> None:
        self.store.fail_set = True
        decision = self.check()

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, ratelimit.REASON_STORE_UNAVAILABLE)

    def test_store_close_failure_is_tolerated(self) -> None:
        self.store.fail_close = True
        decision = self.check()

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, ratelimit.REASON_OK)

    def test_defaults_are_used_when_the_registry_is_unreadable(self) -> None:
        with patch.object(
            ratelimit, "getUtility", side_effect=RuntimeError("no site")
        ):
            decision = check_submission_rate_limit(self.context, self.request)
        self.assertTrue(decision.allowed)


if __name__ == "__main__":
    unittest.main()
