"""Autobahn client implementation."""

import asyncio
import logging
import time
from typing import Awaitable, Callable

import websockets

from autobahn_client.proto.message_pb2 import (
    AbstractMessage,
    HeartbeatMessage,
    MessageType,
    PublishMessage,
    TopicMessage,
)
from autobahn_client.rpc import init_rpc_services
from autobahn_client.util import Address

logger = logging.getLogger(__name__)


class Autobahn:
    """Base Autobahn client with overridable transport hooks."""

    def __init__(
        self,
        address: Address,
        reconnect: bool = True,
        reconnect_interval_seconds: float = 1.0,
    ) -> None:
        """Initialize the client state."""
        self.address = address
        self.websocket: websockets.ClientConnection | None = None
        self.first_subscription = True
        self.callbacks: dict[str, Callable[[bytes], Awaitable[None]]] = {}
        self.reconnect = reconnect
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self.listener_task: asyncio.Task[None] | None = None
        self.last_publish_time = time.time()
        self._connected = False

    async def __init_rpc_services(self) -> None:
        """Initialize configured RPC service subscriptions."""
        await init_rpc_services(self)  # pyright: ignore[reportArgumentType]

    def is_connected(self) -> bool:
        """Return whether the current transport is ready for messaging."""
        return self._connected

    def _set_connected(self, connected: bool) -> None:
        """Update the transport readiness state."""
        self._connected = connected

    def _supports_ping(self) -> bool:
        """Return whether the active transport supports ping frames."""
        return self.websocket is not None

    async def unsubscribe(self, topic: str) -> None:
        """Remove a subscription callback and notify the transport if possible."""
        if topic not in self.callbacks:
            raise ValueError(f"Topic '{topic}' not found")

        del self.callbacks[topic]
        if not self.is_connected():
            return

        try:
            message = TopicMessage(message_type=MessageType.UNSUBSCRIBE, topic=topic)
            await self._send_raw(message.SerializeToString())
        except Exception as e:
            logger.error(
                f"Failed to send unsubscribe message for topic {topic}: {str(e)}"
            )
            raise

    async def begin(self) -> None:
        """Connect the client and initialize RPC services."""
        try:
            await self._connect()
            if self.websocket is not None:
                logger.info(f"Connected to WebSocket at {self.address.make_url()}")
            else:
                logger.info(f"Connected to transport at {self.address.make_url()}")
        except OSError as e:
            logger.error(f"Failed to connect to transport at {self.address}: {str(e)}")
            if not self.reconnect:
                raise ConnectionError(f"Failed to connect: {str(e)}")

        await self.__init_rpc_services()

        if self.reconnect:
            asyncio.create_task(self._maintain_connection())

    async def _connect(self) -> object | None:
        """Establish the default websocket transport."""
        websocket = await websockets.connect(
            self.address.make_url(), max_size=None, max_queue=0
        )

        self.websocket = websocket
        self._set_connected(True)
        self.listener_task = asyncio.create_task(self._listener())
        return self.websocket

    async def _on_connection_closed(self) -> None:
        """Reset state after the active transport closes."""
        self._set_connected(False)
        self.websocket = None
        if self.listener_task:
            self.listener_task.cancel()
            self.listener_task = None

    async def _maintain_connection(self) -> None:
        """Reconnect and resubscribe when the transport becomes unavailable."""
        while True:
            try:
                if not self.is_connected():
                    try:
                        await self._connect()
                        logger.info("Reconnected to transport")
                        for topic in self.callbacks:
                            msg = TopicMessage(
                                message_type=MessageType.SUBSCRIBE, topic=topic
                            )
                            await self._send_raw(msg.SerializeToString())
                    except Exception as e:
                        logger.warning(f"Reconnection failed: {e}")
                        await self._on_connection_closed()
                elif self._supports_ping():
                    try:
                        await self.ping()
                    except websockets.exceptions.ConnectionClosed:
                        logger.warning("WebSocket connection lost")
                        await self._on_connection_closed()
                await asyncio.sleep(self.reconnect_interval_seconds)
            except Exception as e:
                logger.error(f"Error in connection maintenance: {e}")
                await asyncio.sleep(self.reconnect_interval_seconds)

    async def ping(self) -> None:
        """Send a ping if the current transport supports it."""
        if not self.is_connected():
            raise ConnectionError("Transport not connected. Call begin() first.")
        if self.websocket is None:
            raise NotImplementedError("The current transport does not support ping().")

        await self.websocket.ping()

    async def publish(self, topic: str, payload: bytes) -> None:
        """Publish a payload to a topic."""
        if not self.is_connected() and not self.reconnect:
            raise ConnectionError("Transport not connected. Call begin() first.")

        if not self.is_connected():
            logger.warning(
                "Dropped publish message to topic %s because transport is not connected",
                topic,
            )
            return

        message = PublishMessage(
            message_type=MessageType.PUBLISH, topic=topic, payload=payload
        )

        await self._send_raw(message.SerializeToString())

    async def subscribe(
        self, topic: str, callback: Callable[[bytes], Awaitable[None]]
    ) -> None:
        """Register and send a subscription for a topic."""
        if not self.is_connected() and not self.reconnect:
            raise ConnectionError("Transport not connected. Call begin() first.")

        self.callbacks[topic] = callback
        if not self.is_connected():
            logger.warning(
                "Dropped subscribe message to topic %s because transport is not connected",
                topic,
            )
            return

        message = TopicMessage(message_type=MessageType.SUBSCRIBE, topic=topic)
        await self._send_raw(message.SerializeToString())

    async def _send_raw(self, message: bytes) -> None:
        """Send a raw message through the current transport."""
        if not self.is_connected():
            raise ConnectionError("Transport not connected. Call begin() first.")
        if self.websocket is None:
            raise NotImplementedError(
                "Non-websocket transports must override _send_raw()."
            )

        return await self.websocket.send(message)

    async def send_heartbeat(self) -> None:
        """Send a heartbeat message for the currently subscribed topics."""
        if not self.is_connected():
            raise ConnectionError("Transport not connected. Call begin() first.")

        message = HeartbeatMessage(
            message_type=MessageType.HEARTBEAT, topics=list(self.callbacks.keys())
        )
        await self._send_raw(message.SerializeToString())

    async def _listener(self) -> None:
        """Receive inbound websocket messages and dispatch them."""
        while True:
            try:
                if self.websocket is None:
                    await asyncio.sleep(0.5)
                    continue

                message = await self.websocket.recv()

                if isinstance(message, str):
                    logger.warning(f"Received unexpected string message: {message}")
                    continue

                generic_message = AbstractMessage.FromString(message)

                match generic_message.message_type:
                    case MessageType.PUBLISH:
                        message_proto = PublishMessage.FromString(message)
                        if message_proto.topic not in self.callbacks:
                            continue

                        try:
                            await self.callbacks[message_proto.topic](
                                message_proto.payload
                            )
                        except Exception as e:
                            logger.error(
                                f"Error in callback for topic {message_proto.topic}: {str(e)}"
                            )

                    case MessageType.HEARTBEAT:
                        await self.send_heartbeat()

            except websockets.exceptions.ConnectionClosed:
                logger.info("WebSocket connection closed, waiting for reconnection...")
                await self._on_connection_closed()
                await asyncio.sleep(0.5)
                continue
            except Exception as e:
                logger.error(f"Error in listener: {str(e)}")
                await self._on_connection_closed()
                await asyncio.sleep(0.5)
                continue
