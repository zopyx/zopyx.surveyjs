from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from zopyx.surveyjs.browser.services import results


class ResultServiceTests(unittest.TestCase):
    def request(self, **form):
        return SimpleNamespace(form=form)

    def test_format_created_accepts_iso_z_and_invalid_values(self):
        self.assertEqual(
            results.format_created("2024-01-02T03:04:05Z"),
            "2024-01-02T03:04:05",
        )
        self.assertEqual(
            results.format_created(datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
            "2024-01-02T03:04:05",
        )
        self.assertEqual(results.format_created("not-a-date"), "not-a-date")
        self.assertEqual(results.format_created(None), None)

    def test_parse_tabulator_param_handles_empty_lists_and_invalid_json(self):
        self.assertEqual(results.parse_tabulator_param(self.request(), "filters"), [])
        self.assertEqual(
            results.parse_tabulator_param(self.request(filters=["[{\"field\": \"user\"}]"]), "filters"),
            [{"field": "user"}],
        )
        self.assertEqual(
            results.parse_tabulator_param(self.request(filters="not-json"), "filters"),
            [],
        )

    def test_results_row_normalizes_optional_values(self):
        row = results.results_row(
            {
                "poll_id": "poll-1",
                "user": None,
                "seq_no": 4,
                "created": datetime(2024, 1, 2, tzinfo=timezone.utc),
                "result": {"uuid": "uuid-1"},
            }
        )
        self.assertEqual(row["poll_id"], "poll-1")
        self.assertEqual(row["user"], "")
        self.assertEqual(row["uuid"], "uuid-1")
        self.assertTrue(row["created_ts"] > 0)

    def test_results_apply_filters_supports_comparisons_and_in(self):
        rows = [
            {"user": "Alice", "created_ts": 10, "created_display": "2024-01-01"},
            {"user": "Bob", "created_ts": 20, "created_display": "2024-01-02"},
        ]
        self.assertEqual(
            len(results.results_apply_filters(rows, [{"field": "user", "type": "=", "value": "Alice"}])),
            1,
        )
        self.assertEqual(
            len(results.results_apply_filters(rows, [{"field": "created_ts", "type": ">=", "value": 20}])),
            1,
        )
        self.assertEqual(
            len(results.results_apply_filters(rows, [{"field": "user", "type": "in", "value": ["Bob"]}])),
            1,
        )
        self.assertEqual(
            len(results.results_apply_filters(rows, [{"field": "user", "type": "contains", "value": "ali"}])),
            1,
        )
        self.assertEqual(
            len(results.results_apply_filters(rows, [{"field": "user", "type": "unknown", "value": "x"}])),
            2,
        )

    def test_build_results_payload_filters_sorts_searches_and_paginates(self):
        data = [
            {"poll_id": "poll-a", "user": "Alice", "seq_no": 1, "created": datetime(2024, 1, 1, tzinfo=timezone.utc), "result": {"uuid": "a"}},
            {"poll_id": "poll-b", "user": "Bob", "seq_no": 2, "created": datetime(2024, 1, 2, tzinfo=timezone.utc), "result": {"uuid": "b"}},
            {"poll_id": "poll-c", "user": "Alice", "seq_no": 3, "created": datetime(2024, 1, 3, tzinfo=timezone.utc), "result": {"uuid": "c"}},
        ]
        payload = results.build_results_payload(
            data,
            self.request(
                q="alice",
                page="1",
                size="1",
                sorters='[{"field":"seq_no","dir":"desc"}]',
                filters='[{"field":"seq_no","type":">","value":1}]',
            ),
        )
        self.assertEqual(payload["total_rows"], 1)
        self.assertEqual(payload["last_page"], 1)
        self.assertEqual(payload["data"][0].get("seq_no"), 3)

    def test_build_results_payload_clamps_invalid_pagination_and_accepts_dict_params(self):
        payload = results.build_results_payload(
            [],
            self.request(page="bad", size="0", sorters={"field": "user"}, filters={}),
        )
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["last_page"], 1)
        self.assertEqual(payload["data"], [])

    def test_get_paginated_results_searches_by_uuid_and_paginates(self):
        data = [
            {"poll_id": "one", "user": "a", "created": None, "result": {"uuid": "target"}},
            {"poll_id": "two", "user": "b", "created": None, "result": {"uuid": "other"}},
        ]
        payload = results.get_paginated_results(data, self.request(q="target", b_start="0"))
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["poll_id"], "one")
        self.assertEqual(payload["page"], 1)


if __name__ == "__main__":
    unittest.main()
