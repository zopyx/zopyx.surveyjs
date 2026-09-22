from __future__ import annotations

import logging
from typing import Optional

from .storage import (
    SQLResultStorage,
    ZODBResultStorage,
    _get_database_uri,
)

logger = logging.getLogger(__name__)


def migrate_zodb_results_to_rdbms(context, database_uri: Optional[str] = None) -> int:
    """Copy all ZODB results for a survey into a relational database."""
    zodb_storage = ZODBResultStorage()
    sql_storage = SQLResultStorage(database_uri or _get_database_uri())
    results = zodb_storage.list_results(context)
    for entry in results:
        sql_storage.store_result(context, entry)
    logger.info(
        "Migrated %s result(s) from ZODB to relational DB for %s",
        len(results),
        getattr(context, "absolute_url", lambda: repr(context))(),
    )
    return len(results)
