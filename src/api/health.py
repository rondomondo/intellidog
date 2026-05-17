import logging
from typing import Any

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", tags=["ops"])
async def health(request: Request) -> dict[str, Any]:
    """Liveness and dependency health check.

    Returns:
        JSON object with status and per-dependency connectivity flags.
    """
    app_state = request.app.state

    db_ok = False
    try:
        conn = app_state.db_conn
        conn.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception as exc:
        logger.warning("Health: DB check failed: %s", exc)

    redis_ok: bool = False
    try:
        redis_ok = app_state.publisher.is_connected()
    except Exception as exc:
        logger.warning("Health: Redis check failed: %s", exc)

    llm_ok: bool = getattr(app_state.llm_analyser, "_enabled", False)

    overall = "ok" if (db_ok and redis_ok) else "degraded"

    return {
        "status": overall,
        "components": {
            "database": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
            "llm": "ok" if llm_ok else "disabled",
        },
    }
