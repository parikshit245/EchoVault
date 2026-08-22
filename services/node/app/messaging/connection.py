"""
RabbitMQ connection management — Part 6.

Provides a single long-lived RobustConnection per node process.
aio_pika.RobustConnection handles automatic reconnection transparently.

Usage:
    await messaging_connection.connect()   # called in lifespan startup
    await messaging_connection.close()    # called in lifespan shutdown
    messaging_connection.is_healthy()     # used by /health/messaging
"""

from __future__ import annotations

import logging

import aio_pika
import aio_pika.abc

from .config import get_rabbitmq_url

logger = logging.getLogger("echovault.messaging")


class MessagingConnection:
    """
    Wraps a single aio_pika.RobustConnection and one default channel.

    Lifecycle is managed by the FastAPI lifespan context manager in main.py.
    Do NOT create a new connection per request or per message publication.
    """

    def __init__(self) -> None:
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._connected: bool = False

    async def connect(self) -> None:
        """Establish connection to RabbitMQ.  Non-fatal if broker is down."""
        url = get_rabbitmq_url()
        try:
            self._connection = await aio_pika.connect_robust(url)
            self._channel = await self._connection.channel()
            await self._channel.set_qos(prefetch_count=10)
            self._connected = True
            logger.info(
                "RabbitMQ connection established",
                extra={"event": "rabbitmq_connected"},
            )
        except Exception as exc:  # noqa: BLE001
            self._connected = False
            logger.warning(
                "RabbitMQ unavailable at startup — messaging disabled: %s", exc
            )

    async def close(self) -> None:
        """Gracefully close the connection."""
        if self._connection and not self._connection.is_closed:
            try:
                await self._connection.close()
            except Exception:  # noqa: BLE001
                pass
        self._connected = False
        logger.info("RabbitMQ connection closed")

    def is_healthy(self) -> bool:
        """Return True if the connection is open and usable."""
        return (
            self._connected
            and self._connection is not None
            and not self._connection.is_closed
        )

    @property
    def channel(self) -> aio_pika.abc.AbstractChannel | None:
        return self._channel

    @property
    def connection(self) -> aio_pika.abc.AbstractRobustConnection | None:
        return self._connection


# Module-level singleton reused across the entire process lifetime.
messaging_connection = MessagingConnection()
