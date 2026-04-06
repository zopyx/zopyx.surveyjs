"""Tests for rate limiting service.

Tests the RateLimitService class and its integration with endpoints.
"""

import time
import unittest
from unittest.mock import Mock, patch, MagicMock

from zopyx.surveyjs.browser.services.rate_limit import (
    RateLimitService,
    RateLimitExceeded,
    rate_limit_endpoint,
    KEY_PREFIX_IP,
)


class TestRateLimitService(unittest.TestCase):
    """Unit tests for RateLimitService."""

    def setUp(self):
        """Set up test fixtures."""
        self.context = Mock()
        self.request = Mock()
        self.request.getClientAddr.return_value = "192.168.1.1"
        self.request.get_header.return_value = None
        self.request.cookies = {}

    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    @patch("zopyx.surveyjs.browser.services.rate_limit.getUtility")
    def test_check_rate_limit_allows_under_limit(self, mock_get_utility, mock_cache_class):
        """Test that requests under limit are allowed."""
        # Setup mock cache
        mock_cache = Mock()
        mock_cache.get.return_value = []
        mock_cache_class.return_value = mock_cache

        # Setup mock settings
        mock_settings = Mock()
        mock_settings.rate_limiting_enabled = True
        mock_settings.rate_limit_burst_factor = 2.0
        mock_registry = Mock()
        mock_registry.forInterface.return_value = mock_settings
        mock_get_utility.return_value = mock_registry

        service = RateLimitService(self.context, self.request)

        # Should not raise
        result = service.check_rate_limit("test_endpoint", 10, 60)
        self.assertTrue(result)

    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    @patch("zopyx.surveyjs.browser.services.rate_limit.getUtility")
    def test_check_rate_limit_blocks_over_limit(self, mock_get_utility, mock_cache_class):
        """Test that requests over limit are blocked."""
        # Setup mock cache with 25 recent requests (over limit of 10 and burst of 20)
        mock_cache = Mock()
        now = time.time()
        mock_cache.get.return_value = [now - i for i in range(25)]
        mock_cache_class.return_value = mock_cache

        # Setup mock settings - no burst allowance for clearer test
        mock_settings = Mock()
        mock_settings.rate_limiting_enabled = True
        mock_settings.rate_limit_burst_factor = 1.0  # No burst
        mock_registry = Mock()
        mock_registry.forInterface.return_value = mock_settings
        mock_get_utility.return_value = mock_registry

        service = RateLimitService(self.context, self.request)

        with self.assertRaises(RateLimitExceeded):
            service.check_rate_limit("test_endpoint", 10, 60)

    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    @patch("zopyx.surveyjs.browser.services.rate_limit.getUtility")
    def test_sliding_window_expires_old_requests(self, mock_get_utility, mock_cache_class):
        """Test that old requests outside window are expired."""
        # Setup mock cache with mix of old and new requests
        mock_cache = Mock()
        now = time.time()
        mock_cache.get.return_value = [
            now - 120, now - 119, now - 118,  # Outside 60s window
            now - 10, now - 5, now - 1       # Inside 60s window
        ]
        mock_cache_class.return_value = mock_cache

        # Setup mock settings
        mock_settings = Mock()
        mock_settings.rate_limiting_enabled = True
        mock_settings.rate_limit_burst_factor = 2.0
        mock_registry = Mock()
        mock_registry.forInterface.return_value = mock_settings
        mock_get_utility.return_value = mock_registry

        service = RateLimitService(self.context, self.request)

        # Should allow (only 3 requests in window, limit is 5)
        result = service.check_rate_limit("test_endpoint", 5, 60)
        self.assertTrue(result)

    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    @patch("zopyx.surveyjs.browser.services.rate_limit.getUtility")
    def test_fail_open_when_cache_unavailable(self, mock_get_utility, mock_cache_class):
        """Test that requests are allowed when cache fails."""
        # Setup mock cache to fail
        mock_cache_class.side_effect = Exception("Cache error")

        # Setup mock settings
        mock_settings = Mock()
        mock_settings.rate_limiting_enabled = True
        mock_registry = Mock()
        mock_registry.forInterface.return_value = mock_settings
        mock_get_utility.return_value = mock_registry

        service = RateLimitService(self.context, self.request)

        # Should allow (fail-open)
        result = service.check_rate_limit("test_endpoint", 10, 60)
        self.assertTrue(result)

    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    @patch("zopyx.surveyjs.browser.services.rate_limit.getUtility")
    def test_disabled_rate_limiting(self, mock_get_utility, mock_cache_class):
        """Test that rate limiting can be disabled."""
        # Setup mock settings with rate limiting disabled
        mock_settings = Mock()
        mock_settings.rate_limiting_enabled = False
        mock_registry = Mock()
        mock_registry.forInterface.return_value = mock_settings
        mock_get_utility.return_value = mock_registry

        service = RateLimitService(self.context, self.request)

        # Should always allow when disabled
        result = service.check_rate_limit("test_endpoint", 10, 60)
        self.assertTrue(result)
        # Cache should not be accessed
        mock_cache_class.assert_not_called()

    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    @patch("zopyx.surveyjs.browser.services.rate_limit.getUtility")
    def test_burst_allowance(self, mock_get_utility, mock_cache_class):
        """Test that burst factor allows temporary over-limit requests."""
        # Setup mock cache with requests at limit but under burst
        mock_cache = Mock()
        now = time.time()
        # 12 requests (over limit of 10, but under burst of 20)
        mock_cache.get.return_value = [now - i for i in range(12)]
        mock_cache_class.return_value = mock_cache

        # Setup mock settings
        mock_settings = Mock()
        mock_settings.rate_limiting_enabled = True
        mock_settings.rate_limit_burst_factor = 2.0  # burst = 20
        mock_registry = Mock()
        mock_registry.forInterface.return_value = mock_settings
        mock_get_utility.return_value = mock_registry

        service = RateLimitService(self.context, self.request)

        # Should allow (within burst limit)
        result = service.check_rate_limit("test_endpoint", 10, 60)
        self.assertTrue(result)

    def test_get_client_ip_from_forwarded_header(self):
        """Test IP extraction from X-Forwarded-For header."""
        self.request.get_header.side_effect = lambda h: {
            "X-Forwarded-For": "10.0.0.1, 10.0.0.2",
            "X-Real-Ip": None
        }.get(h)

        service = RateLimitService(self.context, self.request)
        ip = service._get_client_ip()

        # Should take first IP from chain
        self.assertEqual(ip, "10.0.0.1")

    def test_get_client_ip_from_real_ip_header(self):
        """Test IP extraction from X-Real-Ip header."""
        self.request.get_header.side_effect = lambda h: {
            "X-Forwarded-For": None,
            "X-Real-Ip": "10.0.0.5"
        }.get(h)

        service = RateLimitService(self.context, self.request)
        ip = service._get_client_ip()

        self.assertEqual(ip, "10.0.0.5")

    def test_get_client_ip_fallback(self):
        """Test IP fallback to getClientAddr."""
        self.request.get_header.return_value = None
        self.request.getClientAddr.return_value = "192.168.1.100"

        service = RateLimitService(self.context, self.request)
        ip = service._get_client_ip()

        self.assertEqual(ip, "192.168.1.100")

    def test_cache_key_format(self):
        """Test that cache keys are properly formatted."""
        service = RateLimitService(self.context, self.request)
        key = service._build_cache_key("save_poll", "ip", "192.168.1.1")

        # Key should start with prefix and contain hashed endpoint and identifier
        self.assertTrue(key.startswith(KEY_PREFIX_IP))
        self.assertIn("192.168.1.1", key)  # Contains identifier

    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    @patch("zopyx.surveyjs.browser.services.rate_limit.getUtility")
    def test_context_manager(self, mock_get_utility, mock_cache_class):
        """Test that context manager properly closes cache."""
        mock_cache = Mock()
        mock_cache_class.return_value = mock_cache

        mock_settings = Mock()
        mock_settings.rate_limiting_enabled = True
        mock_settings.rate_limit_burst_factor = 2.0
        mock_registry = Mock()
        mock_registry.forInterface.return_value = mock_settings
        mock_get_utility.return_value = mock_registry

        with RateLimitService(self.context, self.request) as service:
            service.check_rate_limit("test", 10, 60)

        # Cache should be closed after context exit
        mock_cache.close.assert_called_once()

    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    @patch("zopyx.surveyjs.browser.services.rate_limit.getUtility")
    def test_rate_limit_headers_added(self, mock_get_utility, mock_cache_class):
        """Test that rate limit headers are added to response."""
        mock_cache = Mock()
        now = time.time()
        mock_cache.get.return_value = [now - 10, now - 5]  # 2 requests in window
        mock_cache_class.return_value = mock_cache

        mock_settings = Mock()
        mock_settings.rate_limiting_enabled = True
        mock_registry = Mock()
        mock_registry.forInterface.return_value = mock_settings
        mock_get_utility.return_value = mock_registry

        service = RateLimitService(self.context, self.request)

        response = Mock()
        response.headers = {}

        service.add_rate_limit_headers(response, "test_endpoint", 10, 60)

        self.assertEqual(response.headers.get("X-RateLimit-Limit"), "10")
        self.assertEqual(response.headers.get("X-RateLimit-Remaining"), "8")
        self.assertIn("X-RateLimit-Reset", response.headers)
        self.assertEqual(response.headers.get("X-RateLimit-Window"), "60")


