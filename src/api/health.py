import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)
router = APIRouter()

_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Intellidog</title>
  <style>
    body { font-family: monospace; max-width: 640px; margin: 48px auto; padding: 0 16px; background: #0d1117; color: #e6edf3; }
    h1   { font-size: 1.4rem; border-bottom: 1px solid #30363d; padding-bottom: 8px; }
    h2   { font-size: 1rem; color: #8b949e; margin-top: 24px; }
    ul   { list-style: none; padding: 0; }
    li   { margin: 6px 0; }
    a    { color: #58a6ff; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .tag { font-size: 0.75rem; color: #8b949e; margin-left: 6px; }
    footer { margin-top: 40px; font-size: 0.8rem; color: #484f58; }
  </style>
</head>
<body>
  <h1>&#x1F436; Intellidog</h1>
  <p>Intelligent Observability &amp; Event Watchdog</p>

  <h2>Ops</h2>
  <ul>
    <li><a href="/health">/health</a> <span class="tag">liveness + dependency status</span></li>
    <li><a href="/docs">/docs</a> <span class="tag">interactive API docs (Swagger)</span></li>
    <li><a href="/redoc">/redoc</a> <span class="tag">ReDoc API reference</span></li>
  </ul>

  <h2>Metrics</h2>
  <ul>
    <li><a href="/metrics/summary">/metrics/summary</a> <span class="tag">rolling rate, latency, severity breakdown</span></li>
    <li><a href="/metrics/compaction">/metrics/compaction</a> <span class="tag">compaction log</span></li>
  </ul>

  <h2>Query</h2>
  <ul>
    <li><a href="/events">/events</a> <span class="tag">recent application events</span></li>
    <li><a href="/logs">/logs</a> <span class="tag">recent log entries</span></li>
    <li><a href="/notifications">/notifications</a> <span class="tag">recent notifications</span></li>
  </ul>

  <h2>Alerts &amp; Rules</h2>
  <ul>
    <li><a href="/alerts">/alerts</a> <span class="tag">fired alerts</span></li>
    <li><a href="/rules">/rules</a> <span class="tag">configured alert rules</span></li>
  </ul>

  <h2>Webhook</h2>
  <ul>
    <li><a href="/webhook/grafana">/webhook/grafana</a> <span class="tag">last 10 Grafana webhook payloads</span></li>
  </ul>

  <footer>POST /events &nbsp;|&nbsp; POST /logs &nbsp;|&nbsp; POST /notifications &nbsp;|&nbsp; POST /rules &nbsp;|&nbsp; POST /webhook/grafana</footer>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index() -> HTMLResponse:
    """Serve a simple HTML index of all GETable API routes."""
    return HTMLResponse(content=_INDEX_HTML)


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
