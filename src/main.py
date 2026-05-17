import asyncio
import logging
import logging.config
import sqlite3
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from src.api import alerts, health, ingest, metrics, query, webhook
from src.bus.publisher import Publisher
from src.bus.subscriber import Subscriber
from src.config import get_settings
from src.db.connection import get_connection
from src.db.migrations import run_migrations
from src.db.repository import upsert_rule
from src.engine.alert_engine import evaluate_all_rules
from src.engine.compaction import run_compaction
from src.engine.llm_analyser import LLMAnalyser, MockLLMAnalyser
from src.rules.loader import load_rules_from_dir

ALERT_EVAL_INTERVAL_SECONDS = 30


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s UTC %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


async def _alert_evaluation_loop(app: FastAPI) -> None:
    """Periodically evaluate all alert rules and run LLM analysis."""
    settings = get_settings()
    while True:
        await asyncio.sleep(ALERT_EVAL_INTERVAL_SECONDS)
        try:
            conn: sqlite3.Connection = app.state.db_conn
            evaluate_all_rules(conn)
        except Exception as exc:
            logging.getLogger(__name__).error("Alert eval error: %s", exc)
        try:
            await asyncio.sleep(0)
            app.state.llm_analyser.analyse(app.state.db_conn)
        except Exception as exc:
            logging.getLogger(__name__).error("LLM analysis error: %s", exc)


async def _queue_consumer_loop(app: FastAPI) -> None:
    """Drain the Redis subscriber queue and log received messages."""
    logger = logging.getLogger(__name__)
    queue: asyncio.Queue[dict[str, Any]] = app.state.subscriber.queue
    while True:
        try:
            message = await queue.get()
            msg_type = message.get("type", "unknown")
            logger.debug("Bus message received: type=%s", msg_type)
            queue.task_done()
        except Exception as exc:
            logger.error("Queue consumer error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan: start all background services on startup, shut down cleanly."""
    settings = get_settings()
    _configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    # Database
    conn = get_connection(settings.db_path)
    run_migrations(conn)
    app.state.db_conn = conn

    # Load rules from disk into DB
    file_rules = load_rules_from_dir(settings.rules_dir)
    for rule in file_rules:
        upsert_rule(conn, rule)
    logger.info("Loaded %d rules from disk", len(file_rules))

    # Redis publisher
    publisher = Publisher(redis_url=settings.redis_url, channel=settings.redis_channel)
    try:
        publisher.connect()
    except Exception as exc:
        logger.warning("Redis publisher unavailable at startup: %s -- continuing degraded", exc)
    app.state.publisher = publisher

    # Redis subscriber
    loop = asyncio.get_running_loop()
    subscriber = Subscriber(redis_url=settings.redis_url, channel=settings.redis_channel, loop=loop)
    try:
        subscriber.start()
    except Exception as exc:
        logger.warning("Redis subscriber failed to start: %s", exc)
    app.state.subscriber = subscriber

    # LLM analyser -- fall back to heuristic mock when no API key is configured
    if settings.llm_enabled and not settings.llm_api_key:
        llm: LLMAnalyser = MockLLMAnalyser(model=settings.llm_model)
    else:
        llm = LLMAnalyser(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            enabled=settings.llm_enabled,
        )
    llm.connect()
    app.state.llm_analyser = llm

    # Alert engine placeholder stored on state (rules reloaded from DB each cycle)
    app.state.alert_engine = type("_Engine", (), {"reload_rules": lambda self, c: None})()

    # Run compaction once at startup
    try:
        run_compaction(conn, settings.compaction_days)
    except Exception as exc:
        logger.warning("Startup compaction error: %s", exc)

    # Background tasks
    eval_task = asyncio.create_task(_alert_evaluation_loop(app))
    consumer_task = asyncio.create_task(_queue_consumer_loop(app))

    logger.info("Intellidog started -- env=%s db=%s", settings.env, settings.db_path)

    yield

    # Shutdown
    eval_task.cancel()
    consumer_task.cancel()
    subscriber.stop()
    publisher.close()
    logger.info("Intellidog shutdown complete")


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application.

    Returns:
        Configured FastAPI instance with all routers registered.
    """
    app = FastAPI(
        title="Intellidog",
        description="Intelligent Observability & Event Watchdog",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(query.router)
    app.include_router(alerts.router)
    app.include_router(metrics.router)
    app.include_router(webhook.router)
    return app


app = create_app()


def run() -> None:
    """Entry point for running the server via CLI."""
    import uvicorn

    settings = get_settings()
    uvicorn.run("src.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
