import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch

from autobahn_client import Address, Autobahn
from autobahn_client.proto.message_pb2 import HeartbeatMessage, MessageType
import websockets


async def _noop(_: bytes) -> None:
    return None


def test_send_heartbeat_includes_current_topics() -> None:
    asyncio.run(_test_send_heartbeat_includes_current_topics())


async def _test_send_heartbeat_includes_current_topics() -> None:
    client = Autobahn(Address("localhost", 8080), reconnect=False)
    client.websocket = AsyncMock()
    client.callbacks["alpha"] = _noop
    client.callbacks["beta"] = _noop

    await client.send_heartbeat()

    client.websocket.send.assert_awaited_once()
    payload = client.websocket.send.await_args.args[0]
    message = HeartbeatMessage.FromString(payload)

    assert message.message_type == MessageType.HEARTBEAT
    assert set(message.topics) == {"alpha", "beta"}


def test_listener_replies_to_incoming_heartbeat() -> None:
    asyncio.run(_test_listener_replies_to_incoming_heartbeat())


async def _test_listener_replies_to_incoming_heartbeat() -> None:
    client = Autobahn(Address("localhost", 8080), reconnect=False)
    inbound = HeartbeatMessage(
        message_type=MessageType.HEARTBEAT,
        uuid="server",
        topics=["ignored/by/client"],
    ).SerializeToString()

    websocket = AsyncMock()
    websocket.send = AsyncMock()

    recv_count = 0
    block = asyncio.Event()

    async def recv() -> bytes:
        nonlocal recv_count
        recv_count += 1
        if recv_count == 1:
            return inbound

        await block.wait()
        raise AssertionError("listener should be cancelled before waiting resumes")

    websocket.recv = AsyncMock(side_effect=recv)

    client.websocket = websocket
    client.callbacks["heartbeat/topic"] = _noop

    with patch.object(
        websockets,
        "exceptions",
        SimpleNamespace(ConnectionClosed=RuntimeError),
        create=True,
    ):
        listener = asyncio.create_task(client._Autobahn__listener())

        try:
            await asyncio.sleep(0)
            listener.cancel()
            await listener
        except asyncio.CancelledError:
            pass

    websocket.send.assert_awaited_once()
    payload = websocket.send.await_args.args[0]
    message = HeartbeatMessage.FromString(payload)

    assert message.message_type == MessageType.HEARTBEAT
    assert list(message.topics) == ["heartbeat/topic"]
