from autobahn_client.client import Autobahn, Address
import asyncio
from google.protobuf.message import Message

from autobahn_client.proto.message_pb2 import AbstractMessage


# RPC function that is on the server side
# the contents of the function DO matters as
# when the client calls the function on it's side
# the internal works of the autobahn client will relay
# the call to the server side function and the result
# will be relayed back to the client
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
