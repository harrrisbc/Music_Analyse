"""Engine: one source → analyse → condition → OSC/MIDI (+ UI snapshot)."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from music_analyse import config
from music_analyse.audio.analysis import Analyser
from music_analyse.audio.condition import ConditionedFrame, Conditioner
from music_analyse.audio.source import FileSource, LiveSource
from music_analyse.banks import BankParams
from music_analyse.output.addresses import BANK_IDS, FLOATS, TRIGGERS
from music_analyse.output.midi_out import MidiOutput
from music_analyse.output.osc_out import OscOutput
from music_analyse.tune import TuneParams, preset_normal


@dataclass
class EngineState:
    status: str = "idle"  # idle | running | error | starting
    error: str = ""
    mode: str = "file"
    frame: ConditionedFrame = field(default_factory=ConditionedFrame.empty)
    flash: dict[str, float] = field(
        default_factory=lambda: {k: 0.0 for k in (*TRIGGERS, *BANK_IDS)}
    )


class Engine:
    def __init__(self) -> None:
        self.analyser = Analyser()
        self.conditioner = Conditioner(tune=preset_normal())
        self.osc = OscOutput(
            host=config.OSC_HOST,
            port=config.OSC_PORT,
            enabled=config.OSC_ENABLED_DEFAULT,
        )
        self.midi = MidiOutput(
            port_name=config.MIDI_PORT_NAME,
            enabled=False,
        )
        self._midi_wanted = config.MIDI_ENABLED_DEFAULT
        self._midi_port_name = config.MIDI_PORT_NAME
        self._source: FileSource | LiveSource | None = None
        self._lock = threading.Lock()
        self.state = EngineState()
        self._flash_until: dict[str, float] = {k: 0.0 for k in (*TRIGGERS, *BANK_IDS)}
        # Default muted ON — silence speaker monitor; OSC/MIDI still run
        self._mute = bool(config.MUTE_DEFAULT)
        # ~3s heartbeat scope; cap at 4s so a longer window never leaks
        self._scope: deque[tuple[float, dict[str, float], dict[str, bool]]] = deque(
            maxlen=max(32, int(config.ANALYSIS_HZ * 4.0) + 8)
        )

    @property
    def mute(self) -> bool:
        return self._mute

    def set_mute(self, muted: bool) -> None:
        """Silence file playback monitor only. Does not stop analysis/OSC/MIDI."""
        self._mute = bool(muted)
        src = self._source
        if isinstance(src, FileSource):
            src.set_output_gain(0.0 if self._mute else 1.0)

    def apply_tune(self, tune: TuneParams) -> None:
        """Live-update conditioner Tune params while running."""
        self.conditioner.apply_tune(tune)

    def get_tune(self) -> TuneParams:
        return self.conditioner.tune

    def apply_banks(self, banks: list[BankParams]) -> None:
        self.conditioner.apply_banks(banks)

    def get_banks(self) -> list[BankParams]:
        return list(self.conditioner.banks)

    def configure_outputs(
        self,
        osc_enabled: bool,
        osc_host: str,
        osc_port: int,
        midi_enabled: bool,
        midi_port: str,
    ) -> None:
        self.osc.configure(osc_host, int(osc_port), bool(osc_enabled))
        self._midi_wanted = bool(midi_enabled)
        self._midi_port_name = midi_port or config.MIDI_PORT_NAME

    def start_file(self, path: str, play_audio: bool = True) -> None:
        self.stop()
        self._set_status("starting")
        try:
            self.analyser.reset()
            # Keep current tune; only reset envelopes / trigger state
            self.conditioner.reset()
            with self._lock:
                self._scope.clear()
            self._open_midi_if_needed()
            source = FileSource(path, play_audio=play_audio)
            source.set_output_gain(0.0 if self._mute else 1.0)
            source.start(self._on_block)
            self._source = source
            with self._lock:
                self.state.mode = "file"
                self.state.status = "running"
                self.state.error = ""
        except Exception as exc:
            self._fail(str(exc))

    def start_live(self, device: int | None) -> None:
        self.stop()
        self._set_status("starting")
        try:
            self.analyser.reset()
            self.conditioner.reset()
            with self._lock:
                self._scope.clear()
            self._open_midi_if_needed()
            source = LiveSource(device=device)
            source.start(self._on_block)
            self._source = source
            with self._lock:
                self.state.mode = "live"
                self.state.status = "running"
                self.state.error = ""
        except Exception as exc:
            self._fail(str(exc))

    def _open_midi_if_needed(self) -> None:
        if self._midi_wanted:
            try:
                self.midi.configure(self._midi_port_name, True)
            except Exception as exc:
                with self._lock:
                    self.state.error = f"MIDI: {exc}"
                self.midi.enabled = False
        else:
            self.midi.configure(self._midi_port_name, False)

    def stop(self) -> None:
        src = self._source
        self._source = None
        if src is not None:
            try:
                src.stop()
            except Exception:
                pass
        try:
            self.midi.close()
        except Exception:
            pass
        with self._lock:
            if self.state.status != "error":
                self.state.status = "idle"
            self.state.frame = ConditionedFrame.empty()
            self.state.flash = {k: 0.0 for k in (*TRIGGERS, *BANK_IDS)}
            # Freeze last window on stop (idle draw stays valid; no growth)

    def _fail(self, message: str) -> None:
        self.stop()
        with self._lock:
            self.state.status = "error"
            self.state.error = message

    def _set_status(self, status: str) -> None:
        with self._lock:
            self.state.status = status

    def _on_block(self, block: np.ndarray) -> None:
        try:
            raw = self.analyser.process(block)
            bank_raw = {
                b.key: self.analyser.band_energy_hz(b.lo_hz, b.hi_hz)
                for b in self.conditioner.banks
            }
            frame = self.conditioner.process(raw, bank_raw)
            now_mono = time.monotonic()
            with self._lock:
                self._scope.append(
                    (
                        now_mono,
                        {k: float(frame.floats.get(k, 0.0)) for k in (*FLOATS, *BANK_IDS)},
                        {k: bool(frame.triggers.get(k)) for k in (*TRIGGERS, *BANK_IDS)},
                    )
                )
            self.osc.send_frame(frame.triggers, frame.floats)
            self.midi.send_frame(frame.triggers, frame.floats)
            now = time.monotonic()
            with self._lock:
                self.state.frame = frame
                for name, bang in frame.triggers.items():
                    if bang:
                        self._flash_until[name] = now + config.TRIGGER_FLASH_S
                self.state.flash = {
                    k: 1.0 if now < self._flash_until[k] else 0.0
                    for k in (*TRIGGERS, *BANK_IDS)
                }
                if isinstance(self._source, FileSource) and self._source.last_error:
                    self.state.status = "error"
                    self.state.error = str(self._source.last_error)
                if isinstance(self._source, LiveSource) and self._source.last_error:
                    self.state.error = str(self._source.last_error)
                if self._source is not None and not self._source.is_running:
                    if self.state.status == "running":
                        self.state.status = "idle"
        except Exception as exc:
            self._fail(str(exc))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            frame = self.state.frame
            now = time.monotonic()
            flash = {
                k: 1.0 if now < self._flash_until[k] else 0.0
                for k in (*TRIGGERS, *BANK_IDS)
            }
            self.state.flash = flash
            return {
                "status": self.state.status,
                "error": self.state.error,
                "mode": self.state.mode,
                "mute": self._mute,
                "triggers": dict(frame.triggers),
                "floats": {
                    k: float(frame.floats.get(k, 0.0)) for k in (*FLOATS, *BANK_IDS)
                },
                "flash": flash,
            }

    def scope_samples(self, window_s: float = config.SCOPE_WINDOW_S) -> list[
        tuple[float, dict[str, float], dict[str, bool]]
    ]:
        """Oldest → newest samples in the last `window_s` seconds."""
        with self._lock:
            if not self._scope:
                return []
            cutoff = self._scope[-1][0] - float(window_s)
            return [s for s in self._scope if s[0] >= cutoff]
