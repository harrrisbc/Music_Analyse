"""Session + last-used JSON (stdlib only). Shared by named files and quit restore."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from music_analyse import config
from music_analyse.banks import BankParams, default_banks, ensure_four
from music_analyse.tune import TuneParams, preset_normal

SESSION_VERSION = 1


def last_used_dir() -> Path:
    return Path.home() / ".music_analyse"


def last_used_path() -> Path:
    return last_used_dir() / "last_used.json"


def documents_dir() -> Path:
    docs = Path.home() / "Documents"
    return docs if docs.is_dir() else Path.home()


def default_payload() -> dict[str, Any]:
    return {
        "version": SESSION_VERSION,
        "view": "show",
        "source": {
            "mode": "file",
            "file_path": "",
            "live_device_label": "",
        },
        "transport": {"mute": bool(config.MUTE_DEFAULT)},
        "analysis": {
            "mode": config.MODE_DEFAULT,
            "lookahead_ms": int(config.PRO_LOOKAHEAD_MS),
            "extract": config.EXTRACT_DEFAULT,
        },
        "tempo": {
            "bpm": float(config.BPM_DEFAULT),
            "tap_locked": False,
        },
        "osc": {
            "enabled": bool(config.OSC_ENABLED_DEFAULT),
            "host": str(config.OSC_HOST),
            "port": int(config.OSC_PORT),
        },
        "midi": {
            "enabled": bool(config.MIDI_ENABLED_DEFAULT),
            "port": str(config.MIDI_PORT_NAME),
        },
        "tune": preset_normal().to_dict(),
        "banks": [b.to_dict() for b in default_banks()],
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize(data: Any) -> dict[str, Any]:
    """Unknown keys ignored; missing keys → defaults."""
    out = default_payload()
    if not isinstance(data, dict):
        return out

    src = _as_dict(data.get("source"))
    tr = _as_dict(data.get("transport"))
    an = _as_dict(data.get("analysis"))
    te = _as_dict(data.get("tempo"))
    osc = _as_dict(data.get("osc"))
    midi = _as_dict(data.get("midi"))

    view = str(data.get("view") or "show").lower()
    out["view"] = "setup" if view == "setup" else "show"

    mode = str(src.get("mode") or "file").lower()
    out["source"]["mode"] = "live" if mode == "live" else "file"
    out["source"]["file_path"] = str(src.get("file_path") or "")
    out["source"]["live_device_label"] = str(src.get("live_device_label") or "")

    if "mute" in tr:
        out["transport"]["mute"] = bool(tr["mute"])

    am = str(an.get("mode") or out["analysis"]["mode"]).lower()
    out["analysis"]["mode"] = "pro" if am == "pro" else "live"
    try:
        la = float(an.get("lookahead_ms", out["analysis"]["lookahead_ms"]))
        choices = config.PRO_LOOKAHEAD_CHOICES
        out["analysis"]["lookahead_ms"] = int(min(choices, key=lambda c: abs(float(c) - la)))
    except (TypeError, ValueError):
        pass
    ex = str(an.get("extract") or "").lower()
    if ex in ("filters", "stems"):
        out["analysis"]["extract"] = ex

    try:
        bpm = float(te.get("bpm", out["tempo"]["bpm"]))
        out["tempo"]["bpm"] = float(max(config.TAP_BPM_LO, min(config.TAP_BPM_HI, bpm)))
    except (TypeError, ValueError):
        pass
    if "tap_locked" in te:
        out["tempo"]["tap_locked"] = bool(te["tap_locked"])

    if "enabled" in osc:
        out["osc"]["enabled"] = bool(osc["enabled"])
    host = str(osc.get("host") or "").strip()
    if host:
        out["osc"]["host"] = host
    try:
        out["osc"]["port"] = int(float(osc.get("port", out["osc"]["port"])))
    except (TypeError, ValueError):
        pass

    if "enabled" in midi:
        out["midi"]["enabled"] = bool(midi["enabled"])
    port = str(midi.get("port") or "").strip()
    if port:
        out["midi"]["port"] = port

    if isinstance(data.get("tune"), dict):
        out["tune"] = TuneParams.from_dict(data["tune"]).to_dict()

    parsed: list[BankParams] = []
    for item in _as_list(data.get("banks")):
        bank = BankParams.from_dict(item)
        if bank is not None:
            parsed.append(bank)
    if parsed:
        out["banks"] = [b.to_dict() for b in ensure_four(parsed)]

    try:
        out["version"] = int(data.get("version", SESSION_VERSION))
    except (TypeError, ValueError):
        out["version"] = SESSION_VERSION
    return out


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(normalize(payload), indent=2) + "\n"


def load(path: Path | str) -> dict[str, Any] | None:
    try:
        text = Path(path).read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError):
        return None
    return normalize(data)


def save(path: Path | str, payload: dict[str, Any]) -> None:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(dumps(payload), encoding="utf-8")
    tmp.replace(dest)


def load_last_used() -> dict[str, Any] | None:
    path = last_used_path()
    if not path.is_file():
        return None
    return load(path)


def save_last_used(payload: dict[str, Any]) -> None:
    save(last_used_path(), payload)
