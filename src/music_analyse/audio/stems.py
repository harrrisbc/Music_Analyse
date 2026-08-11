"""Stem separators — Stem-lite (causal HPSS + low crossover) is required."""

from __future__ import annotations

from collections import deque
from typing import Protocol

import numpy as np
from numpy.fft import irfft, rfft, rfftfreq

from music_analyse import config
from music_analyse.audio.filters import IirBand


class StemSeparator(Protocol):
    def reset(self) -> None: ...

    def process(self, block: np.ndarray) -> dict[str, np.ndarray]: ...

    def extra_ms(self) -> float: ...


class HpssLiteSeparator:
    """
    Causal HPSS-lite on a rolling spec, then IFFT the newest hop.
    drums ← perc · vocals ← harmonic mid · bass ← LPF mix · other ← residual
    """

    def __init__(
        self,
        sample_rate: int,
        hop: int,
        n_fft: int,
        spec_frames: int = 48,
    ) -> None:
        self.sample_rate = sample_rate
        self.hop = hop
        self.n_fft = n_fft
        self._window = np.hanning(n_fft).astype(np.float32)
        self._overlap = np.zeros(n_fft, dtype=np.float32)
        self._spec: deque[np.ndarray] = deque(maxlen=max(16, spec_frames))
        self._freqs = rfftfreq(n_fft, 1.0 / sample_rate)
        self._harm_ema: np.ndarray | None = None
        self._bass_lp = IirBand(sample_rate, 20.0, config.FILTER_BASS_LP, kind="low")
        self._vocal_bp = IirBand(sample_rate, *config.FILTER_VOCAL, kind="band")
        self._hop_i = 0
        self.last_tone_like = 0.0

    def extra_ms(self) -> float:
        return 0.5 * 1000.0 * self.n_fft / max(self.sample_rate, 1)

    def reset(self) -> None:
        self._overlap[:] = 0
        self._spec.clear()
        self._harm_ema = None
        self._bass_lp.reset()
        self._vocal_bp.reset()
        self._hop_i = 0
        self.last_tone_like = 0.0

    def process(self, block: np.ndarray) -> dict[str, np.ndarray]:
        x = np.asarray(block, dtype=np.float32).reshape(-1)
        if len(x) < self.hop:
            x = np.concatenate([x, np.zeros(self.hop - len(x), dtype=np.float32)])
        else:
            x = x[: self.hop]

        self._overlap = np.concatenate([self._overlap[self.hop :], x])
        self._hop_i += 1
        frame = self._overlap * self._window
        spec = rfft(frame)
        mag = np.abs(spec).astype(np.float64)
        self._spec.append(mag)

        perc_m, harm_m = self._split(mag)
        self.last_tone_like = self._tone_like(mag)
        phase = np.exp(1j * np.angle(spec))
        drums_td = irfft(perc_m * phase, n=self.n_fft).astype(np.float32)
        harm_td = irfft(harm_m * phase, n=self.n_fft).astype(np.float32)
        drums = drums_td[-self.hop :]
        harm = harm_td[-self.hop :]

        bass = self._bass_lp.process(x)
        vocals = self._vocal_bp.process(harm)
        other = x - drums - vocals - bass
        other = np.clip(other, -2.0, 2.0)
        return {
            "mix": x,
            "drums": drums,
            "vocals": vocals.astype(np.float32, copy=False),
            "bass": bass.astype(np.float32, copy=False),
            "other": other.astype(np.float32),
            "tone_like": self.last_tone_like,
        }

    def _split(self, mag: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        k_f = 15
        pad = k_f // 2
        padded = np.pad(mag, (pad, pad), mode="edge")
        perc = np.median(np.lib.stride_tricks.sliding_window_view(padded, k_f), axis=-1)

        neigh = np.pad(mag, 2, mode="edge")
        avg = (neigh[:-4] + neigh[1:-3] + neigh[3:-1] + neigh[4:]) * 0.25
        peak_r = mag / (avg + 1e-12)
        sine = np.clip((peak_r - 1.6) / 2.5, 0.0, 1.0)

        if self._harm_ema is None:
            self._harm_ema = np.zeros_like(mag)
        # ~3-hop lock on sustains; transients stay ahead of the EMA
        self._harm_ema = 0.72 * self._harm_ema + 0.28 * mag

        if len(self._spec) >= 4:
            s = np.stack(list(self._spec), axis=1)
            k_t = min(9, s.shape[1])
            tmed = np.median(s[:, -k_t:], axis=1)
        else:
            tmed = self._harm_ema

        harm = np.maximum(np.maximum(tmed, self._harm_ema), sine * mag)
        h2 = harm * harm
        p2 = perc * perc
        denom = h2 + p2 + 1e-12
        return mag * (p2 / denom), mag * (h2 / denom)

    def _tone_like(self, mag: np.ndarray) -> float:
        """0–1: current frame has a low f0 plus 2f/3f (piano stack, not a thud)."""
        freqs = self._freqs
        band = (freqs >= 70.0) & (freqs <= 250.0)
        if not np.any(band):
            return 0.0
        idx = np.where(band)[0]
        peak_i = int(idx[np.argmax(mag[idx])])
        f0 = float(freqs[peak_i])
        if f0 < 55.0:
            return 0.0
        e1 = self._bin_energy(mag, f0)
        if e1 < 1e-9:
            return 0.0
        e2 = self._bin_energy(mag, 2.0 * f0)
        e3 = self._bin_energy(mag, 3.0 * f0)
        return float(np.clip((e2 + 0.65 * e3) / (e1 + 1e-9), 0.0, 1.0))

    def _bin_energy(self, mag: np.ndarray, freq: float) -> float:
        j = int(round(freq * self.n_fft / max(self.sample_rate, 1)))
        if j <= 0 or j >= len(mag):
            return 0.0
        lo = max(0, j - 1)
        hi = min(len(mag), j + 2)
        return float(np.max(mag[lo:hi]))
