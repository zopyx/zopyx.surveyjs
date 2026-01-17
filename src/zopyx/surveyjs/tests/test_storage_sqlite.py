from __future__ import annotations

from datetime import datetime, timezone

from zopyx.surveyjs.storage import SQLiteResultStorage


class DummySurvey:
    def UID(self):
        return "survey-1"


def test_sqlite_storage_roundtrip(tmp_path):
    db_path = tmp_path / "results.db"
    storage = SQLiteResultStorage(str(db_path))
    context = DummySurvey()

    created = datetime(2024, 2, 2, tzinfo=timezone.utc)
    poll_id = storage.store_result(
        context,
        {
            "poll_id": "poll-1",
            "created": created,
            "user": "tester",
            "form_version": "v1",
            "result": {"q1": "answer"},
        },
    )

    entry = storage.get_result(context, poll_id)
    assert entry["poll_id"] == "poll-1"
    assert entry["result"]["q1"] == "answer"
    assert entry["created"].tzinfo == timezone.utc


def test_sqlite_storage_list_delete_clear(tmp_path):
    db_path = tmp_path / "results.db"
    storage = SQLiteResultStorage(str(db_path))
    context = DummySurvey()

    storage.store_result(
        context,
        {
            "poll_id": "poll-1",
            "created": datetime(2024, 2, 1, tzinfo=timezone.utc),
            "result": {"q1": "a"},
        },
    )
    storage.store_result(
        context,
        {
            "poll_id": "poll-2",
            "created": datetime(2024, 2, 2, tzinfo=timezone.utc),
            "result": {"q1": "b"},
        },
    )

    results = storage.list_results(context)
    assert [r["poll_id"] for r in results] == ["poll-2", "poll-1"]

    status = storage.delete_results(context, ["poll-2", "missing"])
    assert status["deleted"] == ["poll-2"]
    assert status["missing"] == ["missing"]
    assert storage.get_result(context, "poll-2") is None

    storage.clear_results(context)
    assert storage.list_results(context) == []
