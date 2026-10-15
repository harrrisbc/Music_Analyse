"""Manual / semi-auto cue sheet edits."""

from __future__ import annotations

from pathlib import Path

from haris_music_analyser.models import Cue, CueSheet


def lock_sheet(sheet: CueSheet) -> CueSheet:
    sheet.detection.locked = True
    return sheet


def add_cue(
    sheet: CueSheet,
    time: float,
    cue_type: str,
    velocity: float = 1.0,
    bar: int | None = None,
) -> CueSheet:
    sheet.cues.append(Cue(time=time, type=cue_type, velocity=velocity, bar=bar))
    return sheet


def remove_cue(sheet: CueSheet, index: int) -> CueSheet:
    cues = sheet.sorted_cues()
    if index < 0 or index >= len(cues):
        raise IndexError(f"cue index out of range: {index} (have {len(cues)})")
    target = cues[index]
    sheet.cues = [c for c in sheet.cues if not (c.time == target.time and c.type == target.type)]
    return sheet


def list_cues(sheet: CueSheet) -> str:
    lines = []
    for i, c in enumerate(sheet.sorted_cues()):
        bar = f" bar={c.bar}" if c.bar is not None else ""
        lines.append(f"{i:4d}  {c.time:8.3f}s  {c.type:5s}  vel={c.velocity:.2f}{bar}")
    locked = "LOCKED" if sheet.detection.locked else "editable"
    return f"({len(sheet.cues)} cues, {locked})\n" + "\n".join(lines)


def load_or_raise(path: Path | str) -> CueSheet:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return CueSheet.load(path)
