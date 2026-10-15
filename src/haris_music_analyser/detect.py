"""Kick / snare onset detection on an isolated drums stem."""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np

from haris_music_analyser.models import Cue, CueSheet, DetectionMeta, SourceInfo
from haris_music_analyser.profile import load_profile


def detect_cues(
    drums_path: Path | str,
    *,
    profile: str | Path = "default",
    mix_path: Path | str | None = None,
) -> CueSheet:
    """Classify kick vs snare at each onset on the drums stem."""
    drums_path = Path(drums_path)
    cfg = load_profile(profile)
    y, sr = librosa.load(drums_path, sr=None, mono=True)
    duration = float(len(y) / sr)

    hop = int(cfg["onset"]["hop_length"])
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env,
        sr=sr,
        hop_length=hop,
        pre_max=int(cfg["onset"]["pre_max"]),
        post_max=int(cfg["onset"]["post_max"]),
        pre_avg=int(cfg["onset"]["pre_avg"]),
        post_avg=int(cfg["onset"]["post_avg"]),
        delta=float(cfg["onset"]["delta"]),
        wait=int(cfg["onset"]["wait"]),
        units="frames",
    )
    times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop)

    min_iv = float(cfg["onset"]["min_interval_sec"])
    times = _dedupe_times(times, min_iv)

    cues: list[Cue] = []
    win = int(float(cfg["classification"]["analysis_window_sec"]) * sr)
    for t in times:
        cue_type, vel = _classify_onset(y, sr, float(t), win, onset_env, hop, cfg)
        if cue_type is None:
            continue
        cues.append(Cue(time=float(t), type=cue_type, velocity=vel))

    sheet = CueSheet(
        cues=cues,
        source=SourceInfo(
            audio_path=str(Path(mix_path).resolve()) if mix_path else None,
            drums_stem_path=str(drums_path.resolve()),
            duration_sec=duration,
            sample_rate=int(sr),
        ),
        detection=DetectionMeta(profile=str(profile), locked=False),
    )
    print(f"[detect] {len(cues)} cues from {drums_path.name} ({duration:.1f}s)")
    return sheet


def _dedupe_times(times: np.ndarray, min_interval: float) -> np.ndarray:
    if len(times) == 0:
        return times
    kept = [float(times[0])]
    for t in times[1:]:
        if float(t) - kept[-1] >= min_interval:
            kept.append(float(t))
    return np.array(kept, dtype=np.float64)


def _classify_onset(
    y: np.ndarray,
    sr: int,
    time_sec: float,
    win: int,
    onset_env: np.ndarray,
    hop: int,
    cfg: dict,
) -> tuple[str | None, float]:
    start = int(time_sec * sr)
    end = min(len(y), start + win)
    if end - start < 64:
        return None, 0.0
    seg = y[start:end]

    # Spectral features on the hit window
    S = np.abs(librosa.stft(seg, n_fft=1024, hop_length=256)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=1024)
    centroid = float(np.mean(librosa.feature.spectral_centroid(S=S, sr=sr)))
    low_hz = float(cfg["classification"]["kick_low_hz"])
    sn_lo = float(cfg["classification"]["snare_low_hz"])
    sn_hi = float(cfg["classification"]["snare_high_hz"])

    def band_energy(f_lo: float, f_hi: float) -> float:
        mask = (freqs >= f_lo) & (freqs < f_hi)
        return float(np.sum(S[mask, :])) if np.any(mask) else 0.0

    e_low = band_energy(20, low_hz)
    e_mid = band_energy(sn_lo, sn_hi)
    e_total = e_low + e_mid + 1e-12
    low_ratio = e_low / e_total
    mid_ratio = e_mid / e_total

    kick_cent_max = float(cfg["classification"]["kick_centroid_max_hz"])
    snare_cent_min = float(cfg["classification"]["snare_centroid_min_hz"])
    kick_low_min = float(cfg["classification"]["kick_low_ratio_min"])
    snare_mid_min = float(cfg["classification"]["snare_mid_ratio_min"])
    amb = float(cfg["classification"]["ambiguous_centroid_hz"])

    kick_score = 0.0
    snare_score = 0.0
    if centroid <= kick_cent_max and low_ratio >= kick_low_min:
        kick_score = low_ratio * (1.0 - centroid / (kick_cent_max + 1))
    if centroid >= snare_cent_min and mid_ratio >= snare_mid_min:
        snare_score = mid_ratio * min(1.0, centroid / (snare_cent_min * 2))

    if kick_score <= 0 and snare_score <= 0:
        # Weak fallback: split by centroid only
        if centroid < amb:
            kick_score = 0.3
        else:
            snare_score = 0.3

    if kick_score >= snare_score:
        cue_type = "kick"
    else:
        cue_type = "snare"

    frame = int(time_sec * sr / hop)
    frame = min(max(0, frame), len(onset_env) - 1)
    strength = float(onset_env[frame])
    vel = _strength_to_velocity(strength, cfg)
    return cue_type, vel


def _strength_to_velocity(strength: float, cfg: dict) -> float:
    floor = float(cfg["velocity"]["onset_strength_floor"])
    ceil = float(cfg["velocity"]["onset_strength_ceil"])
    if strength <= floor:
        return 0.35
    if strength >= ceil:
        return 1.0
    return float(0.35 + 0.65 * (strength - floor) / (ceil - floor))
