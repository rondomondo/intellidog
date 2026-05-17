import logging
import sqlite3
from datetime import UTC, datetime, timedelta

from src.db.repository import mark_compacted

logger = logging.getLogger(__name__)

COMPACTABLE_TABLES = ("events", "logs")


def run_compaction(conn: sqlite3.Connection, compaction_days: int) -> dict[str, int]:
    """Mark records older than compaction_days as compacted.

    Records are never deleted -- compaction only sets the compacted flag
    so that dashboards and queries can filter them as needed.

    Args:
        conn: Open SQLite connection.
        compaction_days: Records older than this many days are marked compacted.

    Returns:
        Dict mapping table name to the count of rows marked compacted.
    """
    cutoff = datetime.now(UTC) - timedelta(days=compaction_days)
    results: dict[str, int] = {}

    for table in COMPACTABLE_TABLES:
        try:
            marked = mark_compacted(conn, table, cutoff)
            results[table] = marked
            if marked:
                logger.info("Compaction: marked %d rows in '%s' (cutoff=%s)", marked, table, cutoff.isoformat())
            else:
                logger.debug("Compaction: no rows to compact in '%s'", table)
        except Exception as exc:
            logger.error("Compaction failed for table '%s': %s", table, exc)
            results[table] = 0

    return results


def compaction_status(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """Return the compaction log history.

    Args:
        conn: Open SQLite connection.

    Returns:
        List of dicts from the compaction_log table, most recent first.
    """
    rows = conn.execute(
        "SELECT table_name, records_marked, ran_at FROM compaction_log ORDER BY ran_at DESC LIMIT 50"
    ).fetchall()
    return [dict(r) for r in rows]
