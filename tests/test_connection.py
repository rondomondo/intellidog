import tempfile
from pathlib import Path

import pytest

from src.db.connection import close_connection, get_connection, reset_connection


@pytest.fixture(autouse=True)
def _isolate() -> None:  # type: ignore[return]
    reset_connection()
    yield
    reset_connection()


def test_get_connection_creates_file(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    assert conn is not None
    assert db_path.exists()
    close_connection()


def test_get_connection_returns_same_instance(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn1 = get_connection(db_path)
    conn2 = get_connection(db_path)
    assert conn1 is conn2
    close_connection()


def test_get_connection_creates_parent_dirs(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "deep" / "test.db"
    conn = get_connection(db_path)
    assert db_path.exists()
    close_connection()


def test_close_connection_allows_new_open(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn1 = get_connection(db_path)
    close_connection()
    conn2 = get_connection(db_path)
    assert conn1 is not conn2
    close_connection()


def test_close_connection_when_none_is_noop() -> None:
    close_connection()  # should not raise


def test_reset_connection_clears_state(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    get_connection(db_path)
    reset_connection()
    # After reset, a new call should open a fresh connection
    from src.db import connection as conn_module

    assert conn_module._connection is None


def test_wal_mode_enabled(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"
    close_connection()
