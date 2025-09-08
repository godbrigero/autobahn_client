"""Autobahn client implementation."""

from concurrent.futures import Future
from dataclasses import dataclass
import threading
import time
from typing import (
    Awaitable,
    Callable,
    Optional,
    TypeVar,
    Union,
)
from autobahn_client.loop import AsyncLoopThread
from autobahn_client.rpc import RPCFunctionInfo, init_rpc_services
import websockets
from autobahn_client.proto.message_pb2 import (
    MessageType,
    PublishMessage,
    RPCMessageType,
    RPCRequestMessage,
    RPCResponseMessage,
    RPCResponseType,
    TopicMessage,
)
import asyncio
from autobahn_client.util import Address
from google.protobuf import message as _message
import functools
import uuid
import inspect
import logging

# Configure logging
logger = logging.getLogger(__name__)


class Autobahn:
    special_rpc_prefix_base = "RPC/FUNCTIONAL_SERVICE/"
    special_rpc_prefix_output = f"{special_rpc_prefix_base}OUTPUT/"
    _global_rpc_functions: list[RPCFunctionInfo] = []

    def __init__(
        self,
        address: Address,
        reconnect: bool = True,
        reconnect_interval_seconds: float = 1.0,
    ):
        """Initialize Autobahn client.

        Args:
            address: WebSocket server address
            reconnect: Whether to automatically reconnect on connection loss
            reconnect_interval_seconds: Interval between reconnection attempts
        """
        self.address = address
        self.websocket: websockets.ClientConnection | None = None
        self.first_subscription = True
        self.callbacks = {}
        self.reconnect = reconnect
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self.listener_lock = asyncio.Lock()
        self.listener_task = None

        self.publication_manager: _PublicationManager | None = None
        self.subscription_listener: _SubscriptionListener | None = None

    async def __init_rpc_services(self) -> None:
        await init_rpc_services(self)

    async def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a topic.

        Args:
            topic: Topic to unsubscribe from

        Raises:
            ConnectionError: If WebSocket is not connected
            ValueError: If topic is not subscribed
        """

        if self.websocket is None:
            raise ConnectionError("WebSocket not connected. Call begin() first.")

        if topic not in self.callbacks:
            raise ValueError(f"Topic '{topic}' not found")

        del self.callbacks[topic]

        try:
            assert self.publication_manager is not None
            self.publication_manager.unsubscribe(topic)
        except Exception as e:
            logger.error(
                f"Failed to send unsubscribe message for topic {topic}: {str(e)}"
            )
            raise

    async def begin(self) -> None:
        """Start the Autobahn client connection and initialize RPC services.

        Raises:
            ConnectionError: If initial connection fails and reconnect is disabled
        """
        try:
            await self.__connect()
            logger.info(f"Connected to WebSocket at {self.address.make_url()}")
        except OSError as e:
            logger.error(f"Failed to connect to WebSocket at {self.address}: {str(e)}")
            if not self.reconnect:
                raise ConnectionError(f"Failed to connect: {str(e)}")

        await self.__init_rpc_services()

        if self.reconnect:
            asyncio.create_task(self.__maintain_connection())

    async def __connect(self):
        """Establish WebSocket connection.

        Returns:
            WebSocket connection

        Raises:
            OSError: If connection fails
        """

        websocket = await websockets.connect(
            self.address.make_url(),
            max_size=None,
            max_queue=0,
            write_limit=10,
        )

        self.publication_manager = _PublicationManager(websocket)
        self.subscription_listener = _SubscriptionListener(
            websocket, self.__on_connection_closed
        )

        self.websocket = websocket

    async def __on_connection_closed(self) -> None:
        self.websocket = None
        self.publication_manager = None
        self.subscription_listener = None

    async def __maintain_connection(self) -> None:
        """Maintain WebSocket connection with reconnection logic."""
        while True:
            try:
                if self.websocket is None:
                    try:
                        await self.__connect()
                        assert self.publication_manager is not None
                        assert self.subscription_listener is not None

                        logger.info("Reconnected to WebSocket")

                        for topic in self.callbacks.keys():
                            self.publication_manager.subscribe(topic)
                            self.subscription_listener.subscribe(
                                topic, self.callbacks[topic]
                            )
                    except Exception as e:
                        logger.warning(f"Reconnection failed: {str(e)}")
                        await self.__on_connection_closed()
                else:
                    try:
                        await self.websocket.ping()
                    except websockets.exceptions.ConnectionClosed:
                        logger.warning("WebSocket connection lost")
                        await self.__on_connection_closed()

                await asyncio.sleep(self.reconnect_interval_seconds)

            except Exception as e:
                logger.error(f"Error in connection maintenance: {str(e)}")
                await asyncio.sleep(self.reconnect_interval_seconds)

    async def ping(self) -> None:
        """Send ping to WebSocket server.

        Raises:
            ConnectionError: If WebSocket is not connected
        """
        if self.websocket is None:
            raise ConnectionError("WebSocket not connected. Call begin() first.")

        try:
            await self.websocket.ping()
        except Exception as e:
            logger.error(f"Ping failed: {str(e)}")
            raise

    async def publish(self, topic: str, payload: bytes) -> None:
        """Publish a message to a topic.

        Args:
            topic: Topic to publish to
            payload: Message payload

        Raises:
            ConnectionError: If WebSocket is not connected and reconnect is disabled
        """
        if self.websocket is None and not self.reconnect:
            raise ConnectionError("WebSocket not connected. Call begin() first.")

        assert self.publication_manager is not None

        self.publication_manager.publish(topic, payload)

    async def subscribe(
        self, topic: str, callback: Callable[[bytes], Awaitable[None]]
    ) -> None:
        """Subscribe to a topic with a callback function.

        Args:
            topic: Topic to subscribe to
            callback: Async callback function to handle received messages

        Raises:
            ConnectionError: If WebSocket is not connected and reconnect is disabled
        """
        if self.websocket is None and not self.reconnect:
            raise ConnectionError("WebSocket not connected. Call begin() first.")

        assert self.subscription_listener is not None
        self.subscription_listener.subscribe(topic, callback)

        self.callbacks[topic] = callback

        if self.websocket is not None:
            try:
                assert self.publication_manager is not None
                self.publication_manager.subscribe(topic)
            except Exception as e:
                logger.error(
                    f"Failed to send subscribe message for topic {topic}: {str(e)}"
                )
                # Don't raise here if reconnect is enabled - the reconnection logic will handle it


class _SubscriptionListener:
    def __init__(
        self,
        websocket: websockets.ClientConnection,
        on_connection_closed: Callable[[], Awaitable[None]],
    ) -> None:
        self._thread = AsyncLoopThread("sub-loop")
        self._thread.start_and_wait()
        self._ws = websocket
        self._callbacks: dict[str, list[Callable[[bytes], Awaitable[None]]]] = {}
        self._on_connection_closed = on_connection_closed
        self._thread.run_coro(self.__listener())

    def subscribe(
        self, topic: str, callback: Callable[[bytes], Awaitable[None]]
    ) -> None:
        self._callbacks[topic].append(callback)

    def unsubscribe(
        self, topic: str, callback: Callable[[bytes], Awaitable[None]]
    ) -> None:
        self._callbacks[topic].remove(callback)
        if len(self._callbacks[topic]) == 0:
            del self._callbacks[topic]

    def unsubscribe_topic(self, topic: str) -> None:
        del self._callbacks[topic]

    async def __listener(self) -> None:
        while True:
            try:
                if self._ws is None:
                    await asyncio.sleep(0.5)
                    continue

                message = await self._ws.recv()

                if isinstance(message, str):
                    logger.warning(f"Received unexpected string message: {message}")
                    continue

                try:
                    message_proto = PublishMessage.FromString(message)
                    if message_proto.message_type == MessageType.PUBLISH:
                        if message_proto.topic in self._callbacks:
                            try:
                                for callback in self._callbacks[message_proto.topic]:
                                    await callback(message_proto.payload)
                            except Exception as e:
                                logger.error(
                                    f"Error in callback for topic {message_proto.topic}: {str(e)}"
                                )
                except Exception as e:
                    logger.error(f"Error parsing message: {str(e)}")

            except websockets.exceptions.ConnectionClosed:
                logger.info("WebSocket connection closed, waiting for reconnection...")
                await self._on_connection_closed()
                await asyncio.sleep(0.5)
                continue
            except Exception as e:
                logger.error(f"Error in listener: {str(e)}")
                await asyncio.sleep(0.5)
                continue


class _PublicationManager:
    def __init__(
        self, websocket: websockets.ClientConnection, timeout_ms: float = 1
    ) -> None:
        self._thread = AsyncLoopThread("pub-loop")
        self._thread.start_and_wait()
        self._ws = websocket

    async def _publish_impl(self, topic: str, payload: bytes) -> None:
        message = PublishMessage(
            message_type=MessageType.PUBLISH, topic=topic, payload=payload
        )

        await self._ws.send(message.SerializeToString())

    async def _subscribe_impl(self, topic: str) -> None:
        message = TopicMessage(message_type=MessageType.SUBSCRIBE, topic=topic)
        await self._ws.send(message.SerializeToString())

    async def _unsubscribe_impl(self, topic: str) -> None:
        message = TopicMessage(message_type=MessageType.UNSUBSCRIBE, topic=topic)
        await self._ws.send(message.SerializeToString())

    def publish(self, topic: str, payload: bytes) -> Future[None]:
        return self._thread.run_coro(self._publish_impl(topic, payload))

    def subscribe(self, topic: str) -> Future[None]:
        return self._thread.run_coro(self._subscribe_impl(topic))

    def unsubscribe(self, topic: str) -> Future[None]:
        return self._thread.run_coro(self._unsubscribe_impl(topic))

    def publish_blocking(
        self, topic: str, payload: bytes, timeout: Optional[float] = None
    ) -> None:
        self.publish(topic, payload).result(timeout=timeout)

    def set_websocket(self, websocket: websockets.ClientConnection) -> None:
        self._ws = websocket
