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
    total_time = 0
    total_runs = 10

    while True:
        c += 1

        # print(f"Sending to server: {c}")
        time_start = time.time()
        res = await get_user(server, AbstractMessage())
        time_end = time.time()
        # print(f"Time taken: {(time_end - time_start) * 1000} ms")

        total_time += time_end * 1000 - time_start * 1000

        if c % total_runs == 0:
            print(total_time / total_runs)
            total_time = 0
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
