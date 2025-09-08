from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Address:
    host: str
    port: int

    def make_url(self) -> str:
        return f"ws://{self.host}:{self.port}"


def get_remaining_capacity_ratio(websocket: Any) -> Optional[float]:
    transport = websocket.transport
    try:
        size = transport.get_write_buffer_size()
    except Exception:
        return None
    try:
        high, low = transport.get_write_buffer_limits()
    except Exception:
        return None
    if high <= 0:
        return None
    return max(0.0, min(1.0, (high - size) / high))