class TestRateLimitDecorator(unittest.TestCase):
    """Tests for the rate_limit_endpoint decorator."""

    def setUp(self):
        """Set up test fixtures."""
        self.context = Mock()
        self.request = Mock()
        self.request.getClientAddr.return_value = "192.168.1.1"
        self.request.get_header.return_value = None
        self.request.cookies = {}
        self.request.response = Mock()
        self.request.response.headers = {}

    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    @patch("zopyx.surveyjs.browser.services.rate_limit.getUtility")
    def test_decorator_allows_under_limit(self, mock_get_utility, mock_cache_class):
        """Test that decorator allows requests under limit."""
        mock_cache = Mock()
        mock_cache.get.return_value = []
        mock_cache_class.return_value = mock_cache

        mock_settings = Mock()
        mock_settings.rate_limiting_enabled = True
        mock_settings.rate_limit_burst_factor = 2.0
        mock_registry = Mock()
        mock_registry.forInterface.return_value = mock_settings
        mock_get_utility.return_value = mock_registry

        class TestView:
            def __init__(self, context, request):
                self.context = context
                self.request = request

            @rate_limit_endpoint("test_endpoint", 10, 60)
            def test_method(self):
                return {"success": True}

        view = TestView(self.context, self.request)
        result = view.test_method()

        self.assertEqual(result, {"success": True})

    @patch("zopyx.surveyjs.browser.services.rate_limit.json_error")
    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    @patch("zopyx.surveyjs.browser.services.rate_limit.getUtility")
    def test_decorator_blocks_over_limit(self, mock_get_utility, mock_cache_class, mock_json_error):
        """Test that decorator blocks requests over limit."""
        mock_cache = Mock()
        now = time.time()
        mock_cache.get.return_value = [now - i for i in range(25)]  # Over limit and burst
        mock_cache_class.return_value = mock_cache

        mock_settings = Mock()
        mock_settings.rate_limiting_enabled = True
        mock_settings.rate_limit_burst_factor = 1.0  # No burst
        mock_registry = Mock()
        mock_registry.forInterface.return_value = mock_settings
        mock_get_utility.return_value = mock_registry

        # Mock json_error to return a response-like object
        mock_response = Mock()
        mock_response.headers = {}
        mock_json_error.return_value = mock_response

        class TestView:
            def __init__(self, context, request):
                self.context = context
                self.request = request

            @rate_limit_endpoint("test_endpoint", 10, 60)
            def test_method(self):
                return {"success": True}

        view = TestView(self.context, self.request)
        result = view.test_method()

        # json_error should have been called
        mock_json_error.assert_called_once()
        # Should return the error response, not success
        self.assertEqual(result, mock_response)


