import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
import redis

from src.bus.subscriber import Subscriber


def _make_subscriber() -> Subscriber:
    loop = asyncio.new_event_loop()
    return Subscriber(redis_url="redis://localhost:6379/0", channel="test-channel", loop=loop)


def test_queue_property() -> None:
    sub = _make_subscriber()
    assert isinstance(sub.queue, asyncio.Queue)


def test_is_connected_no_thread() -> None:
    sub = _make_subscriber()
    assert sub.is_connected() is False


def test_is_connected_thread_not_alive() -> None:
    sub = _make_subscriber()
    dead_thread = threading.Thread(target=lambda: None)
    dead_thread.start()
    dead_thread.join()
    sub._thread = dead_thread
    assert sub.is_connected() is False


def test_is_connected_no_client() -> None:
    sub = _make_subscriber()
    alive_thread = threading.Thread(target=lambda: time.sleep(0.5), daemon=True)
    alive_thread.start()
    sub._thread = alive_thread
    sub._client = None
    assert sub.is_connected() is False
    alive_thread.join(timeout=1)


def test_is_connected_ping_error() -> None:
    sub = _make_subscriber()
    alive_thread = threading.Thread(target=lambda: time.sleep(0.5), daemon=True)
    alive_thread.start()
    sub._thread = alive_thread
    mock_client = MagicMock()
    mock_client.ping.side_effect = redis.exceptions.RedisError("timeout")
    sub._client = mock_client
    assert sub.is_connected() is False
    alive_thread.join(timeout=1)


def test_stop_without_start() -> None:
    sub = _make_subscriber()
    sub.stop()  # should not raise


def test_stop_closes_client() -> None:
    sub = _make_subscriber()
    mock_client = MagicMock()
    sub._client = mock_client
    sub.stop()
    mock_client.close.assert_called_once()


def test_stop_client_close_redis_error() -> None:
    sub = _make_subscriber()
    mock_client = MagicMock()
    mock_client.close.side_effect = redis.exceptions.RedisError("gone")
    sub._client = mock_client
    sub.stop()  # should not raise


def test_run_loop_stop_event_set_immediately() -> None:
    """Subscriber _run() exits immediately if stop_event is set before thread starts."""
    loop = asyncio.new_event_loop()
    sub = Subscriber(redis_url="redis://localhost:6379/0", channel="test-channel", loop=loop)
    sub._stop_event.set()

    thread = threading.Thread(target=sub._run, daemon=True)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_run_loop_redis_error_then_stop() -> None:
    """Subscriber _run() handles RedisError then exits cleanly via stop_event."""
    loop = asyncio.new_event_loop()
    sub = Subscriber(redis_url="redis://localhost:6379/0", channel="test-channel", loop=loop)

    call_count = 0

    def fake_from_url(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        mock_client = MagicMock()
        mock_pubsub = MagicMock()
        mock_pubsub.listen.side_effect = redis.exceptions.RedisError("connection refused")
        mock_client.pubsub.return_value = mock_pubsub
        # Stop after first error so test doesn't spin indefinitely
        sub._stop_event.set()
        return mock_client

    with patch("src.bus.subscriber.redis.from_url", side_effect=fake_from_url):
        thread = threading.Thread(target=sub._run, daemon=True)
        thread.start()
        thread.join(timeout=3)

    assert call_count >= 1


def test_run_loop_message_delivered_to_queue() -> None:
    """Subscriber _run() puts valid messages onto the asyncio Queue."""
    import json

    loop = asyncio.new_event_loop()
    sub = Subscriber(redis_url="redis://localhost:6379/0", channel="test-channel", loop=loop)

    messages = [
        {"type": "subscribe", "data": 1},
        {"type": "message", "data": json.dumps({"hello": "world"})},
    ]

    def fake_listen():  # type: ignore[no-untyped-def]
        for m in messages:
            yield m
        sub._stop_event.set()

    mock_pubsub = MagicMock()
    mock_pubsub.listen.return_value = fake_listen()
    mock_client = MagicMock()
    mock_client.pubsub.return_value = mock_pubsub

    with patch("src.bus.subscriber.redis.from_url", return_value=mock_client):
        thread = threading.Thread(target=sub._run, daemon=True)
        thread.start()
        thread.join(timeout=3)

    result = loop.run_until_complete(asyncio.wait_for(sub.queue.get(), timeout=1.0))
    assert result == {"hello": "world"}


def test_run_loop_malformed_json_ignored() -> None:
    """Subscriber _run() logs and ignores malformed JSON messages without crashing."""
    loop = asyncio.new_event_loop()
    sub = Subscriber(redis_url="redis://localhost:6379/0", channel="test-channel", loop=loop)

    messages = [
        {"type": "message", "data": "not-json{{{{"},
    ]

    def fake_listen():  # type: ignore[no-untyped-def]
        for m in messages:
            yield m
        sub._stop_event.set()

    mock_pubsub = MagicMock()
    mock_pubsub.listen.return_value = fake_listen()
    mock_client = MagicMock()
    mock_client.pubsub.return_value = mock_pubsub

    with patch("src.bus.subscriber.redis.from_url", return_value=mock_client):
        thread = threading.Thread(target=sub._run, daemon=True)
        thread.start()
        thread.join(timeout=3)

    assert sub.queue.empty()
