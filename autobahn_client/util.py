from dataclasses import dataclass


@dataclass
class Address:
    host: str
    port: int

    def make_url(self) -> str:
        return f"ws://{self.host}:{self.port}"