import asyncio
from dataclasses import dataclass
import functools
import inspect
import logging
from typing import Awaitable, Callable, TypeVar, Union, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from autobahn_client.client import Autobahn

logger = logging.getLogger(__name__)
from autobahn_client.proto.message_pb2 import (
    RPCMessageType,
    RPCRequestMessage,
    RPCResponseMessage,
    RPCResponseType,
)
from google.protobuf import message as _message


@dataclass
class RPCFunctionInfo:
    name: str
    handler: Callable
    input_type: type
    original_function: Callable


SPECIAL_RPC_PREFIX_BASE = "RPC/FUNCTIONAL_SERVICE/"
SPECIAL_RPC_PREFIX_OUTPUT = f"{SPECIAL_RPC_PREFIX_BASE}OUTPUT/"
GLOBAL_RPC_FUNCTIONS: list[RPCFunctionInfo] = []


async def init_rpc_services(client: "Autobahn") -> None:
    """Initialize RPC service subscriptions."""
    for service_info in GLOBAL_RPC_FUNCTIONS:

        # Create a proper closure to capture the current service info
        async def create_rpc_callback(handler: Callable, msg_type: type, svc_name: str):
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
                                await client.publish(
                                    f"{SPECIAL_RPC_PREFIX_OUTPUT}{rpc_message.call_id}",
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

                            await client.publish(
                                f"{SPECIAL_RPC_PREFIX_OUTPUT}{rpc_message.call_id}",
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
                                await client.publish(
                                    f"{SPECIAL_RPC_PREFIX_OUTPUT}{rpc_message.call_id}",
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
        await client.subscribe(service_info.name, callback)
        logger.info(f"RPC service {service_info.name} is listening")


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


def rpc_callable(
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
                raise ConnectionError("WebSocket not connected. Call begin() first.")

            call_id = str(uuid.uuid4())
            response_topic = f"{SPECIAL_RPC_PREFIX_OUTPUT}{call_id}"

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
                    request_topic = (
                        f"{SPECIAL_RPC_PREFIX_BASE}{from_function_to_rpc_name(func)}"
                    )
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
                    typed_message = message  # Runtime: this will be the correct type
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
