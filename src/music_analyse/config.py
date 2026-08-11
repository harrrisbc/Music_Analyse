"""Defaults — audio, OSC/MIDI, analysis heuristics, conditioner knobs."""

from __future__ import annotations

# Audio
SAMPLE_RATE = 22_050
BLOCK_SIZE = 512  # ~43 Hz analysis rate at SAMPLE_RATE
CHANNELS = 1
ANALYSIS_BUFFER_SEC = 4.0
ANALYSIS_HZ = SAMPLE_RATE / BLOCK_SIZE  # ~43.07

# Monitor scope (heartbeat strip)
SCOPE_WINDOW_S = 3.0
SCOPE_DEFAULT_CHANNEL = "vocal_presence"

# OSC
OSC_ENABLED_DEFAULT = True
OSC_HOST = "127.0.0.1"
OSC_PORT = 8000

# MIDI
MIDI_ENABLED_DEFAULT = True
MIDI_PORT_NAME = "Music Analyse"
MIDI_CHANNEL_TRIGGERS = 0  # ch 1 (0-indexed)
MIDI_CHANNEL_DRUMS = 9  # ch 10
MIDI_CHANNEL_CC = 0  # ch 1

# Analysis bands (raw feature extraction)
KICK_BAND = (40.0, 150.0)  # sub/low thud for kick transient
KICK_SHAPE_MID_BAND = (200.0, 2000.0)  # pitched harmonic region (piano-ish)
KICK_BEATER_BAND = (2000.0, 6000.0)  # optional click/beater bonus
SNARE_BAND = (150.0, 2500.0)
HIHAT_BAND = (5000.0, 10_000.0)
VOCAL_BAND = (300.0, 3400.0)
BASS_BAND = (20.0, 150.0)  # continuous bass float (piano OK)

# Beat / tempo
BPM_MIN = 60.0
BPM_MAX = 180.0
BPM_DEFAULT = 120.0
BEAT_PHASE_TOLERANCE = 0.08  # fraction of beat period

# --- Conditioner (floats: floor → adaptive norm → clamp → EMA) ---
NOISE_FLOOR = 0.01
NORM_WINDOW_S = 3.0
ATTACK_S = 0.03
RELEASE_S = 0.25
NORM_EPSILON = 1e-6

# Trigger: rising edge vs threshold + refractory
TRIGGER_THRESHOLD = 0.5
TRIGGER_THRESHOLDS = {
    "onset": 0.5,
    "kick": 0.55,  # superseded by KICK_THRESHOLD for kick path
    "snare": 0.55,
    "hihat": 0.5,
    "beat": 0.5,
}
REFRACTORY_MS = 80.0

# --- Kick detector (multi-gate; NOT f(bass_energy) alone) ---
# Score combines low transient + attack + (1 - harmonicity) + sub/mid shape.
# Bang only if all soft gates pass, score crosses KICK_THRESHOLD, then refractory.
KICK_THRESHOLD = 0.58
KICK_HARMONICITY_MAX = 0.45  # above → treat as pitched (piano) → suppress
KICK_MIN_FLUX = 0.22
KICK_MIN_ATTACK = 0.18
KICK_MIN_SHAPE = 0.35  # sub/(sub+mid) preference for thud vs harmonic mid
KICK_REFRACTORY_MS = 110.0
KICK_BEATER_WEIGHT = 0.12  # soft bonus only; never sole condition

# UI flash hold (visual only)
TRIGGER_FLASH_S = 0.08

# Audio monitor mute (File playback only; analysis/OSC/MIDI keep running)
MUTE_DEFAULT = True

# MIDI note / CC map (see also output.addresses)
MIDI_NOTES = {
    "beat": 36,
    "kick": 36,
    "snare": 38,
    "hihat": 42,
    "onset": 37,
    "bank1": 48,
    "bank2": 49,
    "bank3": 50,
    "bank4": 51,
}
MIDI_CCS = {
    "rms": 20,
    "bass_energy": 21,
    "vocal_presence": 22,
    "onset_strength": 23,
    "bpm": 24,
    "bank1": 30,
    "bank2": 31,
    "bank3": 32,
    "bank4": 33,
}
MIDI_NOTE_VELOCITY = 100
MIDI_NOTE_OFF_DELAY_MS = 40

# Legacy aliases (analysis used these before conditioner owned gates)
ONSET_THRESHOLD = TRIGGER_THRESHOLDS["onset"]
SNARE_THRESHOLD = TRIGGER_THRESHOLDS["snare"]
HIHAT_THRESHOLD = TRIGGER_THRESHOLDS["hihat"]
