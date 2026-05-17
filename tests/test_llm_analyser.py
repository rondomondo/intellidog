import sqlite3
from datetime import UTC, datetime
from unittest.mock import MagicMock

from src.db.repository import insert_event
from src.engine.llm_analyser import LLMAnalyser
from src.models.event import EventEntry, EventSeverity, EventType


def _event() -> EventEntry:
    return EventEntry(
        source="test-svc",
        event_type=EventType.error,
        severity=EventSeverity.critical,
        message="Critical failure in payment pipeline",
        timestamp=datetime.now(UTC),
    )


def test_llm_disabled_when_no_key(db_conn: sqlite3.Connection) -> None:
    analyser = LLMAnalyser(api_key="", model="claude-sonnet-4-6")
    analyser.connect()
    assert not analyser.is_enabled()


def test_llm_analyse_returns_empty_when_disabled(db_conn: sqlite3.Connection) -> None:
    analyser = LLMAnalyser(api_key="", model="claude-sonnet-4-6")
    analyser.connect()
    results = analyser.analyse(db_conn)
    assert results == []


def test_llm_analyse_no_events_skips_call(db_conn: sqlite3.Connection) -> None:
    analyser = LLMAnalyser(api_key="sk-fake", model="claude-sonnet-4-6", enabled=True)
    mock_client = MagicMock()
    analyser._client = mock_client
    analyser._enabled = True
    results = analyser.analyse(db_conn)
    assert results == []
    mock_client.messages.create.assert_not_called()


def test_llm_analyse_returns_anomalies(db_conn: sqlite3.Connection) -> None:
    insert_event(db_conn, _event())
    analyser = LLMAnalyser(api_key="sk-fake", model="claude-sonnet-4-6", enabled=True)
    import json

    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text=json.dumps(
                {
                    "anomalies": [
                        {
                            "title": "Payment cascade failure",
                            "severity": "critical",
                            "explanation": "Multiple critical errors from payment-service in a short window.",
                            "affected_sources": ["test-svc"],
                            "event_ids": [],
                        }
                    ],
                    "summary": "Possible cascade failure detected.",
                }
            )
        )
    ]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    analyser._client = mock_client
    analyser._enabled = True

    alerts = analyser.analyse(db_conn)
    assert len(alerts) == 1
    assert alerts[0].source == "llm"
    assert alerts[0].rule_name == "Payment cascade failure"


def test_llm_analyse_handles_api_error(db_conn: sqlite3.Connection) -> None:
    insert_event(db_conn, _event())
    analyser = LLMAnalyser(api_key="sk-fake", model="claude-sonnet-4-6", enabled=True)
    import anthropic

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = anthropic.APIError("rate limited", request=MagicMock(), body=None)
    analyser._client = mock_client
    analyser._enabled = True

    alerts = analyser.analyse(db_conn)
    assert alerts == []


def test_llm_analyse_handles_json_parse_error(db_conn: sqlite3.Connection) -> None:
    insert_event(db_conn, _event())
    analyser = LLMAnalyser(api_key="sk-fake", model="claude-sonnet-4-6", enabled=True)
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="not valid json {{{{")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    analyser._client = mock_client
    analyser._enabled = True

    alerts = analyser.analyse(db_conn)
    assert alerts == []
