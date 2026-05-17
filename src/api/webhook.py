import logging
from collections import deque
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request, status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])

_MAX_ENTRIES = 10
_recent: deque[dict[str, Any]] = deque(maxlen=_MAX_ENTRIES)


@router.post("/grafana", status_code=status.HTTP_204_NO_CONTENT)
async def receive_grafana_webhook(request: Request) -> None:
    """Accept an incoming Grafana alert webhook and store it for inspection.

    Grafana POSTs a JSON payload whenever an alert fires or resolves. This
    endpoint records the last 10 payloads so operators can verify the
    integration is working without needing an external sink.

    Args:
        request: FastAPI request; body is parsed as raw JSON.
    """
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        body = {}

    entry: dict[str, Any] = {
        "received_at": datetime.now(UTC).isoformat(),
        "remote_addr": request.client.host if request.client else "unknown",
        "payload": body,
    }
    _recent.appendleft(entry)
    logger.info(
        "Grafana webhook received: state=%s alert_count=%d",
        body.get("state", body.get("status", "unknown")),
        len(body.get("alerts", [])),
    )


@router.get("/grafana")
async def list_grafana_webhooks() -> dict[str, Any]:
    """Return the last 10 Grafana webhook payloads received.

    Returns:
        Dict with count and ordered list of webhook entries (newest first).
    """
    return {
        "count": len(_recent),
        "max": _MAX_ENTRIES,
        "entries": list(_recent),
    }
