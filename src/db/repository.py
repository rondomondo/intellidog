import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from src.models.alert import Alert, AlertRule, AlertSeverity, RuleCondition
from src.models.event import EventEntry, LogEntry, NotificationEntry
from src.models.metric import MetricSummary, PercentileStats, RateStats, SourceStat

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SECONDS = 300


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _ts(dt: datetime) -> str:
    return dt.isoformat()


def insert_event(conn: sqlite3.Connection, event: EventEntry) -> None:
    """Persist a single EventEntry to the events table.

    Args:
        conn: Open SQLite connection.
        event: Validated EventEntry to store.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO events
            (event_id, source, event_type, severity, message, payload, tags, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.event_id,
            event.source,
            event.event_type.value,
            event.severity.value,
            event.message,
            json.dumps(event.payload, ensure_ascii=False),
            json.dumps(event.tags, ensure_ascii=False),
            _ts(event.timestamp),
        ),
    )
    conn.commit()


def insert_log(conn: sqlite3.Connection, log: LogEntry) -> None:
    """Persist a single LogEntry to the logs table.

    Args:
        conn: Open SQLite connection.
        log: Validated LogEntry to store.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO logs
            (log_id, host, service, level, message, process, pid, tags, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log.log_id,
            log.host,
            log.service,
            log.level.value,
            log.message,
            log.process,
            log.pid,
            json.dumps(log.tags, ensure_ascii=False),
            _ts(log.timestamp),
        ),
    )
    conn.commit()


def insert_notification(conn: sqlite3.Connection, notif: NotificationEntry) -> None:
    """Persist a single NotificationEntry to the notifications table.

    Args:
        conn: Open SQLite connection.
        notif: Validated NotificationEntry to store.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO notifications
            (notification_id, channel, source_system, title, body, metadata, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            notif.notification_id,
            notif.channel.value,
            notif.source_system,
            notif.title,
            notif.body,
            json.dumps(notif.metadata, ensure_ascii=False),
            _ts(notif.timestamp),
        ),
    )
    conn.commit()


def query_events(
    conn: sqlite3.Connection,
    source: str | None = None,
    severity: str | None = None,
    event_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query events with optional filters.

    Args:
        conn: Open SQLite connection.
        source: Filter by event source.
        severity: Filter by severity level.
        event_type: Filter by event type.
        since: Include only events at or after this UTC datetime.
        until: Include only events at or before this UTC datetime.
        limit: Maximum number of rows to return.
        offset: Number of rows to skip.

    Returns:
        List of event dicts with parsed payload and tags.
    """
    clauses = ["1=1"]
    params: list[Any] = []
    if source:
        clauses.append("source = ?")
        params.append(source)
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if since:
        clauses.append("timestamp >= ?")
        params.append(_ts(since))
    if until:
        clauses.append("timestamp <= ?")
        params.append(_ts(until))
    params.extend([limit, offset])
    rows = conn.execute(
        f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        params,
    ).fetchall()
    return [_parse_event_row(r) for r in rows]


