"""WebSocket buffer metrics utilities for asyncio websockets.

Provides helpers to inspect the underlying transport's write buffer
to estimate remaining capacity before flow-control backpressure engages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import websockets


@dataclass
class WebSocketBufferMetrics:
    """Snapshot of write buffer metrics for a websocket connection.

    Attributes:
        write_buffer_size: Current size of the transport's write buffer in bytes.
        high_watermark: High-water mark (bytes) where the transport starts applying backpressure.
        low_watermark: Low-water mark (bytes) where the transport resumes writes after backpressure.
        remaining_capacity: Estimated remaining bytes before hitting the high-water mark; zero if unknown.
        is_closing: Whether the underlying transport is closing.
    """

    write_buffer_size: int
    high_watermark: Optional[int]
    low_watermark: Optional[int]
    remaining_capacity: Optional[int]
    is_closing: bool


def get_write_buffer_metrics(
    websocket: Any,
) -> WebSocketBufferMetrics:
    """Return transport write buffer metrics for the given websocket.

    Note:
        This relies on the asyncio transport used by the `websockets` library.
        Values are informative and platform/implementation dependent.

    Args:
        websocket: A `websockets.WebSocketClientProtocol` instance.

    Returns:
        WebSocketBufferMetrics with current buffer usage and limits.
    """

    transport = websocket.transport

    # Current buffer size
    try:
        size = transport.get_write_buffer_size()
    except Exception:
        size = 0

    # Watermarks (may not be available on all transports)
    high: Optional[int]
    low: Optional[int]
    try:
        high, low = transport.get_write_buffer_limits()  # type: ignore[assignment]
    except Exception:
        high, low = None, None

    # Estimate remaining capacity until the high watermark
    if high is not None:
        remaining = max(0, high - size)
    else:
        remaining = None

    # Closing state
    try:
        closing = transport.is_closing()
    except Exception:
        closing = False

    return WebSocketBufferMetrics(
        write_buffer_size=size,
        high_watermark=high,
        low_watermark=low,
        remaining_capacity=remaining,
        is_closing=closing,
    )


def get_remaining_capacity_bytes(websocket: Any) -> Optional[int]:
    """Return remaining bytes before hitting the high-water mark.

    Args:
        websocket: A websockets client connection (e.g., ClientConnection).

    Returns:
        Remaining bytes, or None if the high-water mark is unavailable.
    """

    metrics = get_write_buffer_metrics(websocket)
    return metrics.remaining_capacity


def get_remaining_capacity_ratio(websocket: Any) -> Optional[float]:
    """Return remaining capacity as a 0..1 ratio relative to the high-water mark.

    Args:
        websocket: A websockets client connection (e.g., ClientConnection).

    Returns:
        Remaining capacity ratio, or None if limits are unavailable.
    """

    metrics = get_write_buffer_metrics(websocket)
    if metrics.high_watermark is None or metrics.remaining_capacity is None:
        return None
    if metrics.high_watermark <= 0:
        return None
    return metrics.remaining_capacity / metrics.high_watermark
