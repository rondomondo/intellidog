import json
import logging
from datetime import datetime
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request, status

from src.db.repository import disable_rule, query_alerts, query_rules, upsert_rule
from src.models.alert import AlertRule, AlertSeverity, RuleCondition

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/alerts", tags=["alerts"])
async def get_alerts(
    request: Request,
    alert_status: str | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List alerts with optional status and time filters.

    Args:
        request: FastAPI request carrying app state.
        alert_status: Filter by alert status (active, resolved, suppressed).
        since: Include alerts fired at or after this UTC datetime.
        limit: Maximum number of alerts to return.

    Returns:
        Dict with count and list of alert dicts.
    """
    conn = request.app.state.db_conn
    alerts = query_alerts(conn, status=alert_status, since=since, limit=limit)
    return {"total": len(alerts), "alerts": alerts}


@router.get("/alerts/{alert_id}", tags=["alerts"])
async def get_alert(request: Request, alert_id: str) -> dict[str, Any]:
    """Retrieve a single alert by ID.

    Args:
        request: FastAPI request carrying app state.
        alert_id: UUID of the alert to retrieve.

    Returns:
        Alert dict or 404 if not found.
    """
    conn = request.app.state.db_conn
    rows = conn.execute("SELECT * FROM alerts WHERE alert_id=?", (alert_id,)).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Alert not found")
    d = dict(rows[0])
    d["details"] = json.loads(d.get("details") or "{}")
    return d


@router.get("/rules", tags=["rules"])
async def get_rules(request: Request, enabled_only: bool = False) -> dict[str, Any]:
    """List all alert rules.

    Args:
        request: FastAPI request carrying app state.
        enabled_only: When True, return only enabled rules.

    Returns:
        Dict with count and list of rule dicts.
    """
    conn = request.app.state.db_conn
    rules = query_rules(conn, enabled_only=enabled_only)
    return {"total": len(rules), "rules": rules}


@router.post("/rules", status_code=status.HTTP_201_CREATED, tags=["rules"])
async def create_rule(request: Request) -> dict[str, Any]:
    """Add or update an alert rule from a JSON or YAML body.

    Accepts Content-Type: application/json or application/yaml (or text/yaml).
    The body must contain a single rule object matching the AlertRule schema.

    Returns:
        Dict with the rule_id of the created/updated rule.
    """
    conn = request.app.state.db_conn
    content_type = request.headers.get("content-type", "application/json")
    raw_bytes = await request.body()
    raw_text = raw_bytes.decode("utf-8")

    try:
        if "yaml" in content_type:
            data: dict[str, Any] = yaml.safe_load(raw_text)
        else:
            data = json.loads(raw_text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise HTTPException(status_code=422, detail=f"Body parse error: {exc}") from exc

    try:
        condition = RuleCondition(**data.get("condition", {}))
        rule = AlertRule(
            id=data.get("id", ""),
            name=data["name"],
            description=data.get("description", ""),
            condition=condition,
            severity=AlertSeverity(data.get("severity", "medium")),
            enabled=bool(data.get("enabled", True)),
            source="api",
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Rule validation error: {exc}") from exc

    upsert_rule(conn, rule)

    engine = request.app.state.alert_engine
    if hasattr(engine, "reload_rules"):
        engine.reload_rules(conn)

    logger.info("Rule created/updated via API: %s", rule.id)
    return {"rule_id": rule.id, "name": rule.name}


@router.delete("/rules/{rule_id}", tags=["rules"])
async def delete_rule(request: Request, rule_id: str) -> dict[str, Any]:
    """Soft-disable a rule by setting enabled=0.

    Rules are never hard-deleted to preserve audit history.

    Args:
        request: FastAPI request carrying app state.
        rule_id: ID of the rule to disable.

    Returns:
        Dict confirming the rule_id was disabled.
    """
    conn = request.app.state.db_conn
    found = disable_rule(conn, rule_id)
    if not found:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"rule_id": rule_id, "status": "disabled"}
