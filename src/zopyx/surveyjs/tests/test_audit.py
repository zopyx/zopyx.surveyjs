from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from zopyx.surveyjs.audit import persistent_audit_log


class AuditContext:
    portal_type = "Survey"
    title = "Example survey"

    def absolute_url(self) -> str:
        return "https://example.test/survey"

    def getPhysicalPath(self) -> tuple[str, ...]:
        return ("", "survey")


class PersistentAuditLogTests(unittest.TestCase):
    def test_returns_true_when_backend_writes_entry(self) -> None:
        adapter = MagicMock()
        with patch(
            "zopyx.surveyjs.audit.IPersistentLogger", return_value=adapter
        ):
            result = persistent_audit_log(
                AuditContext(),
                "Survey updated",
                action="metadata.update",
            )

        self.assertTrue(result)
        adapter.log.assert_called_once()

    def test_returns_false_and_logs_failure_when_backend_is_unavailable(self) -> None:
        adapter = MagicMock()
        adapter.log.side_effect = RuntimeError("backend unavailable")
        with (
            patch("zopyx.surveyjs.audit.IPersistentLogger", return_value=adapter),
            patch("zopyx.surveyjs.audit.logger") as logger,
        ):
            result = persistent_audit_log(
                AuditContext(),
                "Survey updated",
                action="metadata.update",
            )

        self.assertFalse(result)
        logger.exception.assert_called_once()
        args, kwargs = logger.exception.call_args
        self.assertIn("metadata.update", args)
        self.assertIn("audit_failure", kwargs["extra"])
        self.assertEqual(kwargs["extra"]["audit_path"], "/survey")


if __name__ == "__main__":
    unittest.main()
