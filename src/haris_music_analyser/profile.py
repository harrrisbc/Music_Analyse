"""Per-song detection profiles (YAML). Defaults become tunable later."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_PROFILE: dict[str, Any] = {
    "onset": {
        "hop_length": 512,
        "pre_max": 3,
        "post_max": 3,
        "pre_avg": 3,
        "post_avg": 5,
        "delta": 0.07,
        "wait": 4,
        "min_interval_sec": 0.045,
    },
    "classification": {
        "analysis_window_sec": 0.06,
        "kick_low_hz": 150,
        "snare_low_hz": 150,
        "snare_high_hz": 6000,
        "kick_centroid_max_hz": 450,
        "snare_centroid_min_hz": 900,
        "kick_low_ratio_min": 0.55,
        "snare_mid_ratio_min": 0.35,
        "ambiguous_centroid_hz": 650,
    },
    "velocity": {
        "onset_strength_floor": 0.15,
        "onset_strength_ceil": 2.5,
    },
    "export": {
        "midi_kick_note": 36,
        "midi_snare_note": 38,
        "ticks_per_beat": 480,
        "default_bpm": 120.0,
    },
    "playback": {
        "osc_kick_address": "/music/kick",
        "osc_snare_address": "/music/snare",
        "lookahead_sec": 0.0,
        "trigger_tolerance_sec": 0.012,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_profile(name_or_path: str | Path | None = None) -> dict[str, Any]:
    if name_or_path is None or str(name_or_path) == "default":
        return dict(DEFAULT_PROFILE)

    path = Path(name_or_path)
    if path.is_file():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return _deep_merge(DEFAULT_PROFILE, raw)

    # Named profile: package data, then repo-root profiles/ (dev)
    pkg_profiles = Path(__file__).resolve().parent / "profiles" / f"{name_or_path}.yaml"
    if pkg_profiles.is_file():
        raw = yaml.safe_load(pkg_profiles.read_text(encoding="utf-8")) or {}
        return _deep_merge(DEFAULT_PROFILE, raw)
    repo_profiles = Path(__file__).resolve().parents[2] / "profiles" / f"{name_or_path}.yaml"
    if repo_profiles.is_file():
        raw = yaml.safe_load(repo_profiles.read_text(encoding="utf-8")) or {}
        return _deep_merge(DEFAULT_PROFILE, raw)

    raise FileNotFoundError(f"profile not found: {name_or_path}")
