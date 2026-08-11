"""MIDI output (virtual or hardware port)."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from typing import Any

import mido

from music_analyse import config
from music_analyse.output.addresses import (
    BANK_IDS,
    FLOATS,
    MIDI_CCS,
    MIDI_NOTES,
    TRIGGERS,
    bpm_to_cc,
)


def list_midi_output_names() -> list[str]:
    """
    List MIDI outputs.

    `mido.get_output_names()` / python-rtmidi can **abort the process** on
    some macOS CoreMIDI states. Probe in a short-lived subprocess so a crash
    cannot take down the UI.
    """
    names = [config.MIDI_PORT_NAME]
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import mido; print('\\n'.join(mido.get_output_names()))",
            ],
            capture_output=True,
            text=True,
            timeout=2.5,
            check=False,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                label = line.strip()
                if label and label not in names:
                    names.append(label)
    except Exception:
        pass
    return names


class MidiOutput:
    def __init__(
        self,
        port_name: str = config.MIDI_PORT_NAME,
        enabled: bool = True,
    ) -> None:
        self.port_name = port_name
        self.enabled = enabled
        self._port: Any = None
        self._lock = threading.Lock()
        if enabled:
            self.open()

    def open(self) -> None:
        """Open MIDI out. Never enumerate ports here — listing can abort on macOS."""
        self.close()
        if not self.enabled:
            return
        try:
            if self.port_name == config.MIDI_PORT_NAME:
                self._port = mido.open_output(self.port_name, virtual=True)
            else:
                self._port = mido.open_output(self.port_name)
        except Exception:
            self._port = None
            raise

    def configure(self, port_name: str, enabled: bool) -> None:
        self.port_name = port_name
        self.enabled = enabled
        if enabled:
            self.open()
        else:
            self.close()

    def send_frame(self, triggers: dict[str, bool], floats: dict[str, float]) -> None:
        if not self.enabled or self._port is None:
            return
        with self._lock:
            for name in (*TRIGGERS, *BANK_IDS):
                if not triggers.get(name):
                    continue
                note = MIDI_NOTES[name]
                channel = (
                    config.MIDI_CHANNEL_DRUMS
                    if name in ("kick", "snare", "hihat")
                    else config.MIDI_CHANNEL_TRIGGERS
                )
                self._port.send(
                    mido.Message(
                        "note_on",
                        note=note,
                        velocity=config.MIDI_NOTE_VELOCITY,
                        channel=channel,
                    )
                )
                threading.Thread(
                    target=self._note_off_later,
                    args=(note, channel),
                    daemon=True,
                ).start()

            for name in (*FLOATS, *BANK_IDS):
                if name not in floats or name not in MIDI_CCS:
                    continue
                value = floats[name]
                if name == "bpm":
                    cc_val = bpm_to_cc(value)
                else:
                    cc_val = int(max(0, min(127, round(float(value) * 127.0))))
                self._port.send(
                    mido.Message(
                        "control_change",
                        control=MIDI_CCS[name],
                        value=cc_val,
                        channel=config.MIDI_CHANNEL_CC,
                    )
                )

    def _note_off_later(self, note: int, channel: int) -> None:
        time.sleep(config.MIDI_NOTE_OFF_DELAY_MS / 1000.0)
        with self._lock:
            if self._port is None:
                return
            try:
                self._port.send(
                    mido.Message("note_off", note=note, velocity=0, channel=channel)
                )
            except Exception:
                pass

    def close(self) -> None:
        with self._lock:
            if self._port is not None:
                try:
                    self._port.close()
                except Exception:
                    pass
                self._port = None