def query_logs(
    conn: sqlite3.Connection,
    host: str | None = None,
    service: str | None = None,
    level: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query log entries with optional filters.

    Args:
        conn: Open SQLite connection.
        host: Filter by host.
        service: Filter by service name.
        level: Filter by log level.
        since: Include only logs at or after this UTC datetime.
        until: Include only logs at or before this UTC datetime.
        limit: Maximum number of rows to return.
        offset: Number of rows to skip.

    Returns:
        List of log entry dicts with parsed tags.
    """
    clauses = ["1=1"]
    params: list[Any] = []
    if host:
        clauses.append("host = ?")
        params.append(host)
    if service:
        clauses.append("service = ?")
        params.append(service)
    if level:
        clauses.append("level = ?")
        params.append(level)
    if since:
        clauses.append("timestamp >= ?")
        params.append(_ts(since))
    if until:
        clauses.append("timestamp <= ?")
        params.append(_ts(until))
    params.extend([limit, offset])
    rows = conn.execute(
        f"SELECT * FROM logs WHERE {' AND '.join(clauses)} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        params,
    ).fetchall()
    return [_parse_log_row(r) for r in rows]


def query_notifications(
    conn: sqlite3.Connection,
    channel: str | None = None,
    source_system: str | None = None,
    since: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query notification entries with optional filters."""
    clauses = ["1=1"]
    params: list[Any] = []
    if channel:
        clauses.append("channel = ?")
        params.append(channel)
    if source_system:
        clauses.append("source_system = ?")
        params.append(source_system)
    if since:
        clauses.append("timestamp >= ?")
        params.append(_ts(since))
    params.extend([limit, offset])
    rows = conn.execute(
        f"SELECT * FROM notifications WHERE {' AND '.join(clauses)} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def insert_alert(conn: sqlite3.Connection, alert: Alert) -> None:
    """Persist a fired alert.

    Args:
        conn: Open SQLite connection.
        alert: Alert to store.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO alerts
            (alert_id, rule_id, rule_name, severity, status, message, details, source, fired_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            alert.alert_id,
            alert.rule_id,
            alert.rule_name,
            alert.severity.value,
            alert.status.value,
            alert.message,
            json.dumps(alert.details, ensure_ascii=False),
            alert.source,
            _ts(alert.fired_at),
        ),
    )
    conn.commit()


def query_alerts(
    conn: sqlite3.Connection,
    status: str | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query alerts with optional status and time filters."""
    clauses = ["1=1"]
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if since:
        clauses.append("fired_at >= ?")
        params.append(_ts(since))
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM alerts WHERE {' AND '.join(clauses)} ORDER BY fired_at DESC LIMIT ?",
        params,
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["details"] = json.loads(d.get("details") or "{}")
        result.append(d)
    return result


def upsert_rule(conn: sqlite3.Connection, rule: AlertRule) -> None:
    """Insert or replace an alert rule.

    Args:
        conn: Open SQLite connection.
        rule: AlertRule to persist.
    """
    conn.execute(
        """
        INSERT INTO rules (rule_id, name, description, condition, severity, enabled, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(rule_id) DO UPDATE SET
            name=excluded.name,
            description=excluded.description,
            condition=excluded.condition,
            severity=excluded.severity,
            enabled=excluded.enabled
        """,
        (
            rule.id,
            rule.name,
            rule.description,
            rule.condition.model_dump_json(),
            rule.severity.value,
            int(rule.enabled),
            rule.source,
            _ts(rule.created_at),
        ),
    )
    conn.commit()


def query_rules(conn: sqlite3.Connection, enabled_only: bool = False) -> list[dict[str, Any]]:
    """Return all stored alert rules.

    Args:
        conn: Open SQLite connection.
        enabled_only: When True, only return rules with enabled=1.

    Returns:
        List of rule dicts with parsed condition.
    """
    sql = "SELECT * FROM rules"
    if enabled_only:
        sql += " WHERE enabled=1"
    rows = conn.execute(sql).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["condition"] = json.loads(d["condition"])
        result.append(d)
    return result


def disable_rule(conn: sqlite3.Connection, rule_id: str) -> bool:
    """Soft-disable a rule by setting enabled=0.

    Args:
        conn: Open SQLite connection.
        rule_id: ID of the rule to disable.

    Returns:
        True if a row was updated, False if rule_id was not found.
    """
    cur = conn.execute("UPDATE rules SET enabled=0 WHERE rule_id=?", (rule_id,))
    conn.commit()
    return cur.rowcount > 0


def get_metric_summary(conn: sqlite3.Connection, window_seconds: int = DEFAULT_WINDOW_SECONDS) -> MetricSummary:
    """Compute and return an aggregated metrics snapshot.

    Args:
        conn: Open SQLite connection.
        window_seconds: Rolling window size for rate calculations.

    Returns:
        MetricSummary populated from the current DB state.
    """
    since = datetime.now(UTC) - timedelta(seconds=window_seconds)
    since_str = _ts(since)

    rate_row = conn.execute(
        "SELECT COUNT(*) as total, SUM(CASE WHEN severity='critical' OR severity='high' THEN 1 ELSE 0 END) as errors "
        "FROM events WHERE timestamp >= ?",
        (since_str,),
    ).fetchone()
    total = rate_row["total"] or 0
    errors = rate_row["errors"] or 0
    per_minute = (total / window_seconds) * 60 if total else 0.0
    error_rate = (errors / total * 100) if total else 0.0

    severity_rows = conn.execute(
        "SELECT severity, COUNT(*) as cnt FROM events WHERE timestamp >= ? GROUP BY severity",
        (since_str,),
    ).fetchall()
    severity_breakdown = {r["severity"]: r["cnt"] for r in severity_rows}

    source_rows = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM events WHERE timestamp >= ? GROUP BY source ORDER BY cnt DESC LIMIT 10",
        (since_str,),
    ).fetchall()
    top_sources = [SourceStat(source=r["source"], count=r["cnt"]) for r in source_rows]

    latency = PercentileStats()
    payload_rows = conn.execute(
        "SELECT payload FROM events WHERE timestamp >= ? AND json_extract(payload, '$.duration_ms') IS NOT NULL",
        (since_str,),
    ).fetchall()
    if payload_rows:
        durations = sorted(json.loads(r["payload"]).get("duration_ms", 0) for r in payload_rows if r["payload"])
        n = len(durations)
        if n:
            latency = PercentileStats(
                p50=durations[int(n * 0.50)],
                p95=durations[int(n * 0.95)],
                p99=durations[int(n * 0.99)],
                min=durations[0],
                max=durations[-1],
                count=n,
            )

    active_alerts = conn.execute("SELECT COUNT(*) FROM alerts WHERE status='active'").fetchone()[0]
    hour_ago = _ts(datetime.now(UTC) - timedelta(hours=1))
    llm_anomalies = conn.execute(
        "SELECT COUNT(*) FROM alerts WHERE source='llm' AND fired_at >= ?", (hour_ago,)
    ).fetchone()[0]

    return MetricSummary(
        window_seconds=window_seconds,
        computed_at=datetime.now(UTC),
        rate=RateStats(
            total=total,
            per_minute=round(per_minute, 2),
            error_count=errors,
            error_rate_pct=round(error_rate, 2),
            window_seconds=window_seconds,
        ),
        severity_breakdown=severity_breakdown,
        top_sources=top_sources,
        latency=latency,
        active_alerts=active_alerts,
        llm_anomalies_last_hour=llm_anomalies,
    )


def mark_compacted(conn: sqlite3.Connection, table: str, before: datetime) -> int:
    """Mark old records as compacted without deleting them.

    Args:
        conn: Open SQLite connection.
        table: Table name to compact ('events' or 'logs').
        before: Records with timestamp before this UTC datetime are marked.

    Returns:
        Number of records marked as compacted.
    """
    cur = conn.execute(
        f"UPDATE {table} SET compacted=1 WHERE timestamp < ? AND compacted=0",
        (_ts(before),),
    )
    conn.commit()
    rows_marked = cur.rowcount
    conn.execute(
        "INSERT INTO compaction_log (table_name, records_marked) VALUES (?, ?)",
        (table, rows_marked),
    )
    conn.commit()
    return rows_marked


def _parse_event_row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["payload"] = json.loads(d.get("payload") or "{}")
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d


def _parse_log_row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d


def load_rules_from_db(conn: sqlite3.Connection) -> list[AlertRule]:
    """Load all enabled rules from the database as AlertRule objects.

    Args:
        conn: Open SQLite connection.

    Returns:
        List of AlertRule instances.
    """
    rows = query_rules(conn, enabled_only=True)
    rules = []
    for r in rows:
        try:
            rule = AlertRule(
                id=r["rule_id"],
                name=r["name"],
                description=r.get("description", ""),
                condition=RuleCondition(**r["condition"]),
                severity=AlertSeverity(r["severity"]),
                enabled=bool(r["enabled"]),
                source=r.get("source", "config"),
                created_at=datetime.fromisoformat(r["created_at"]).replace(tzinfo=UTC),
            )
            rules.append(rule)
        except Exception:
            logger.warning("Skipping malformed rule row: %s", r.get("rule_id"))
    return rules
