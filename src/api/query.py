import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, Request

from src.db.repository import query_events, query_logs, query_notifications

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/events", tags=["query"])
async def get_events(
    request: Request,
    source: str | None = Query(None),
    severity: str | None = Query(None),
    event_type: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Query application events with optional filters.

    Args:
        request: FastAPI request carrying app state.
        source: Filter by event source.
        severity: Filter by severity level.
        event_type: Filter by event type.
        since: Include events at or after this UTC datetime.
        until: Include events at or before this UTC datetime.
        limit: Max results (1-1000).
        offset: Pagination offset.

    Returns:
        Dict with total count and list of event dicts.
    """
    conn = request.app.state.db_conn
    events = query_events(
        conn,
        source=source,
        severity=severity,
        event_type=event_type,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return {"total": len(events), "offset": offset, "events": events}


@router.get("/logs", tags=["query"])
async def get_logs(
    request: Request,
    host: str | None = Query(None),
    service: str | None = Query(None),
    level: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Query system log entries with optional filters.

    Args:
        request: FastAPI request carrying app state.
        host: Filter by host name.
        service: Filter by service name.
        level: Filter by log level.
        since: Include logs at or after this UTC datetime.
        until: Include logs at or before this UTC datetime.
        limit: Max results (1-1000).
        offset: Pagination offset.

    Returns:
        Dict with total count and list of log entry dicts.
    """
    conn = request.app.state.db_conn
    logs = query_logs(
        conn, host=host, service=service, level=level, since=since, until=until, limit=limit, offset=offset
    )
    return {"total": len(logs), "offset": offset, "logs": logs}


@router.get("/notifications", tags=["query"])
async def get_notifications(
    request: Request,
    channel: str | None = Query(None),
    source_system: str | None = Query(None),
    since: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Query notification events with optional filters."""
    conn = request.app.state.db_conn
    notifs = query_notifications(
        conn, channel=channel, source_system=source_system, since=since, limit=limit, offset=offset
    )
    return {"total": len(notifs), "offset": offset, "notifications": notifs}
