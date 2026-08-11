"""OSC output to TouchDesigner."""

from __future__ import annotations

from pythonosc.udp_client import SimpleUDPClient

from music_analyse.output.addresses import (
    BANK_IDS,
    FLOATS,
    OSC_FLOAT_ADDR,
    OSC_TRIGGER_ADDR,
    TRIGGERS,
)


class OscOutput:
    def __init__(self, host: str = "127.0.0.1", port: int = 8000, enabled: bool = True) -> None:
        self.host = host
        self.port = int(port)
        self.enabled = enabled
        self._client: SimpleUDPClient | None = None
        if enabled:
            self._connect()

    def _connect(self) -> None:
        self._client = SimpleUDPClient(self.host, self.port)

    def configure(self, host: str, port: int, enabled: bool) -> None:
        self.host = host
        self.port = int(port)
        self.enabled = enabled
        self._client = None
        if enabled:
            self._connect()

    def send_frame(self, triggers: dict[str, bool], floats: dict[str, float]) -> None:
        if not self.enabled or self._client is None:
            return
        # TouchDesigner OSC In CHOP holds the last value. Always send 0 or 1
        # every frame so a bang is a 1-frame pulse, not a sticky 1.
        for name in (*TRIGGERS, *BANK_IDS):
            self._client.send_message(
                OSC_TRIGGER_ADDR[name],
                1.0 if triggers.get(name) else 0.0,
            )
        for name in (*FLOATS, *BANK_IDS):
            self._client.send_message(OSC_FLOAT_ADDR[name], float(floats.get(name, 0.0)))

    def close(self) -> None:
        self._client = None
        self.enabled = False
