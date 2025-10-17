import time
from autobahn_client.client import Autobahn, Address
import asyncio

from autobahn_client.proto.message_pb2 import AbstractMessage, ServerForwardMessage
from autobahn_client.rpc import rpc_callable


# RPC function that is on the client side
# The contents of the function do not matter, it is just a placeholder
# and gets replaced by the "@Autobahn.rpc_callable()" decorator
@rpc_callable()
async def get_user(request: AbstractMessage) -> ServerForwardMessage:
    raise NotImplementedError()


async def main():
    server = Autobahn(address=Address("localhost", 8080))
    await server.begin()

    print("Server started")
    c = 0

    while True:
        c += 1

        if c > 2:
            print(f"Sending to server: {c}")
            time_start = time.time()
            res = await get_user(server, AbstractMessage())
            time_end = time.time()
            print(f"Time taken: {(time_end - time_start) * 1000} ms")
            if res is not None:
                print(f"Response from server: '{res.payload.decode('utf-8')}'")
            else:
                print("No response from server")

        await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
