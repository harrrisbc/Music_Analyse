"""Heuristic streaming analysis → raw features (pre-conditioner)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.fft import rfft, rfftfreq

from music_analyse import config


@dataclass
class RawFrame:
    """Unconditioned features for one audio block."""

    rms: float = 0.0
    bass_energy: float = 0.0
    vocal_presence: float = 0.0
    onset_strength: float = 0.0  # spectral flux (pre-norm)
    bpm: float = config.BPM_DEFAULT
    kick_flux: float = 0.0
    snare_flux: float = 0.0
    hihat_flux: float = 0.0
    beat_pulse: bool = False
    # Kick multi-gate features (see Conditioner._kick_bang)
    kick_attack: float = 0.0  # fast envelope rise 0–1
    kick_harmonicity: float = 0.0  # pitchedness 0–1 (high → piano-like)
    kick_shape: float = 0.0  # sub vs mid-harmonic dominance 0–1
    kick_beater: float = 0.0  # optional 2–6 kHz energy bonus 0–1

    @staticmethod
    def empty() -> RawFrame:
        return RawFrame()


class Analyser:
    """Block-based heuristic feature extractor (energy bands + onset + beat phase)."""

    def __init__(
        self,
        sample_rate: int = config.SAMPLE_RATE,
        block_size: int = config.BLOCK_SIZE,
    ) -> None:
        self.sample_rate = sample_rate
        self.block_size = block_size
        self._prev_mag: np.ndarray | None = None
        self._prev_band = {"kick": 0.0, "snare": 0.0, "hihat": 0.0, "full": 0.0, "beater": 0.0}
        self._env_fast = 0.0
        self._env_slow = 0.0
        self._ioi: list[float] = []
        self._last_onset_time = -1.0
        self._time = 0.0
        self._bpm = config.BPM_DEFAULT
        self._beat_phase = 0.0
        self._last_beat_time = -1.0
        self._freqs = rfftfreq(block_size, d=1.0 / sample_rate)
        self._last_mag: np.ndarray | None = None

    def reset(self) -> None:
        self._prev_mag = None
        self._last_mag = None
        self._prev_band = {"kick": 0.0, "snare": 0.0, "hihat": 0.0, "full": 0.0, "beater": 0.0}
        self._env_fast = 0.0
        self._env_slow = 0.0
        self._ioi.clear()
        self._last_onset_time = -1.0
        self._time = 0.0
        self._bpm = config.BPM_DEFAULT
        self._beat_phase = 0.0
        self._last_beat_time = -1.0

    def process(self, block: np.ndarray) -> RawFrame:
        x = np.asarray(block, dtype=np.float32).reshape(-1)
        if len(x) < self.block_size:
            pad = np.zeros(self.block_size - len(x), dtype=np.float32)
            x = np.concatenate([x, pad])
        elif len(x) > self.block_size:
            x = x[: self.block_size]

        dt = self.block_size / self.sample_rate
        self._time += dt

        window = np.hanning(self.block_size).astype(np.float32)
        spectrum = rfft(x * window)
        mag = np.abs(spectrum).astype(np.float64)

        rms = float(np.sqrt(np.mean(x * x) + 1e-12))
        bass = self._band_energy(mag, *config.BASS_BAND)
        vocal = self._band_energy(mag, *config.VOCAL_BAND)
        kick_e = self._band_energy(mag, *config.KICK_BAND)
        snare_e = self._band_energy(mag, *config.SNARE_BAND)
        hihat_e = self._band_energy(mag, *config.HIHAT_BAND)
        mid_h = self._band_energy(mag, *config.KICK_SHAPE_MID_BAND)
        beater_e = self._band_energy(mag, *config.KICK_BEATER_BAND)
        full_e = float(np.mean(mag) + 1e-12)

        if self._prev_mag is None:
            flux = 0.0
        else:
            diff = mag - self._prev_mag
            flux = float(np.mean(np.maximum(diff, 0.0)))
        self._prev_mag = mag
        self._last_mag = mag

        kick_flux = max(0.0, kick_e - self._prev_band["kick"]) / (
            kick_e + self._prev_band["kick"] + 1e-9
        )
        snare_flux = max(0.0, snare_e - self._prev_band["snare"]) / (
            snare_e + self._prev_band["snare"] + 1e-9
        )
        hihat_flux = max(0.0, hihat_e - self._prev_band["hihat"]) / (
            hihat_e + self._prev_band["hihat"] + 1e-9
        )
        beater_flux = max(0.0, beater_e - self._prev_band["beater"]) / (
            beater_e + self._prev_band["beater"] + 1e-9
        )
        self._prev_band = {
            "kick": kick_e,
            "snare": snare_e,
            "hihat": hihat_e,
            "full": full_e,
            "beater": beater_e,
        }

        # Fast attack: fast envelope ahead of slow envelope (kick thud, not pad swell)
        kick_attack = self._attack_score(rms)

        # Harmonicity / pitch salience — high on piano, lower on kick thud
        kick_harmonicity = self._harmonicity(x, mag)

        # Shape: prefer sub/low thud energy vs clear mid-harmonic banding
        # kick_shape ≈ 1 when sub dominates mid harmonics (drum-like)
        kick_shape = float(kick_e / (kick_e + mid_h + 1e-9))

        kick_beater = float(min(1.0, beater_flux))

        onset_hint = flux > 1e-6

        if onset_hint:
            if self._last_onset_time >= 0:
                ioi = self._time - self._last_onset_time
                if 60.0 / config.BPM_MAX <= ioi <= 60.0 / config.BPM_MIN:
                    self._ioi.append(ioi)
                    if len(self._ioi) > 24:
                        self._ioi.pop(0)
                    med = float(np.median(self._ioi))
                    self._bpm = float(
                        np.clip(60.0 / med, config.BPM_MIN, config.BPM_MAX)
                    )
            self._last_onset_time = self._time

        beat_period = 60.0 / max(self._bpm, 1.0)
        self._beat_phase += dt / beat_period
        beat_pulse = False
        if self._beat_phase >= 1.0:
            self._beat_phase -= 1.0
            if self._time - self._last_beat_time > beat_period * 0.5:
                beat_pulse = True
                self._last_beat_time = self._time
        if onset_hint and flux > 0.0:
            phase_err = min(self._beat_phase, 1.0 - self._beat_phase)
            if phase_err < config.BEAT_PHASE_TOLERANCE and not beat_pulse:
                if self._time - self._last_beat_time > beat_period * 0.45:
                    beat_pulse = True
                    self._beat_phase = 0.0
                    self._last_beat_time = self._time

        return RawFrame(
            rms=rms,
            bass_energy=bass,
            vocal_presence=vocal,
            onset_strength=flux,
            bpm=float(self._bpm),
            kick_flux=float(kick_flux),
            snare_flux=float(snare_flux),
            hihat_flux=float(hihat_flux),
            beat_pulse=beat_pulse,
            kick_attack=float(kick_attack),
            kick_harmonicity=float(kick_harmonicity),
            kick_shape=float(kick_shape),
            kick_beater=float(kick_beater),
        )

    def _attack_score(self, rms: float) -> float:
        # Dual EMA: large fast−slow gap ⇒ sharp attack
        a_fast = 1.0 - pow(2.718281828, -(self.block_size / self.sample_rate) / 0.008)
        a_slow = 1.0 - pow(2.718281828, -(self.block_size / self.sample_rate) / 0.080)
        self._env_fast = self._env_fast + a_fast * (rms - self._env_fast)
        self._env_slow = self._env_slow + a_slow * (rms - self._env_slow)
        gap = max(0.0, self._env_fast - self._env_slow)
        return float(min(1.0, gap / (self._env_slow + 1e-4) * 2.0))

    def _harmonicity(self, x: np.ndarray, mag: np.ndarray) -> float:
        """
        Lightweight pitchedness score in low–mid range.
        Mix of (1) spectral peakiness 100–1500 Hz and (2) autocorrelation clarity
        for periods ~80–400 Hz. High → sustained piano-like pitch; low → thud/noise.
        """
        # Spectral peakiness
        mask = (self._freqs >= 100.0) & (self._freqs <= 1500.0)
        if np.any(mask):
            band = mag[mask]
            peakiness = float(np.max(band) / (np.mean(band) + 1e-12))
            peak_score = float(min(1.0, max(0.0, (peakiness - 2.0) / 8.0)))
        else:
            peak_score = 0.0

        # Autocorrelation clarity (lag range for 80–400 Hz)
        n = len(x)
        min_lag = max(1, int(self.sample_rate / 400.0))
        max_lag = min(n - 1, int(self.sample_rate / 80.0))
        if max_lag <= min_lag + 2:
            ac_score = 0.0
        else:
            # Normalize and compute biased autocorr at lags
            y = x - float(np.mean(x))
            denom = float(np.dot(y, y) + 1e-12)
            best = 0.0
            for lag in range(min_lag, max_lag + 1, 2):
                corr = float(np.dot(y[lag:], y[:-lag]) / denom)
                if corr > best:
                    best = corr
            ac_score = float(min(1.0, max(0.0, best)))

        return float(min(1.0, 0.55 * peak_score + 0.45 * ac_score))

    def band_energy_hz(self, lo_hz: float, hi_hz: float) -> float:
        """Mean magnitude in [lo, hi) from the last analysed block (no extra FFT)."""
        if self._last_mag is None or hi_hz <= lo_hz:
            return 0.0
        return self._band_energy(self._last_mag, lo_hz, hi_hz)

    def _band_energy(self, mag: np.ndarray, lo_hz: float, hi_hz: float) -> float:
        mask = (self._freqs >= lo_hz) & (self._freqs < hi_hz)
        if not np.any(mask):
            return 0.0
        return float(np.mean(mag[mask]))
