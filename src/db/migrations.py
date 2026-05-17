import logging
import sqlite3

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT    NOT NULL UNIQUE,
    source      TEXT    NOT NULL,
    event_type  TEXT    NOT NULL,
    severity    TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    payload     TEXT    NOT NULL DEFAULT '{}',
    tags        TEXT    NOT NULL DEFAULT '[]',
    timestamp   TEXT    NOT NULL,
    compacted   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id      TEXT    NOT NULL UNIQUE,
    host        TEXT    NOT NULL,
    service     TEXT    NOT NULL,
    level       TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    process     TEXT    NOT NULL DEFAULT '',
    pid         INTEGER,
    tags        TEXT    NOT NULL DEFAULT '[]',
    timestamp   TEXT    NOT NULL,
    compacted   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS notifications (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id     TEXT    NOT NULL UNIQUE,
    channel             TEXT    NOT NULL,
    source_system       TEXT    NOT NULL,
    title               TEXT    NOT NULL,
    body                TEXT    NOT NULL,
    metadata            TEXT    NOT NULL DEFAULT '{}',
    timestamp           TEXT    NOT NULL,
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id    TEXT    NOT NULL UNIQUE,
    rule_id     TEXT,
    rule_name   TEXT    NOT NULL,
    severity    TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'active',
    message     TEXT    NOT NULL,
    details     TEXT    NOT NULL DEFAULT '{}',
    source      TEXT    NOT NULL DEFAULT 'engine',
    fired_at    TEXT    NOT NULL,
    resolved_at TEXT,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id     TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    condition   TEXT    NOT NULL,
    severity    TEXT    NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    source      TEXT    NOT NULL DEFAULT 'config',
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS compaction_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name      TEXT    NOT NULL,
    records_marked  INTEGER NOT NULL DEFAULT 0,
    ran_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp  ON events (timestamp);
CREATE INDEX IF NOT EXISTS idx_events_source     ON events (source);
CREATE INDEX IF NOT EXISTS idx_events_severity   ON events (severity);
CREATE INDEX IF NOT EXISTS idx_events_compacted  ON events (compacted);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp    ON logs (timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_level        ON logs (level);
CREATE INDEX IF NOT EXISTS idx_alerts_status     ON alerts (status);
CREATE INDEX IF NOT EXISTS idx_alerts_fired_at   ON alerts (fired_at);
"""


def run_migrations(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if they do not already exist.

    Args:
        conn: Open SQLite connection to migrate.
    """
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    logger.info("Database migrations applied")
