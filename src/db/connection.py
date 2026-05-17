import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_connection: sqlite3.Connection | None = None


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Return (or create) the shared SQLite connection in WAL mode.

    Args:
        db_path: Filesystem path to the SQLite database file.

    Returns:
        An open sqlite3.Connection configured for WAL and UTC timestamps.
    """
    global _connection
    if _connection is not None:
        return _connection

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA wal_autocheckpoint=100")
    _connection = conn
    logger.info("SQLite connection opened: %s (WAL mode)", db_path)
    return _connection


def close_connection() -> None:
    """Close and discard the shared connection."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
        logger.info("SQLite connection closed")


def reset_connection() -> None:
    """Force-close the connection so the next call to get_connection opens a fresh one.

    Used in tests to swap in an in-memory database.
    """
    global _connection
    _connection = None
