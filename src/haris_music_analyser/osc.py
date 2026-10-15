"""OSC output for TouchDesigner and Unreal."""

from __future__ import annotations

from pathlib import Path

from pythonosc import udp_client

from haris_music_analyser.profile import load_profile


class OscCueSender:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9000,
        *,
        profile: str | Path | None = "default",
    ) -> None:
        cfg = load_profile(profile)
        pb = cfg["playback"]
        self._kick_addr = str(pb["osc_kick_address"])
        self._snare_addr = str(pb["osc_snare_address"])
        self._client = udp_client.SimpleUDPClient(host, port)
        self._host = host
        self._port = port

    def send(self, cue_type: str, velocity: float) -> None:
        v = float(max(0.0, min(1.0, velocity)))
        addr = self._kick_addr if cue_type == "kick" else self._snare_addr
        self._client.send_message(addr, v)

    @property
    def endpoint(self) -> str:
        return f"{self._host}:{self._port}"
