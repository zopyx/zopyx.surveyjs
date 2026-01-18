from __future__ import annotations

import unittest
from datetime import datetime, timezone

from plone import api
from plone.app.testing import TEST_USER_ID, setRoles

from zopyx.surveyjs.storage import ZODBResultStorage
from zopyx.surveyjs.testing import ZOPYX_SURVEYJS_INTEGRATION_TESTING


class ZODBStorageTests(unittest.TestCase):
    layer = ZOPYX_SURVEYJS_INTEGRATION_TESTING

    def setUp(self) -> None:
        self.portal = self.layer["portal"]
        setRoles(self.portal, TEST_USER_ID, ["Manager"])
        self.survey = api.content.create(
            container=self.portal,
            type="Survey",
            id="survey-storage",
            title="Survey Storage",
        )
        self.storage = ZODBResultStorage()

    def test_store_and_get_result(self) -> None:
        poll_id = self.storage.store_result(
            self.survey,
            {
                "poll_id": "poll-1",
                "created": "2024-01-01T00:00:00Z",
                "result": {"q1": "answer"},
            },
        )
        entry = self.storage.get_result(self.survey, poll_id)
        self.assertEqual(entry["poll_id"], "poll-1")
        self.assertEqual(entry["site_id"], self.portal.getId())
        self.assertEqual(entry["result"]["q1"], "answer")
        self.assertEqual(entry["created"].tzinfo, timezone.utc)

    def test_list_delete_clear_count_results(self) -> None:
        self.storage.store_result(
            self.survey,
            {
                "poll_id": "poll-1",
                "created": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "result": {"q1": "a"},
            },
        )
        self.storage.store_result(
            self.survey,
            {
                "poll_id": "poll-2",
                "created": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "result": {"q1": "b"},
            },
        )
        results = self.storage.list_results(self.survey)
        self.assertEqual([r["poll_id"] for r in results], ["poll-2", "poll-1"])
        self.assertEqual(self.storage.count_results(self.survey), 2)

        status = self.storage.delete_results(self.survey, ["poll-2", "missing"])
        self.assertEqual(status["deleted"], ["poll-2"])
        self.assertEqual(status["missing"], ["missing"])
        self.assertIsNone(self.storage.get_result(self.survey, "poll-2"))

        self.storage.clear_results(self.survey)
        self.assertEqual(self.storage.list_results(self.survey), [])
