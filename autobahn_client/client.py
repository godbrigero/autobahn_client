"""Autobahn client implementation."""

from typing import Awaitable, Callable
import websockets
from autobahn_client.proto.message_pb2 import MessageType, PublishMessage, TopicMessage
import asyncio
from autobahn_client.util import Address


class Autobahn:
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
        self.listener_lock = asyncio.Lock()
        self.listener_task = None

    async def begin(self):
        try:
            self.websocket = await self.__connect()
        except OSError as e :
            print(f"Failed to connect to WebSocket at {self.address}: {str(e)}")
        
        if self.reconnect:
            asyncio.create_task(self.__maintain_connection())


    async def __connect(self) -> websockets.ClientConnection:    
        websocket = await websockets.connect(self.address.make_url())
        
        if self.callbacks and not self.first_subscription:
            self.__start_listener()

        return websocket

    async def __maintain_connection(self):
        while True:
            try:
                if self.websocket is None:
                    self.websocket = await self.__connect()
                    
                    for topic in self.callbacks.keys():
                        await self.websocket.send(
                            TopicMessage(
                                message_type=MessageType.SUBSCRIBE, topic=topic
                            ).SerializeToString()
                        )
                else:
                    try:
                        await self.websocket.ping()
                    except websockets.exceptions.ConnectionClosed:
                        self.websocket = None
                        print("Reconnecting...")
                await asyncio.sleep(self.reconnect_interval_seconds)
            except ConnectionError as e:
                print(f"Reconnection attempt failed: {str(e)}")
                await asyncio.sleep(self.reconnect_interval_seconds)

    async def ping(self):
        if self.websocket is None:
            raise ConnectionError("WebSocket not connected. Call begin() first.")

        await self.websocket.ping()

    async def publish(self, topic: str, payload: bytes):
        if self.websocket is None and not self.reconnect:
            raise ConnectionError("WebSocket not connected. Call begin() first.")
        
        if self.websocket is not None:
            message_proto = PublishMessage(
                message_type=MessageType.PUBLISH,
                topic=topic,
                payload=payload,
            )
            
            try:
                await self.websocket.send(message_proto.SerializeToString())
            except Exception as e:
                print(f"Error sending message: {str(e)}")
                self.websocket = None

    def __start_listener(self):
        if self.listener_task is None or self.listener_task.done():
            self.listener_task = asyncio.create_task(self.__listener())

    async def __listener(self):
        async with self.listener_lock:
            while True:
                try:
                    if self.websocket is None:
                        await asyncio.sleep(0.5)
                        continue

                    message = await self.websocket.recv()
                    if isinstance(message, str):
                        continue

                    message_proto = PublishMessage.FromString(message)
                    if message_proto.message_type == MessageType.PUBLISH:
                        if message_proto.topic in self.callbacks:
                            await self.callbacks[message_proto.topic](message_proto.payload)
                except websockets.exceptions.ConnectionClosed:
                    print("WebSocket connection closed, waiting for reconnection...")
                    self.websocket = None
                    await asyncio.sleep(0.5)
                    continue
                except Exception as e:
                    print(f"Error in listener: {str(e)}")
                    await asyncio.sleep(0.5)
                    continue

    async def subscribe(self, topic: str, callback: Callable[[bytes], Awaitable[None]]):
        if self.websocket is None and not self.reconnect:
            raise ConnectionError("WebSocket not connected. Call begin() first.")
        
        self.callbacks[topic] = callback
        
        if self.websocket is not None:
            await self.websocket.send(
                TopicMessage(
                    message_type=MessageType.SUBSCRIBE, topic=topic
                ).SerializeToString()
            )

        if self.first_subscription:
            self.__start_listener()
            self.first_subscription = False
