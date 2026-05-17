import logging
from typing import Any

from fastapi import APIRouter, Query, Request

from src.db.repository import get_metric_summary
from src.engine.compaction import compaction_status

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/metrics/summary", tags=["metrics"])
async def metrics_summary(
    request: Request,
    window: int = Query(300, ge=60, le=86400, description="Rolling window in seconds"),
) -> dict[str, Any]:
    """Return an aggregated metrics snapshot for the specified window.

    Args:
        request: FastAPI request carrying app state.
        window: Rolling window size in seconds (60-86400).

    Returns:
        MetricSummary as a JSON-serialisable dict.
    """
    conn = request.app.state.db_conn
    summary = get_metric_summary(conn, window_seconds=window)
    return summary.model_dump(mode="json")


@router.get("/metrics/compaction", tags=["metrics"])
async def compaction_history(request: Request) -> dict[str, Any]:
    """Return the last 50 compaction log entries.

    Args:
        request: FastAPI request carrying app state.

    Returns:
        Dict with list of compaction log rows.
    """
    conn = request.app.state.db_conn
    history = compaction_status(conn)
    return {"total": len(history), "history": history}
