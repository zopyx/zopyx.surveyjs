import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from zopyx.surveyjs import monitoring


class MonitoringFacadeTests(unittest.TestCase):
    def test_monitoring_cache_uses_configured_kv_facade_factory(self):
        settings = SimpleNamespace(kv_cache_backend="diskcache")
        registry = MagicMock()
        registry.forInterface.return_value = settings
        with patch(
            "zopyx.surveyjs.monitoring.getUtility",
            return_value=registry,
        ), patch(
            "zopyx.surveyjs.monitoring.get_configured_kv_store",
            return_value="cache",
        ) as factory:
            self.assertEqual(monitoring._get_cache(), "cache")
        factory.assert_called_once_with(settings, "monitoring")


if __name__ == "__main__":
    unittest.main()
