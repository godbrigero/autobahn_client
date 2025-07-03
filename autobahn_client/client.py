"""Autobahn client implementation."""

from dataclasses import dataclass
from typing import (
    Awaitable,
    Callable,
    Type,
    TypeVar,
    Union,
    get_origin,
    get_args,
    Any,
    Generic,
)
import websockets
from autobahn_client.proto.message_pb2 import (
    MessageType,
    PublishMessage,
    RPCMessageType,
    RPCRequestMessage,
    RPCResponseMessage,
    RPCResponseType,
    TopicMessage,
    RPCMessage,
    AbstractMessage,
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


def from_function_to_rpc_name(function: Callable) -> str:
    """Convert a function to an RPC name string with type information.

    Args:
        function: The function to convert to an RPC name

    Returns:
        A string in the format "<function name><function arg1 type><function arg2 type>...<function return type>"

    Raises:
        ValueError: If function lacks proper type annotations
    """
    sig = inspect.signature(function)

    # Validate that function has proper annotations for the types
    if not function.__annotations__:
        raise ValueError(
            f"Function {function.__name__} must have type annotations for RPC usage"
        )

    param_types = []
    for param in sig.parameters.values():
        if param.annotation == inspect.Parameter.empty:
            raise ValueError(
                f"Parameter {param.name} in function {function.__name__} must have type annotation"
            )

        param_type_name = (
            param.annotation.__name__
            if hasattr(param.annotation, "__name__")
            else str(param.annotation)
        )
        param_types.append(param_type_name)

    return_type = (
        sig.return_annotation.__name__
        if hasattr(sig.return_annotation, "__name__")
        else str(sig.return_annotation)
    )

    return f"{function.__name__}{''.join(param_types)}{return_type}"


T = TypeVar("T", bound=Union[_message.Message, None])
R = TypeVar("R", bound=Union[_message.Message, None])


@dataclass
class RPCFunctionInfo:
    name: str
    handler: Callable
    input_type: type
    original_function: Callable


class Autobahn:
    special_rpc_prefix_base = "RPC/FUNCTIONAL_SERVICE/"
    special_rpc_prefix_output = f"{special_rpc_prefix_base}OUTPUT/"

    _global_rpc_functions: list[RPCFunctionInfo] = []

    @classmethod
    def rpc_callable(
        cls,
        timeout_ms: float = 3000.0,
    ):
        """Decorator to create RPC client calls.

        Args:
            timeout_ms: Timeout for RPC calls in milliseconds

        Returns:
            Decorator function that creates RPC client calls

        Raises:
            ValueError: If decorated function lacks proper type annotations
        """

        def decorator(
            func: Union[Callable[[], Awaitable[R]], Callable[[T], Awaitable[R]]],
        ):
            sig = inspect.signature(func)

            if sig.return_annotation == inspect.Signature.empty:
                raise ValueError(
                    f"RPC callable {func.__name__} must have return type annotation"
                )

            output_type = sig.return_annotation

            @functools.wraps(func)  # type: ignore[arg-type]
            async def rpc_caller(autobahn_instance: "Autobahn", message: T) -> R | None:
                if autobahn_instance.websocket is None:
                    raise ConnectionError(
                        "WebSocket not connected. Call begin() first."
                    )

                call_id = str(uuid.uuid4())
                response_topic = f"{cls.special_rpc_prefix_output}{call_id}"

                try:
                    serialized_message = (
                        message.SerializeToString() if message is not None else b""
                    )

                    rpc_message = RPCRequestMessage(
                        message_type=RPCMessageType.RPC_REQUEST,
                        call_id=call_id,
                        payload=serialized_message,
                    )

                    response_future: asyncio.Future[R | None] = asyncio.Future()

                    async def response_handler(payload: bytes) -> None:
                        try:
                            response_message = RPCResponseMessage.FromString(payload)

                            if (
                                response_message.response_type
                                == RPCResponseType.RPC_RESPONSE_SUCCESS
                            ):
                                if response_message.payload == b"":
                                    if output_type is None or output_type == type(None):
                                        response_future.set_result(None)
                                    else:
                                        response_future.set_exception(
                                            Exception(
                                                f"RPC call to '{from_function_to_rpc_name(func)}' returned empty result but expected {output_type}"
                                            )
                                        )
                                else:
                                    if output_type is None or output_type == type(None):
                                        response_future.set_exception(
                                            Exception(
                                                f"RPC call to '{from_function_to_rpc_name(func)}' returned data but expected None"
                                            )
                                        )
                                    else:
                                        try:
                                            result_message = output_type.FromString(
                                                response_message.payload
                                            )
                                            response_future.set_result(result_message)
                                        except Exception as e:
                                            response_future.set_exception(
                                                Exception(
                                                    f"Failed to deserialize RPC response: {str(e)}"
                                                )
                                            )
                            else:
                                error_msg = (
                                    response_message.payload.decode()
                                    if response_message.payload
                                    else "Unknown RPC error"
                                )
                                response_future.set_exception(Exception(error_msg))

                        except Exception as e:
                            logger.error(f"Error processing RPC response: {str(e)}")
                            response_future.set_exception(e)

                    # Subscribe to response topic
                    await autobahn_instance.subscribe(response_topic, response_handler)

                    try:
                        # Publish request
                        request_topic = f"{cls.special_rpc_prefix_base}{from_function_to_rpc_name(func)}"
                        await autobahn_instance.publish(
                            request_topic, rpc_message.SerializeToString()
                        )

                        # Wait for response with timeout
                        try:
                            result = await asyncio.wait_for(
                                response_future, timeout=timeout_ms / 1000.0
                            )

                            return result
                        except asyncio.TimeoutError:
                            response_future.cancel()
                            raise TimeoutError(
                                f"RPC call to '{from_function_to_rpc_name(func)}' timed out after {timeout_ms}ms"
                            )
                    finally:
                        try:
                            await autobahn_instance.unsubscribe(response_topic)
                        except Exception as e:
                            logger.warning(
                                f"Failed to unsubscribe from response topic {response_topic}: {str(e)}"
                            )
                except Exception as e:
                    logger.error(f"RPC call failed: {str(e)}")
                    raise

            return rpc_caller

        return decorator

    @classmethod
    def rpc_function(cls):
        """Decorator to register functions as RPC services.

        Returns:
            Decorator function that registers the decorated function as an RPC service

        Raises:
            ValueError: If decorated function lacks proper type annotations
        """

        def decorator(
            func: Union[Callable[[], Awaitable[R]], Callable[[T], Awaitable[R]]],
        ):
            sig = inspect.signature(func)
            return_type = sig.return_annotation
            params = list(sig.parameters.values())
            input_type = params[0].annotation if params else None

            name = from_function_to_rpc_name(func)

            @functools.wraps(func)  # type: ignore[arg-type]
            async def wrapper(message: T) -> R | None:
                try:
                    if message is not None:
                        typed_message = (
                            message  # Runtime: this will be the correct type
                        )
                        return await func(typed_message)  # type: ignore[arg-type]
                    else:
                        return await func(message)  # type: ignore[arg-type]
                except Exception as e:
                    logger.error(f"RPC function {func.__name__} failed: {str(e)}")
                    raise

            service_info = RPCFunctionInfo(
                name=cls.special_rpc_prefix_base + name,
                handler=wrapper,
                input_type=type(input_type),
                original_function=func,
            )

            cls._global_rpc_functions.append(service_info)

            return wrapper

        return decorator

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

    async def __init_rpc_services(self) -> None:
        """Initialize RPC service subscriptions."""
        for service_info in self._global_rpc_functions:

            # Create a proper closure to capture the current service info
            async def create_rpc_callback(
                handler: Callable, msg_type: type, svc_name: str
            ):
                async def rpc_service_callback(payload: bytes) -> None:
                    try:
                        rpc_message = RPCRequestMessage.FromString(payload)

                        # Deserialize input if needed
                        if msg_type is not None and msg_type != type(None):
                            if rpc_message.payload == b"":
                                rpc_args = None
                            else:
                                try:
                                    rpc_args = msg_type.FromString(rpc_message.payload)
                                except Exception as e:
                                    logger.error(
                                        f"Failed to deserialize RPC input for {svc_name}: {str(e)}"
                                    )
                                    # Send error response
                                    error_response = RPCResponseMessage(
                                        message_type=RPCMessageType.RPC_RESPONSE,
                                        response_type=RPCResponseType.RPC_RESPONSE_ERROR,
                                        call_id=rpc_message.call_id,
                                        payload=f"Failed to deserialize input: {str(e)}".encode(),
                                    )
                                    await self.publish(
                                        f"{self.special_rpc_prefix_output}{rpc_message.call_id}",
                                        error_response.SerializeToString(),
                                    )
                                    return
                        else:
                            rpc_args = None

                        async def execute_rpc():
                            try:
                                result = await handler(rpc_args)

                                response = RPCResponseMessage(
                                    message_type=RPCMessageType.RPC_RESPONSE,
                                    response_type=RPCResponseType.RPC_RESPONSE_SUCCESS,
                                    call_id=rpc_message.call_id,
                                    payload=b"",
                                )

                                if result is not None:
                                    if isinstance(result, _message.Message):
                                        response.payload = result.SerializeToString()
                                    else:
                                        # Invalid return type
                                        response.response_type = (
                                            RPCResponseType.RPC_RESPONSE_ERROR
                                        )
                                        response.payload = f"RPC function returned invalid type: {type(result)}".encode()

                                await self.publish(
                                    f"{self.special_rpc_prefix_output}{rpc_message.call_id}",
                                    response.SerializeToString(),
                                )

                            except Exception as e:
                                logger.error(
                                    f"RPC service {svc_name} execution failed: {str(e)}"
                                )
                                error_response = RPCResponseMessage(
                                    message_type=RPCMessageType.RPC_RESPONSE,
                                    response_type=RPCResponseType.RPC_RESPONSE_ERROR,
                                    call_id=rpc_message.call_id,
                                    payload=str(e).encode(),
                                )
                                try:
                                    await self.publish(
                                        f"{self.special_rpc_prefix_output}{rpc_message.call_id}",
                                        error_response.SerializeToString(),
                                    )
                                except Exception as pub_error:
                                    logger.error(
                                        f"Failed to send error response: {str(pub_error)}"
                                    )

                        # Execute RPC in background task
                        asyncio.create_task(execute_rpc())

                    except Exception as e:
                        logger.error(
                            f"Error in RPC service callback for {svc_name}: {str(e)}"
                        )

                return rpc_service_callback

            # Create the callback with proper closure
            callback = await create_rpc_callback(
                service_info.handler, service_info.input_type, service_info.name
            )
            await self.subscribe(service_info.name, callback)
            logger.info(f"RPC service {service_info.name} is listening")

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
            await self.websocket.send(
                TopicMessage(
                    message_type=MessageType.UNSUBSCRIBE, topic=topic
                ).SerializeToString()
            )
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
            self.websocket = await self.__connect()
            logger.info(f"Connected to WebSocket at {self.address.make_url()}")
        except OSError as e:
            logger.error(f"Failed to connect to WebSocket at {self.address}: {str(e)}")
            if not self.reconnect:
                raise ConnectionError(f"Failed to connect: {str(e)}")

        await self.__init_rpc_services()

        if self.reconnect:
            asyncio.create_task(self.__maintain_connection())

    async def __connect(self) -> websockets.ClientConnection:
        """Establish WebSocket connection.

        Returns:
            WebSocket connection

        Raises:
            OSError: If connection fails
        """
        # Set max_size to 100MB (100 * 1024 * 1024 bytes)
        websocket = await websockets.connect(
            self.address.make_url(), max_size=100 * 1024 * 1024
        )

        if self.callbacks and not self.first_subscription:
            self.__start_listener()

        return websocket

    async def __maintain_connection(self) -> None:
        """Maintain WebSocket connection with reconnection logic."""
        while True:
            try:
                if self.websocket is None:
                    try:
                        self.websocket = await self.__connect()
                        logger.info("Reconnected to WebSocket")

                        # Re-subscribe to all topics
                        for topic in self.callbacks.keys():
                            await self.websocket.send(
                                TopicMessage(
                                    message_type=MessageType.SUBSCRIBE, topic=topic
                                ).SerializeToString()
                            )
                    except Exception as e:
                        logger.warning(f"Reconnection failed: {str(e)}")
                        self.websocket = None
                else:
                    try:
                        await self.websocket.ping()
                    except websockets.exceptions.ConnectionClosed:
                        logger.warning("WebSocket connection lost")
                        self.websocket = None

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

        if self.websocket is not None:
            message_proto = PublishMessage(
                message_type=MessageType.PUBLISH,
                topic=topic,
                payload=payload,
            )

            try:
                await self.websocket.send(message_proto.SerializeToString())
            except Exception as e:
                logger.error(f"Error sending message to topic {topic}: {str(e)}")
                self.websocket = None
                if not self.reconnect:
                    raise

    def __start_listener(self) -> None:
        """Start the message listener task."""
        if self.listener_task is None or self.listener_task.done():
            self.listener_task = asyncio.create_task(self.__listener())

    async def __listener(self) -> None:
        """Listen for incoming WebSocket messages."""
        async with self.listener_lock:
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
                    logger.info(
                        "WebSocket connection closed, waiting for reconnection..."
                    )
                    self.websocket = None
                    await asyncio.sleep(0.5)
                    continue
                except Exception as e:
                    logger.error(f"Error in listener: {str(e)}")
                    await asyncio.sleep(0.5)
                    continue

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

        self.callbacks[topic] = callback

        if self.websocket is not None:
            try:
                await self.websocket.send(
                    TopicMessage(
                        message_type=MessageType.SUBSCRIBE, topic=topic
                    ).SerializeToString()
                )
            except Exception as e:
                logger.error(
                    f"Failed to send subscribe message for topic {topic}: {str(e)}"
                )
                # Don't raise here if reconnect is enabled - the reconnection logic will handle it

        if self.first_subscription:
            self.__start_listener()
            self.first_subscription = False
