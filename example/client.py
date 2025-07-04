from autobahn_client.client import Autobahn, Address
import asyncio

from autobahn_client.proto.message_pb2 import AbstractMessage


# RPC function that is on the client side
# The contents of the function do not matter, it is just a placeholder
# and gets replaced by the "@Autobahn.rpc_callable()" decorator
@Autobahn.rpc_callable()
async def get_user(request: AbstractMessage) -> None:
    raise NotImplementedError()


async def main():
    server = Autobahn(address=Address("localhost", 8080))
    await server.begin()

    print("Server started")
    c = 0

    while True:
        c += 1
        print(f"Server: {c}")
        await asyncio.sleep(1)

        if c > 2:
            res = await get_user(server, AbstractMessage())
            print(res)


if __name__ == "__main__":
    asyncio.run(main())
