from autobahn_client.client import Autobahn, Address
import asyncio
from google.protobuf.message import Message

from autobahn_client.proto.message_pb2 import AbstractMessage


@Autobahn.rpc_function()
async def get_user(request: AbstractMessage) -> None:
    print("GOT!!!")


async def main():
    client = Autobahn(address=Address("localhost", 8080))
    await client.begin()

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