class TestRateLimitIntegration(unittest.TestCase):
    """Integration-style tests for rate limiting scenarios."""

    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    @patch("zopyx.surveyjs.browser.services.rate_limit.getUtility")
    def test_multiple_endpoints_independent(self, mock_get_utility, mock_cache_class):
        """Test that different endpoints have independent rate limits."""
        cache_data = {}

        def mock_get(key, default=None):
            return cache_data.get(key, default)

        def mock_set(key, value, expire=None):
            cache_data[key] = value

        mock_cache = Mock()
        mock_cache.get = mock_get
        mock_cache.set = mock_set
        mock_cache_class.return_value = mock_cache

        mock_settings = Mock()
        mock_settings.rate_limiting_enabled = True
        mock_settings.rate_limit_burst_factor = 1.0  # No burst for clearer test
        mock_registry = Mock()
        mock_registry.forInterface.return_value = mock_settings
        mock_get_utility.return_value = mock_registry

        context = Mock()
        request = Mock()
        request.getClientAddr.return_value = "192.168.1.1"
        request.get_header.return_value = None
        request.cookies = {}

        service = RateLimitService(context, request)

        # Exhaust limit for endpoint A (need to go over burst too)
        for _ in range(15):
            try:
                service.check_rate_limit("endpoint_a", 10, 60)
            except RateLimitExceeded:
                pass  # Expected after limit

        # Should be blocked
        with self.assertRaises(RateLimitExceeded):
            service.check_rate_limit("endpoint_a", 10, 60)

        # But endpoint B should still work (first request)
        result = service.check_rate_limit("endpoint_b", 10, 60)
        self.assertTrue(result)

    @patch("zopyx.surveyjs.browser.services.rate_limit.diskcache.Cache")
    @patch("zopyx.surveyjs.browser.services.rate_limit.getUtility")
    def test_different_ips_independent(self, mock_get_utility, mock_cache_class):
        """Test that different IPs have independent rate limits."""
        cache_data = {}

        def mock_get(key, default=None):
            return cache_data.get(key, default)

        def mock_set(key, value, expire=None):
            cache_data[key] = value

        mock_cache = Mock()
        mock_cache.get = mock_get
        mock_cache.set = mock_set
        mock_cache_class.return_value = mock_cache

        mock_settings = Mock()
        mock_settings.rate_limiting_enabled = True
        mock_settings.rate_limit_burst_factor = 1.0  # No burst for clearer test
        mock_registry = Mock()
        mock_registry.forInterface.return_value = mock_settings
        mock_get_utility.return_value = mock_registry

        context = Mock()

        # First IP exhausts its limit (need to go over)
        request1 = Mock()
        request1.getClientAddr.return_value = "192.168.1.1"
        request1.get_header.return_value = None
        request1.cookies = {}

        service1 = RateLimitService(context, request1)
        for _ in range(15):
            try:
                service1.check_rate_limit("test_endpoint", 10, 60)
            except RateLimitExceeded:
                pass  # Expected after limit

        # Should be blocked for IP1
        with self.assertRaises(RateLimitExceeded):
            service1.check_rate_limit("test_endpoint", 10, 60)

        # But IP2 should still work (first request)
        request2 = Mock()
        request2.getClientAddr.return_value = "192.168.1.2"
        request2.get_header.return_value = None
        request2.cookies = {}

        service2 = RateLimitService(context, request2)
        result = service2.check_rate_limit("test_endpoint", 10, 60)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
