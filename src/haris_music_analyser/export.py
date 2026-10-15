"""Export cue sheets to MIDI and re-save JSON."""

from __future__ import annotations

from pathlib import Path

import mido

from haris_music_analyser.models import CueSheet
from haris_music_analyser.profile import load_profile


def export_midi(sheet: CueSheet, midi_path: Path | str, *, profile: str | Path = "default") -> Path:
    midi_path = Path(midi_path)
    cfg = load_profile(profile)
    exp = cfg["export"]
    kick_note = int(exp["midi_kick_note"])
    snare_note = int(exp["midi_snare_note"])
    tpb = int(exp["ticks_per_beat"])
    bpm = float(exp["default_bpm"])

    mid = mido.MidiFile(ticks_per_beat=tpb)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))

    sec_per_tick = 60.0 / bpm / tpb
    events: list[tuple[float, mido.Message]] = []
    for cue in sheet.sorted_cues():
        note = kick_note if cue.type == "kick" else snare_note
        vel = max(1, min(127, int(round(cue.velocity * 127))))
        events.append((cue.time, mido.Message("note_on", note=note, velocity=vel, time=0)))
        events.append((cue.time + 0.05, mido.Message("note_off", note=note, velocity=0, time=0)))

    events.sort(key=lambda e: e[0])
    last_sec = 0.0
    for t_sec, msg in events:
        delta_ticks = max(0, int(round((t_sec - last_sec) / sec_per_tick)))
        msg.time = delta_ticks
        track.append(msg)
        last_sec = t_sec

    midi_path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(midi_path)
    print(f"[export] MIDI → {midi_path}")
    return midi_path


def export_bundle(
    sheet: CueSheet,
    out_dir: Path | str,
    *,
    profile: str | Path = "default",
    json_name: str = "cues.json",
    midi_name: str = "cues.mid",
) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / json_name
    sheet.save(json_path)
    midi_path = export_midi(sheet, out_dir / midi_name, profile=profile)
    return json_path, midi_path
