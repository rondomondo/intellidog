import sqlite3
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.db.connection import reset_connection
from src.db.migrations import run_migrations


@pytest.fixture()
def db_conn() -> Generator[sqlite3.Connection, None, None]:
    """Provide an in-memory SQLite connection with schema applied."""
    reset_connection()
    conn = sqlite3.connect(":memory:", check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    run_migrations(conn)
    yield conn
    conn.close()
    reset_connection()


@pytest.fixture()
def mock_publisher() -> MagicMock:
    """Return a mock Publisher that does nothing."""
    pub = MagicMock()
    pub.is_connected.return_value = True
    return pub


@pytest.fixture()
def mock_subscriber() -> MagicMock:
    """Return a mock Subscriber."""
    sub = MagicMock()
    sub.is_connected.return_value = True
    return sub


@pytest.fixture()
def mock_llm() -> MagicMock:
    """Return a mock LLMAnalyser that reports enabled=False."""
    llm = MagicMock()
    llm._enabled = False
    llm.is_enabled.return_value = False
    llm.analyse.return_value = []
    return llm


@pytest.fixture()
def app_client(
    db_conn: sqlite3.Connection, mock_publisher: MagicMock, mock_subscriber: MagicMock, mock_llm: MagicMock
) -> Generator[TestClient, None, None]:
    """Provide a TestClient with all dependencies wired to mocks/in-memory DB."""
    from src.main import create_app

    application = create_app()

    class _FakeEngine:
        def reload_rules(self, conn: sqlite3.Connection) -> None:
            pass

    with TestClient(application, raise_server_exceptions=True) as client:
        application.state.db_conn = db_conn
        application.state.publisher = mock_publisher
        application.state.subscriber = mock_subscriber
        application.state.llm_analyser = mock_llm
        application.state.alert_engine = _FakeEngine()
        yield client
