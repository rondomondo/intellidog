import asyncio
import json
import logging
import threading
from typing import Any

import redis

logger = logging.getLogger(__name__)

RECONNECT_DELAY_SECONDS = 5


class Subscriber:
    """Redis pub/sub subscriber that bridges messages into an asyncio Queue.

    Runs a blocking Redis subscription on a dedicated daemon thread. Each
    received message is put onto an asyncio Queue so the FastAPI event loop
    can consume it without blocking.

    Args:
        redis_url: Redis connection URL.
        channel: Pub/sub channel name to subscribe to.
        loop: The running asyncio event loop (used to schedule queue puts thread-safely).
    """

    def __init__(self, redis_url: str, channel: str, loop: asyncio.AbstractEventLoop) -> None:
        self._redis_url = redis_url
        self._channel = channel
        self._loop = loop
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._client: redis.Redis | None = None

    @property
    def queue(self) -> asyncio.Queue[dict[str, Any]]:
        """The asyncio Queue that receives messages from the subscriber thread."""
        return self._queue

    def start(self) -> None:
        """Start the subscriber daemon thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="redis-subscriber")
        self._thread.start()
        logger.info("Redis subscriber thread started: channel=%s", self._channel)

    def stop(self) -> None:
        """Signal the subscriber thread to stop and wait for it to exit."""
        self._stop_event.set()
        if self._client is not None:
            try:
                self._client.close()
            except redis.exceptions.RedisError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Redis subscriber thread stopped")

    def is_connected(self) -> bool:
        """Return True if the subscriber thread is alive and Redis is reachable."""
        if self._thread is None or not self._thread.is_alive():
            return False
        if self._client is None:
            return False
        try:
            self._client.ping()
            return True
        except redis.exceptions.RedisError:
            return False

    def _run(self) -> None:
        """Blocking subscriber loop -- runs on the daemon thread."""
        while not self._stop_event.is_set():
            try:
                self._client = redis.from_url(self._redis_url, decode_responses=True)
                pubsub = self._client.pubsub()
                pubsub.subscribe(self._channel)
                logger.info("Subscribed to Redis channel: %s", self._channel)
                for raw_message in pubsub.listen():
                    if self._stop_event.is_set():
                        break
                    if raw_message.get("type") != "message":
                        continue
                    try:
                        data: dict[str, Any] = json.loads(raw_message["data"])
                        asyncio.run_coroutine_threadsafe(self._queue.put(data), self._loop)
                    except (json.JSONDecodeError, TypeError) as exc:
                        logger.warning("Subscriber: malformed message ignored: %s", exc)
            except redis.exceptions.RedisError as exc:
                if not self._stop_event.is_set():
                    logger.warning(
                        "Redis subscriber disconnected (%s) -- reconnecting in %ds", exc, RECONNECT_DELAY_SECONDS
                    )
                    self._stop_event.wait(RECONNECT_DELAY_SECONDS)
            except Exception as exc:
                logger.error("Subscriber thread unexpected error: %s", exc)
                if not self._stop_event.is_set():
                    self._stop_event.wait(RECONNECT_DELAY_SECONDS)
