from __future__ import annotations

import unittest
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from pathlib import Path

from zopyx.surveyjs.storage import SQLResultStorage


class DummySurvey:
    def UID(self):
        return "survey-1"

    def getId(self):
        return "site-1"


class SQLStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "results.db"
        self.storage = SQLResultStorage(f"sqlite:///{db_path}")
        self.context = DummySurvey()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_sql_storage_roundtrip(self):
        created = datetime(2024, 2, 2, tzinfo=timezone.utc)
        poll_id = self.storage.store_result(
            self.context,
            {
                "poll_id": "poll-1",
                "created": created,
                "user": "tester",
                "form_version": "v1",
                "result": {"q1": "answer"},
            },
        )

        entry = self.storage.get_result(self.context, poll_id)
        self.assertEqual(entry["poll_id"], "poll-1")
        self.assertEqual(entry["site_id"], "site-1")
        self.assertEqual(entry["result"]["q1"], "answer")
        self.assertEqual(entry["created"].tzinfo, timezone.utc)

    def test_sql_storage_list_delete_clear(self):
        self.storage.store_result(
            self.context,
            {
                "poll_id": "poll-1",
                "created": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "result": {"q1": "a"},
            },
        )
        self.storage.store_result(
            self.context,
            {
                "poll_id": "poll-2",
                "created": datetime(2024, 2, 2, tzinfo=timezone.utc),
                "result": {"q1": "b"},
            },
        )

        results = self.storage.list_results(self.context)
        self.assertEqual([r["poll_id"] for r in results], ["poll-2", "poll-1"])

        status = self.storage.delete_results(self.context, ["poll-2", "missing"])
        self.assertEqual(status["deleted"], ["poll-2"])
        self.assertEqual(status["missing"], ["missing"])
        self.assertIsNone(self.storage.get_result(self.context, "poll-2"))

        self.storage.clear_results(self.context)
        self.assertEqual(self.storage.list_results(self.context), [])
