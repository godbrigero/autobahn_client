"""Autobahn client implementation."""

from concurrent.futures import Future
import time
from typing import (
    Awaitable,
    Callable,
    Optional,
    Union,
)
from autobahn_client.loop import AsyncLoopThread
from autobahn_client.rpc import RPCFunctionInfo, init_rpc_services
import websockets
from autobahn_client.proto.message_pb2 import (
    MessageType,
    PublishMessage,
    TopicMessage,
)
import asyncio
from autobahn_client.util import Address, get_remaining_capacity_ratio
import logging

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
        self.address = address
        self.websocket: websockets.ClientConnection | None = None
        self.first_subscription = True
        self.callbacks = {}
        self.reconnect = reconnect
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self.listener_task = None
        self.last_publish_time = time.time()

    async def __init_rpc_services(self) -> None:
        await init_rpc_services(self)

    async def unsubscribe(self, topic: str) -> None:
        if self.websocket is None:
            raise ConnectionError("WebSocket not connected. Call begin() first.")

        if topic not in self.callbacks:
            raise ValueError(f"Topic '{topic}' not found")

        del self.callbacks[topic]

        try:
            message = TopicMessage(message_type=MessageType.UNSUBSCRIBE, topic=topic)
            await self.websocket.send(message.SerializeToString())
        except Exception as e:
            logger.error(
                f"Failed to send unsubscribe message for topic {topic}: {str(e)}"
            )
            raise

    async def begin(self) -> None:
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
        websocket = await websockets.connect(
            self.address.make_url(),
            max_size=None,
            max_queue=0,
            write_limit=10,
        )

        self.websocket = websocket
        self.listener_task = asyncio.create_task(self.__listener())
        return self.websocket

    async def __on_connection_closed(self) -> None:
        self.websocket = None
        if self.listener_task:
            self.listener_task.cancel()
            self.listener_task = None

    async def __maintain_connection(self) -> None:
        while True:
            try:
                if self.websocket is None:
                    try:
                        self.websocket = await self.__connect()

                        logger.info("Reconnected to WebSocket")

                        if self.websocket is not None:
                            for topic in self.callbacks.keys():
                                message = TopicMessage(
                                    message_type=MessageType.SUBSCRIBE, topic=topic
                                )

                                await self.websocket.send(message.SerializeToString())
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
        if self.websocket is None:
            raise ConnectionError("WebSocket not connected. Call begin() first.")

        await self.websocket.ping()

    async def publish(self, topic: str, payload: bytes) -> None:
        if self.websocket is None and not self.reconnect:
            raise ConnectionError("WebSocket not connected. Call begin() first.")

        if self.websocket is None:
            return

        message = PublishMessage(
            message_type=MessageType.PUBLISH, topic=topic, payload=payload
        )

        await self.websocket.send(message.SerializeToString())

    async def subscribe(
        self, topic: str, callback: Callable[[bytes], Awaitable[None]]
    ) -> None:
        if self.websocket is None and not self.reconnect:
            raise ConnectionError("WebSocket not connected. Call begin() first.")

        self.callbacks[topic] = callback

        if self.websocket is not None:
            message = TopicMessage(message_type=MessageType.SUBSCRIBE, topic=topic)
            await self.websocket.send(message.SerializeToString())

    async def __listener(self):
        while True:
            try:
                if self.websocket is None:
                    await asyncio.sleep(0.5)
                    continue

                message = await self.websocket.recv()

                if isinstance(message, str):
                    logger.warning(f"Received unexpected string message: {message}")
                    continue

                try:
                    message_proto = PublishMessage.FromString(message)
                    if message_proto.message_type == MessageType.PUBLISH:
                        if message_proto.topic in self.callbacks:
                            try:
                                await self.callbacks[message_proto.topic](
                                    message_proto.payload
                                )
                            except Exception as e:
                                logger.error(
                                    f"Error in callback for topic {message_proto.topic}: {str(e)}"
                                )
                except Exception as e:
                    logger.error(f"Error parsing message: {str(e)}")

            except websockets.exceptions.ConnectionClosed:
                logger.info("WebSocket connection closed, waiting for reconnection...")
                await self.__on_connection_closed()
                await asyncio.sleep(0.5)
                continue
            except Exception as e:
                logger.error(f"Error in listener: {str(e)}")
                await asyncio.sleep(0.5)
                continue
