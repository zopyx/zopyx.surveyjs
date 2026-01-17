from __future__ import annotations

import logging
from typing import Optional

from .storage import SQLiteResultStorage, ZODBResultStorage, _get_sqlite_path

logger = logging.getLogger(__name__)


def migrate_zodb_results_to_sqlite(context, sqlite_path: Optional[str] = None) -> int:
    """Copy all ZODB results for a survey into SQLite."""
    zodb_storage = ZODBResultStorage()
    sqlite_storage = SQLiteResultStorage(sqlite_path or _get_sqlite_path())
    results = zodb_storage.list_results(context)
    for entry in results:
        sqlite_storage.store_result(context, entry)
    logger.info(
        "Migrated %s result(s) from ZODB to SQLite for %s",
        len(results),
        getattr(context, "absolute_url", lambda: repr(context))(),
    )
    return len(results)
