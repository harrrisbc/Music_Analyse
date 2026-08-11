"""Causal IIR band-pass + per-block envelope (Extract = Filters)."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi

from music_analyse.audio.spectrum import power_to_unit


def _clamp_band(lo: float, hi: float, sr: float) -> tuple[float, float]:
    nyq = 0.49 * float(sr)
    lo = float(max(8.0, min(lo, nyq * 0.95)))
    hi = float(max(lo * 1.08, min(hi, nyq)))
    if hi <= lo:
        hi = min(nyq, lo * 1.2)
    return lo, hi


def design_sos(sr: float, lo: float, hi: float, kind: str = "band") -> np.ndarray:
    if kind == "low":
        cutoff = min(0.49 * sr, max(12.0, hi))
        return butter(2, cutoff, btype="lowpass", fs=sr, output="sos")
    if kind == "high":
        cutoff = min(0.45 * sr, max(20.0, lo))
        return butter(2, cutoff, btype="highpass", fs=sr, output="sos")
    lo, hi = _clamp_band(lo, hi, sr)
    return butter(2, [lo, hi], btype="bandpass", fs=sr, output="sos")


class IirBand:
    """Stateful SOS filter. process() returns the filtered block."""

    def __init__(
        self,
        sample_rate: float,
        lo_hz: float,
        hi_hz: float,
        kind: str = "band",
    ) -> None:
        self.sample_rate = float(sample_rate)
        self.lo_hz = float(lo_hz)
        self.hi_hz = float(hi_hz)
        self.kind = kind
        self.sos = design_sos(self.sample_rate, self.lo_hz, self.hi_hz, kind)
        self.zi = sosfilt_zi(self.sos) * 0.0

    def reset(self) -> None:
        self.zi = sosfilt_zi(self.sos) * 0.0

    def retune(self, lo_hz: float, hi_hz: float) -> None:
        if abs(lo_hz - self.lo_hz) < 0.5 and abs(hi_hz - self.hi_hz) < 0.5:
            return
        self.lo_hz = float(lo_hz)
        self.hi_hz = float(hi_hz)
        self.sos = design_sos(self.sample_rate, self.lo_hz, self.hi_hz, self.kind)
        self.zi = sosfilt_zi(self.sos) * 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        y, self.zi = sosfilt(self.sos, np.asarray(x, dtype=np.float64), zi=self.zi)
        return y.astype(np.float32)


def block_unit(y: np.ndarray) -> float:
    """Filtered-block power → same unit scale as factory floats."""
    power = float(np.mean(np.square(np.asarray(y, dtype=np.float64))))
    return power_to_unit(power)
