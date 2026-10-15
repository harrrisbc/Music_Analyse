"""Cue sheet data model and JSON I/O."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

CueType = Literal["kick", "snare"]
SCHEMA_VERSION = "1.0"


@dataclass
class Cue:
    time: float
    type: CueType
    velocity: float
    bar: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "time": round(self.time, 6),
            "type": self.type,
            "velocity": round(max(0.0, min(1.0, self.velocity)), 4),
        }
        if self.bar is not None:
            d["bar"] = self.bar
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Cue:
        t = data["type"]
        if t not in ("kick", "snare"):
            raise ValueError(f"invalid cue type: {t}")
        return cls(
            time=float(data["time"]),
            type=t,
            velocity=float(data.get("velocity", 1.0)),
            bar=int(data["bar"]) if data.get("bar") is not None else None,
        )


@dataclass
class SourceInfo:
    audio_path: str | None = None
    drums_stem_path: str | None = None
    duration_sec: float | None = None
    sample_rate: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class DetectionMeta:
    profile: str = "default"
    locked: bool = False
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"profile": self.profile, "locked": self.locked}
        if self.notes:
            d["notes"] = self.notes
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DetectionMeta:
        if not data:
            return cls()
        return cls(
            profile=str(data.get("profile", "default")),
            locked=bool(data.get("locked", False)),
            notes=data.get("notes"),
        )


@dataclass
class CueSheet:
    cues: list[Cue] = field(default_factory=list)
    source: SourceInfo = field(default_factory=SourceInfo)
    detection: DetectionMeta = field(default_factory=DetectionMeta)
    schema_version: str = SCHEMA_VERSION

    def sorted_cues(self) -> list[Cue]:
        return sorted(self.cues, key=lambda c: c.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source.to_dict(),
            "detection": self.detection.to_dict(),
            "cues": [c.to_dict() for c in self.sorted_cues()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CueSheet:
        ver = data.get("schema_version", "1.0")
        if ver != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {ver!r} (expected {SCHEMA_VERSION})")
        cues = [Cue.from_dict(c) for c in data.get("cues", [])]
        src = data.get("source") or {}
        source = SourceInfo(
            audio_path=src.get("audio_path"),
            drums_stem_path=src.get("drums_stem_path"),
            duration_sec=src.get("duration_sec"),
            sample_rate=src.get("sample_rate"),
        )
        return cls(
            cues=cues,
            source=source,
            detection=DetectionMeta.from_dict(data.get("detection")),
            schema_version=ver,
        )

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> CueSheet:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def lock_copy(self) -> CueSheet:
        """Return a copy marked locked (for playback)."""
        from copy import deepcopy

        out = deepcopy(self)
        out.detection.locked = True
        return out
