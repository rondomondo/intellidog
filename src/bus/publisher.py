import json
import logging
from typing import Any

import redis

logger = logging.getLogger(__name__)


class Publisher:
    """Thin wrapper around a Redis client for publishing event messages to a channel.

    Args:
        redis_url: Redis connection URL (e.g. redis://localhost:6379/0).
        channel: Pub/sub channel name to publish on.
    """

    def __init__(self, redis_url: str, channel: str) -> None:
        self._channel = channel
        self._client: redis.Redis | None = None
        self._redis_url = redis_url

    def connect(self) -> None:
        """Open the Redis connection.

        Raises:
            redis.exceptions.ConnectionError: If Redis is not reachable.
        """
        self._client = redis.from_url(self._redis_url, decode_responses=True)
        self._client.ping()
        logger.info("Redis publisher connected: %s channel=%s", self._redis_url, self._channel)

    def publish(self, payload: dict[str, Any]) -> None:
        """Publish a JSON-serialised payload to the configured channel.

        Args:
            payload: Arbitrary dict to serialise and publish.
        """
        if self._client is None:
            logger.warning("Publisher not connected -- message dropped")
            return
        try:
            self._client.publish(self._channel, json.dumps(payload, ensure_ascii=False))
        except redis.exceptions.RedisError as exc:
            logger.error("Redis publish error: %s", exc)

    def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("Redis publisher closed")

    def is_connected(self) -> bool:
        """Return True if the publisher has an active connection."""
        if self._client is None:
            return False
        try:
            self._client.ping()
            return True
        except redis.exceptions.RedisError:
            return False
