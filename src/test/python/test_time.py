import asyncio
import argparse
import os
import statistics
import time
from autobahn_client import Address, Autobahn
import matplotlib.pyplot as plt
import threading

from src.test.python.util import (
    deserialize_time_message,
    send_time_messages,
    serialize_time_message,
)

SAMPLE_COUNT = 100
HOST = "localhost"
PORT = 8080
TOPIC = "test"


async def run_test(
    extra_payload: bytes, sleep: float | None, disable_plot: bool = False
):
    client = Autobahn(address=Address(host=HOST, port=PORT))
    await client.begin()
    times = await send_time_messages(
        client, extra_payload, TOPIC, number_of_messages=SAMPLE_COUNT, sleep=sleep
    )

    print("-----------")
    print(f"Average time: {sum(times) / len(times)} milliseconds")
    print(f"Median time: {sorted(times)[len(times) // 2]}")
    print(f"Min time: {min(times)} milliseconds")
    print(f"Max time: {max(times)} milliseconds")
    print(f"Standard deviation: {statistics.stdev(times)} milliseconds")
    print()

    if not disable_plot:
        plt.hist(times, bins=30)
        plt.xlabel("Time (ms)")
        plt.ylabel("Frequency")
        plt.title("Distribution of Message Latencies")

        plt.show(block=True)


def test_1mb():
    extra_payload = os.urandom(1024 * 1024)
    asyncio.run(run_test(extra_payload, 0.01))


def test_4mb():
    extra_payload = os.urandom(1024 * 1024 * 4)
    asyncio.run(run_test(extra_payload, 0.01))


def test_8mb():
    extra_payload = os.urandom(1024 * 1024 * 8)
    asyncio.run(run_test(extra_payload, 0.01))


def test_0mb():
    extra_payload = b""
    asyncio.run(run_test(extra_payload, 0.01))


def test_noms():
    extra_payload = b""
    asyncio.run(run_test(extra_payload, None))


def test_noms_4mb():
    extra_payload = os.urandom(1024 * 1024 * 4)
    asyncio.run(run_test(extra_payload, None))


def test_multi_message_0mb(number_of_threads: int) -> None:
    extra_payload = os.urandom(1024 * 1024 * 1)

    def thread_target() -> None:
        asyncio.run(run_test(extra_payload, 0.01, disable_plot=True))

    threads: list[threading.Thread] = [
        threading.Thread(target=thread_target),
        *[threading.Thread(target=thread_target) for _ in range(number_of_threads - 1)],
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=str, required=True)
    args = parser.parse_args()
    if args.test == "1mb":
        test_1mb()
    elif args.test == "4mb":
        test_4mb()
    elif args.test == "8mb":
        test_8mb()
    elif args.test == "0mb":
        test_0mb()
    elif args.test == "noms":
        test_noms()
    elif args.test == "noms_4mb":
        test_noms_4mb()
    elif args.test == "multi_message_0mb":
        test_multi_message_0mb(2)
    else:
        print("Invalid test")
        exit(1)
