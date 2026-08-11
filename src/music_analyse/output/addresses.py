"""Single source of truth for OSC addresses and MIDI mappings."""

from __future__ import annotations

from music_analyse import config

TRIGGERS = ("beat", "kick", "snare", "hihat", "onset")
FLOATS = ("rms", "bass_energy", "vocal_presence", "onset_strength", "bpm")
BANK_IDS = ("bank1", "bank2", "bank3", "bank4")

OSC_TRIGGER_ADDR = {name: f"/ma/trigger/{name}" for name in TRIGGERS}
OSC_TRIGGER_ADDR.update({name: f"/ma/trigger/{name}" for name in BANK_IDS})
OSC_FLOAT_ADDR = {
    "rms": "/ma/float/rms",
    "bass_energy": "/ma/float/bass_energy",
    "vocal_presence": "/ma/float/vocal_presence",
    "onset_strength": "/ma/float/onset_strength",
    "bpm": "/ma/float/bpm",
}
OSC_FLOAT_ADDR.update({name: f"/ma/float/{name}" for name in BANK_IDS})

MIDI_NOTES = dict(config.MIDI_NOTES)
MIDI_CCS = dict(config.MIDI_CCS)


def bpm_to_cc(bpm: float) -> int:
    """Scale BPM into MIDI CC 0–127 (60–180 → 0–127)."""
    lo, hi = config.BPM_MIN, config.BPM_MAX
    clamped = max(lo, min(hi, float(bpm)))
    return int(round((clamped - lo) / (hi - lo) * 127.0))
