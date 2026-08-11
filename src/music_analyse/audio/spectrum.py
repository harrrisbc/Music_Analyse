"""Shared spectral helpers — dB bands, log flux, flux floor, attack, FFT autocorr."""

from __future__ import annotations

from collections import deque

import numpy as np

from music_analyse import config


def band_power(mag: np.ndarray, freqs: np.ndarray, lo_hz: float, hi_hz: float) -> float:
    """Onesided Parseval power in [lo, hi) — same dBFS family as mean(x²)."""
    mask = (freqs >= lo_hz) & (freqs < hi_hz)
    if not np.any(mask):
        return 0.0
    n_fft = max(2, 2 * (len(mag) - 1))
    m = mag[mask]
    f = freqs[mask]
    nyq = float(freqs[-1]) if len(freqs) else 0.0
    scale = np.where((f > 0.0) & (f < nyq - 1e-9), 2.0, 1.0)
    return float(np.sum(m * m * scale) / (n_fft * n_fft))


def rms_power_unit(x: np.ndarray) -> float:
    """mean(x²) → dB → unit, same map as band energies."""
    power = float(np.mean(np.square(np.asarray(x, dtype=np.float64))))
    return power_to_unit(power)


def power_to_unit(power: float) -> float:
    db = 10.0 * np.log10(float(power) + config.BAND_POWER_EPS)
    span = config.BAND_DB_MAX - config.BAND_DB_MIN
    return float(np.clip((db - config.BAND_DB_MIN) / max(span, 1e-6), 0.0, 1.0))


def band_energy_unit(mag: np.ndarray, freqs: np.ndarray, lo_hz: float, hi_hz: float) -> float:
    return power_to_unit(band_power(mag, freqs, lo_hz, hi_hz))


def make_log_band_slices(
    freqs: np.ndarray,
    n_bands: int = config.ONSET_BANDS,
    fmin: float = 50.0,
    fmax: float = 10_000.0,
) -> list[np.ndarray]:
    hi = min(float(fmax), float(freqs[-1]) if len(freqs) else fmax)
    edges = np.geomspace(fmin, max(fmin * 1.01, hi), n_bands + 1)
    slices: list[np.ndarray] = []
    for i in range(n_bands):
        slices.append((freqs >= edges[i]) & (freqs < edges[i + 1]))
    return slices


def log_band_energies(mag: np.ndarray, slices: list[np.ndarray]) -> np.ndarray:
    out = np.zeros(len(slices), dtype=np.float64)
    for i, sl in enumerate(slices):
        if np.any(sl):
            out[i] = float(np.mean(mag[sl]))
    return np.log1p(out)


def positive_mean_diff(cur: np.ndarray, prev: np.ndarray) -> float:
    return float(np.mean(np.maximum(cur - prev, 0.0)))


def fft_autocorr_peak(x: np.ndarray, sample_rate: int, f_lo: float = 80.0, f_hi: float = 400.0) -> float:
    """Best normalized autocorr in the [f_lo, f_hi] lag range. Vectorized."""
    y = np.asarray(x, dtype=np.float64)
    y = y - float(np.mean(y))
    n = len(y)
    if n < 16:
        return 0.0
    min_lag = max(1, int(sample_rate / f_hi))
    max_lag = min(n - 1, int(sample_rate / f_lo))
    if max_lag <= min_lag + 2:
        return 0.0
    nfft = 1 << (2 * n - 1).bit_length()
    spec = np.fft.rfft(y, n=nfft)
    ac = np.fft.irfft(spec * np.conjugate(spec), n=nfft)[: n]
    denom = float(ac[0]) + 1e-12
    best = float(np.max(ac[min_lag : max_lag + 1]) / denom)
    return float(min(1.0, max(0.0, best)))


def harmonicity(x: np.ndarray, mag: np.ndarray, freqs: np.ndarray, sample_rate: int) -> float:
    mask = (freqs >= 100.0) & (freqs <= 1500.0)
    if np.any(mask):
        band = mag[mask]
        peakiness = float(np.max(band) / (np.mean(band) + 1e-12))
        peak_score = float(min(1.0, max(0.0, (peakiness - 2.0) / 8.0)))
    else:
        peak_score = 0.0
    ac_score = fft_autocorr_peak(x, sample_rate)
    return float(min(1.0, 0.55 * peak_score + 0.45 * ac_score))


class AttackTracker:
    """Dual-EMA attack on one scalar (band energy, not broadband RMS)."""

    def __init__(self, dt: float, fast_s: float = 0.008, slow_s: float = 0.080) -> None:
        self._a_fast = 1.0 - pow(2.718281828, -dt / fast_s)
        self._a_slow = 1.0 - pow(2.718281828, -dt / slow_s)
        self.fast = 0.0
        self.slow = 0.0

    def reset(self) -> None:
        self.fast = 0.0
        self.slow = 0.0

    def update(self, x: float) -> float:
        x = float(x)
        self.fast += self._a_fast * (x - self.fast)
        self.slow += self._a_slow * (x - self.slow)
        gap = max(0.0, self.fast - self.slow)
        return float(min(1.0, gap / (self.slow + 1e-4) * 2.0))


class FluxTracker:
    """Relative rise vs recent median, gated by an absolute floor."""

    def __init__(
        self,
        abs_floor: float = config.FLUX_ABS_FLOOR,
        win: int = config.FLUX_MEDIAN_WIN,
    ) -> None:
        self.abs_floor = abs_floor
        self.prev = 0.0
        self.hist: deque[float] = deque(maxlen=max(4, win))

    def reset(self) -> None:
        self.prev = 0.0
        self.hist.clear()

    def update(self, energy: float) -> float:
        e = float(energy)
        self.hist.append(e)
        if e < self.abs_floor:
            self.prev = e
            return 0.0
        med = float(np.median(self.hist)) if self.hist else 0.0
        flux = max(0.0, e - self.prev) / (med + 1e-3)
        self.prev = e
        return float(min(1.0, flux))


class OnsetPeakPicker:
    """Local-max onset for IOI (not every flux frame)."""

    def __init__(self, win: int = 24, ratio: float = 1.6, abs_floor: float = 0.02) -> None:
        self.hist: deque[float] = deque(maxlen=win)
        self.prev = 0.0
        self.prev2 = 0.0
        self.ratio = ratio
        self.abs_floor = abs_floor

    def reset(self) -> None:
        self.hist.clear()
        self.prev = 0.0
        self.prev2 = 0.0

    def push(self, flux: float) -> bool:
        """True if the *previous* frame was a local peak (one-frame delay)."""
        self.hist.append(self.prev)
        peaked = (
            self.prev > self.prev2
            and self.prev >= flux
            and self.prev >= self.abs_floor
        )
        if peaked and len(self.hist) >= 4:
            med = float(np.median(self.hist))
            peaked = self.prev >= med * self.ratio
        self.prev2 = self.prev
        self.prev = float(flux)
        return bool(peaked)
