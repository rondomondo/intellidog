import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from src.db.repository import insert_alert, query_rules
from src.models.alert import Alert, AlertRule, AlertSeverity, RuleCondition

logger = logging.getLogger(__name__)

OPERATORS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _evaluate_condition(conn: sqlite3.Connection, condition: RuleCondition) -> tuple[bool, float, dict[str, Any]]:
    """Evaluate a single rule condition against the current DB state.

    Args:
        conn: Open SQLite connection.
        condition: Rule condition to evaluate.

    Returns:
        Tuple of (triggered, current_value, detail_dict).
    """
    since = _now_utc() - timedelta(seconds=condition.window_seconds)
    since_str = since.isoformat()
    op_fn = OPERATORS.get(condition.operator)
    if op_fn is None:
        logger.warning("Unknown operator: %s", condition.operator)
        return False, 0.0, {}

    metric = condition.metric
    current: float = 0.0
    details: dict[str, Any] = {"metric": metric, "threshold": condition.threshold, "operator": condition.operator}

    if metric == "events_per_minute":
        clauses = ["timestamp >= ?"]
        params: list[Any] = [since_str]
        if condition.event_type:
            clauses.append("event_type = ?")
            params.append(condition.event_type)
        if condition.source:
            clauses.append("source = ?")
            params.append(condition.source)
        row = conn.execute(f"SELECT COUNT(*) FROM events WHERE {' AND '.join(clauses)}", params).fetchone()
        count = row[0] or 0
        current = (count / condition.window_seconds) * 60
        details["count"] = count
        details["window_seconds"] = condition.window_seconds

    elif metric == "error_rate":
        total_row = conn.execute("SELECT COUNT(*) FROM events WHERE timestamp >= ?", (since_str,)).fetchone()
        total = total_row[0] or 0
        error_row = conn.execute(
            "SELECT COUNT(*) FROM events WHERE timestamp >= ? AND (severity='critical' OR severity='high')",
            (since_str,),
        ).fetchone()
        errors = error_row[0] or 0
        current = (errors / total * 100) if total > 0 else 0.0
        details.update({"total_events": total, "error_events": errors})

    elif metric in ("p95", "p99"):
        field = condition.field or "duration_ms"
        rows = conn.execute(
            "SELECT payload FROM events WHERE timestamp >= ? AND json_extract(payload, ?) IS NOT NULL",
            (since_str, f"$.{field}"),
        ).fetchall()
        values = sorted(json.loads(r[0]).get(field, 0) for r in rows if r[0])
        n = len(values)
        if n:
            pct = 0.95 if metric == "p95" else 0.99
            current = values[int(n * pct)]
        details.update({"field": field, "sample_count": n})

    elif metric == "distinct_sources":
        row = conn.execute("SELECT COUNT(DISTINCT source) FROM events WHERE timestamp >= ?", (since_str,)).fetchone()
        current = float(row[0] or 0)

    elif metric == "log_error_rate":
        total_row = conn.execute("SELECT COUNT(*) FROM logs WHERE timestamp >= ?", (since_str,)).fetchone()
        total = total_row[0] or 0
        err_row = conn.execute(
            "SELECT COUNT(*) FROM logs WHERE timestamp >= ? AND level='ERROR'", (since_str,)
        ).fetchone()
        errors = err_row[0] or 0
        current = (errors / total * 100) if total > 0 else 0.0
        details.update({"total_logs": total, "error_logs": errors})

    details["current_value"] = round(current, 4)
    triggered = op_fn(current, condition.threshold)
    return triggered, current, details


def evaluate_all_rules(conn: sqlite3.Connection) -> list[Alert]:
    """Evaluate all enabled rules against current DB state and persist any triggered alerts.

    Args:
        conn: Open SQLite connection.

    Returns:
        List of Alert objects that were newly triggered this cycle.
    """
    rule_rows = query_rules(conn, enabled_only=True)
    fired: list[Alert] = []

    for row in rule_rows:
        try:
            condition = RuleCondition(**row["condition"])
            triggered, current_val, details = _evaluate_condition(conn, condition)
            if not triggered:
                continue

            alert = Alert(
                rule_id=row["rule_id"],
                rule_name=row["name"],
                severity=AlertSeverity(row["severity"]),
                message=(
                    f"Rule '{row['name']}' triggered: "
                    f"{condition.metric} {condition.operator} {condition.threshold} "
                    f"(current={round(current_val, 4)})"
                ),
                details=details,
                source="engine",
                fired_at=_now_utc(),
            )
            insert_alert(conn, alert)
            fired.append(alert)
            logger.info("Alert fired: %s [%s]", alert.rule_name, alert.severity.value)
        except Exception as exc:
            logger.error("Rule evaluation error (rule_id=%s): %s", row.get("rule_id"), exc)

    return fired


def load_rules_as_objects(conn: sqlite3.Connection) -> list[AlertRule]:
    """Return all enabled rules as AlertRule model objects.

    Args:
        conn: Open SQLite connection.

    Returns:
        List of AlertRule instances.
    """
    from src.db.repository import load_rules_from_db

    return load_rules_from_db(conn)
