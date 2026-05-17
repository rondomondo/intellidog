import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from src.db.repository import insert_event, insert_log, insert_notification
from src.models.event import EventEntry, LogEntry, NotificationEntry

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/events", status_code=status.HTTP_201_CREATED, tags=["ingest"])
async def ingest_events(request: Request, body: EventEntry | list[EventEntry]) -> dict[str, Any]:
    """Ingest one or a batch of application events.

    Args:
        request: FastAPI request carrying app state.
        body: Single EventEntry or list of EventEntry objects.

    Returns:
        Dict with accepted count and list of accepted event_ids.
    """
    events = body if isinstance(body, list) else [body]
    conn = request.app.state.db_conn
    publisher = request.app.state.publisher
    accepted: list[str] = []
    for event in events:
        try:
            insert_event(conn, event)
            publisher.publish({"type": "event", "data": event.model_dump(mode="json")})
            accepted.append(event.event_id)
            logger.debug("Event ingested: %s source=%s", event.event_id, event.source)
        except Exception as exc:
            logger.error("Failed to ingest event %s: %s", event.event_id, exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"accepted": len(accepted), "event_ids": accepted}


@router.post("/logs", status_code=status.HTTP_201_CREATED, tags=["ingest"])
async def ingest_logs(request: Request, body: LogEntry | list[LogEntry]) -> dict[str, Any]:
    """Ingest one or a batch of system log entries.

    Args:
        request: FastAPI request carrying app state.
        body: Single LogEntry or list of LogEntry objects.

    Returns:
        Dict with accepted count and list of accepted log_ids.
    """
    logs = body if isinstance(body, list) else [body]
    conn = request.app.state.db_conn
    publisher = request.app.state.publisher
    accepted: list[str] = []
    for log in logs:
        try:
            insert_log(conn, log)
            publisher.publish({"type": "log", "data": log.model_dump(mode="json")})
            accepted.append(log.log_id)
            logger.debug("Log ingested: %s service=%s", log.log_id, log.service)
        except Exception as exc:
            logger.error("Failed to ingest log %s: %s", log.log_id, exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"accepted": len(accepted), "log_ids": accepted}


@router.post("/notifications", status_code=status.HTTP_201_CREATED, tags=["ingest"])
async def ingest_notifications(request: Request, body: NotificationEntry | list[NotificationEntry]) -> dict[str, Any]:
    """Ingest one or a batch of async notification events.

    Args:
        request: FastAPI request carrying app state.
        body: Single NotificationEntry or list of NotificationEntry objects.

    Returns:
        Dict with accepted count and list of accepted notification_ids.
    """
    notifs = body if isinstance(body, list) else [body]
    conn = request.app.state.db_conn
    publisher = request.app.state.publisher
    accepted: list[str] = []
    for notif in notifs:
        try:
            insert_notification(conn, notif)
            publisher.publish({"type": "notification", "data": notif.model_dump(mode="json")})
            accepted.append(notif.notification_id)
        except Exception as exc:
            logger.error("Failed to ingest notification %s: %s", notif.notification_id, exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"accepted": len(accepted), "notification_ids": accepted}
