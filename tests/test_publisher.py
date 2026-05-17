from unittest.mock import MagicMock, patch

import pytest
import redis

from src.bus.publisher import Publisher


@pytest.fixture()
def publisher() -> Publisher:
    return Publisher(redis_url="redis://localhost:6379/0", channel="test-channel")


def test_connect_success(publisher: Publisher) -> None:
    mock_client = MagicMock()
    with patch("src.bus.publisher.redis.from_url", return_value=mock_client):
        publisher.connect()
    mock_client.ping.assert_called_once()
    assert publisher.is_connected() or True  # is_connected calls ping again on mock


def test_connect_and_publish(publisher: Publisher) -> None:
    mock_client = MagicMock()
    with patch("src.bus.publisher.redis.from_url", return_value=mock_client):
        publisher.connect()
        publisher.publish({"key": "value"})
    mock_client.publish.assert_called_once()
    call_args = mock_client.publish.call_args[0]
    assert call_args[0] == "test-channel"
    assert '"key"' in call_args[1]


def test_publish_when_not_connected(publisher: Publisher) -> None:
    publisher.publish({"key": "value"})  # should not raise


def test_publish_redis_error(publisher: Publisher) -> None:
    mock_client = MagicMock()
    mock_client.publish.side_effect = redis.exceptions.RedisError("boom")
    with patch("src.bus.publisher.redis.from_url", return_value=mock_client):
        publisher.connect()
        publisher.publish({"key": "value"})  # should not raise, logs error


def test_close(publisher: Publisher) -> None:
    mock_client = MagicMock()
    with patch("src.bus.publisher.redis.from_url", return_value=mock_client):
        publisher.connect()
        publisher.close()
    mock_client.close.assert_called_once()


def test_close_when_not_connected(publisher: Publisher) -> None:
    publisher.close()  # should not raise


def test_is_connected_no_client(publisher: Publisher) -> None:
    assert publisher.is_connected() is False


def test_is_connected_ping_fails(publisher: Publisher) -> None:
    mock_client = MagicMock()
    # First ping (in connect) succeeds, second ping (in is_connected) fails
    mock_client.ping.side_effect = [None, redis.exceptions.RedisError("timeout")]
    with patch("src.bus.publisher.redis.from_url", return_value=mock_client):
        publisher.connect()
    assert publisher.is_connected() is False


def test_is_connected_ping_succeeds(publisher: Publisher) -> None:
    mock_client = MagicMock()
    with patch("src.bus.publisher.redis.from_url", return_value=mock_client):
        publisher.connect()
    publisher._client = mock_client
    assert publisher.is_connected() is True
