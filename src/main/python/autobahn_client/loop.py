import asyncio
import threading
import concurrent.futures
from typing import Any, Callable, Coroutine, Optional, TypeVar

T = TypeVar("T")


class AsyncLoopThread(threading.Thread):
    """Owns a dedicated asyncio loop running in a background thread."""

    def __init__(self, name: str = "async-loop") -> None:
        super().__init__(name=name, daemon=True)
        self.loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._ready = threading.Event()

    def run(self) -> None:
        """Thread entry: bind loop to this thread and run forever."""
        asyncio.set_event_loop(self.loop)
        self._ready.set()
        self.loop.run_forever()

    def start_and_wait(self) -> None:
        """Start the thread and wait until the loop is ready."""
        self.start()
        self._ready.wait()

    def run_coro(self, coro: Coroutine[Any, Any, T]) -> "concurrent.futures.Future[T]":
        """Schedule a coroutine on the loop from any thread and get a Future."""
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def call_soon(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Schedule a regular callable on the loop thread-safely."""
        self.loop.call_soon_threadsafe(fn, *args, **kwargs)

    def stop(self) -> None:
        """Stop the loop and join the thread."""

        def _stop() -> None:
            self.loop.stop()

        self.loop.call_soon_threadsafe(_stop)
        self.join()
        self.loop.close()
