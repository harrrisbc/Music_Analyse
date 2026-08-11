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
from music_analyse.audio.lookahead import TriggerLookahead
from music_analyse.audio.pro_analysis import ProAnalyser
from music_analyse.audio.source import FileSource, LiveSource
from music_analyse.banks import BankParams
from music_analyse.output.addresses import BANK_IDS, FLOATS, TRIGGERS
from music_analyse.output.midi_out import MidiOutput
from music_analyse.output.osc_out import OscOutput
from music_analyse.tempo import TempoClock
from music_analyse.tune import TuneParams, preset_normal


@dataclass
class EngineState:
    status: str = "idle"  # idle | running | error | starting | switching
    error: str = ""
    mode: str = "file"  # source: file | live
    analysis_mode: str = config.MODE_DEFAULT  # live | pro
    extract_mode: str = config.EXTRACT_DEFAULT  # filters | stems
    frame: ConditionedFrame = field(default_factory=ConditionedFrame.empty)
    flash: dict[str, float] = field(
        default_factory=lambda: {k: 0.0 for k in (*TRIGGERS, *BANK_IDS)}
    )


class Engine:
    def __init__(self) -> None:
        self.analysis_mode = config.MODE_DEFAULT
        self.extract_mode = config.EXTRACT_DEFAULT
        self.lookahead_ms = float(config.PRO_LOOKAHEAD_MS)
        self.analyser: Analyser | ProAnalyser = Analyser(extract_mode=self.extract_mode)
        self.conditioner = Conditioner(tune=preset_normal())
        self.lookahead = TriggerLookahead(
            hop_s=config.BLOCK_SIZE / config.SAMPLE_RATE,
            lookahead_ms=self.lookahead_ms,
        )
        self.tempo = TempoClock()
        self._last_start: tuple[str, object] | None = None
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
        self.analyser.set_banks(self.conditioner.banks)

    def get_banks(self) -> list[BankParams]:
        return list(self.conditioner.banks)

    def set_analysis_mode(self, mode: str, lookahead_ms: float | None = None) -> None:
        mode = "pro" if str(mode).lower() == "pro" else "live"
        if lookahead_ms is not None:
            self.lookahead_ms = float(max(60.0, min(200.0, lookahead_ms)))
            self.lookahead.set_lookahead_ms(self.lookahead_ms)
        if mode == self.analysis_mode:
            return
        self.analysis_mode = mode
        self.analyser = self._make_analyser()
        self.lookahead.reset()
        with self._lock:
            self.state.analysis_mode = mode

    def set_extract_mode(self, mode: str) -> None:
        mode = "stems" if str(mode).lower() == "stems" else "filters"
        if mode == self.extract_mode:
            return
        self.extract_mode = mode
        self.analyser = self._make_analyser()
        self.lookahead.reset()
        with self._lock:
            self.state.extract_mode = mode

    def _stream_params(self) -> tuple[int, int]:
        if self.analysis_mode == "pro":
            return config.PRO_SAMPLE_RATE, config.PRO_HOP
        return config.SAMPLE_RATE, config.BLOCK_SIZE

    def _make_analyser(self) -> Analyser | ProAnalyser:
        if self.analysis_mode == "pro":
            analyser = ProAnalyser(extract_mode=self.extract_mode)
        else:
            analyser = Analyser(extract_mode=self.extract_mode)
        analyser.set_banks(self.conditioner.banks)
        return analyser

    def tap_tempo(self) -> float:
        return self.tempo.tap()

    def set_bpm(self, bpm: float) -> float:
        return self.tempo.set_bpm(bpm)

    def clear_tap_tempo(self) -> None:
        self.tempo.clear()

    def restore_tempo(self, bpm: float, locked: bool) -> None:
        self.tempo.restore(bpm, locked)

    def set_lookahead_ms(self, lookahead_ms: float) -> None:
        self.lookahead_ms = float(max(60.0, min(200.0, lookahead_ms)))
        self.lookahead.set_lookahead_ms(self.lookahead_ms)

    def restart_if_running(self) -> None:
        if self.snapshot().get("status") != "running" or self._last_start is None:
            return
        kind, arg = self._last_start
        self._set_status("switching")
        if kind == "file":
            self.start_file(str(arg))
        else:
            self.start_live(arg if isinstance(arg, int) else None)

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
        if self._source is not None:
            self._open_midi_if_needed()

    def start_file(self, path: str, play_audio: bool = True) -> None:
        self.stop(clear_tap=False)
        self._set_status("starting")
        try:
            self.analyser.reset()
            # Keep current tune; only reset envelopes / trigger state
            self.conditioner.reset()
            with self._lock:
                self._scope.clear()
            self.lookahead.reset()
            self._open_midi_if_needed()
            sr, hop = self._stream_params()
            source = FileSource(path, sample_rate=sr, block_size=hop, play_audio=play_audio)
            source.set_output_gain(0.0 if self._mute else 1.0)
            source.start(self._on_block)
            self._source = source
            self._last_start = ("file", path)
            with self._lock:
                self.state.mode = "file"
                self.state.status = "running"
                self.state.error = ""
                self.state.analysis_mode = self.analysis_mode
                self.state.extract_mode = self.extract_mode
        except Exception as exc:
            self._fail(str(exc))

    def start_live(self, device: int | None) -> None:
        self.stop(clear_tap=False)
        self._set_status("starting")
        try:
            self.analyser.reset()
            self.conditioner.reset()
            with self._lock:
                self._scope.clear()
            self.lookahead.reset()
            self._open_midi_if_needed()
            sr, hop = self._stream_params()
            try:
                source = LiveSource(device=device, sample_rate=sr, block_size=hop)
                source.start(self._on_block)
            except Exception:
                if self.analysis_mode == "pro" and sr != config.SAMPLE_RATE:
                    # Device refused 44.1 kHz — keep Pro analysis at Live rate
                    self.analyser = ProAnalyser(
                        sample_rate=config.SAMPLE_RATE,
                        hop=config.BLOCK_SIZE,
                        n_fft=config.LIVE_N_FFT,
                        extract_mode=self.extract_mode,
                    )
                    self.analyser.set_banks(self.conditioner.banks)
                    source = LiveSource(
                        device=device,
                        sample_rate=config.SAMPLE_RATE,
                        block_size=config.BLOCK_SIZE,
                    )
                    source.start(self._on_block)
                else:
                    raise
            self._source = source
            self._last_start = ("live", device)
            with self._lock:
                self.state.mode = "live"
                self.state.status = "running"
                self.state.error = ""
                self.state.analysis_mode = self.analysis_mode
                self.state.extract_mode = self.extract_mode
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

    def stop(self, *, clear_tap: bool = True) -> None:
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
        if clear_tap:
            self.clear_tap_tempo()
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
            tap_beat = False
            if self.tempo.locked:
                raw.bpm = self.tempo.bpm
                tap_beat = self.tempo.poll(time.monotonic())
                raw.beat_pulse = tap_beat
            else:
                self.tempo.follow_auto(raw.bpm)
            bank_raw = self.analyser.bank_energies()
            frame = self.conditioner.process(raw, bank_raw)
            if self.analysis_mode == "pro":
                gated = self.lookahead.process(
                    frame.triggers, frame.floats, raw, bank_raw
                )
                frame.triggers = {**frame.triggers, **gated}
                if self.tempo.locked:
                    # Tap grid must not wait for look-ahead
                    frame.triggers["beat"] = tap_beat
                    frame.floats["bpm"] = self.tempo.bpm
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
                "analysis_mode": self.analysis_mode,
                "extract_mode": self.extract_mode,
                "stems_extra_ms": float(self.analyser.extra_ms()),
                "lookahead_ms": self.lookahead_ms,
                "bpm": self.tempo.bpm,
                "tap_locked": self.tempo.locked,
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
