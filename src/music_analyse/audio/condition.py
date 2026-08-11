"""Signal conditioning: normalize + smooth floats; edge+refractory triggers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from music_analyse import config
from music_analyse.audio.analysis import RawFrame
from music_analyse.banks import BankParams, default_banks, ensure_four
from music_analyse.output.addresses import BANK_IDS, FLOATS, TRIGGERS
from music_analyse.tune import (
    TuneParams,
    kick_strictness_to_harmonicity_max,
    kick_strictness_to_threshold_boost,
    preset_normal,
    sensitivity_to_scale,
)


@dataclass
class ConditionedFrame:
    triggers: dict[str, bool] = field(default_factory=dict)
    floats: dict[str, float] = field(default_factory=dict)

    @staticmethod
    def empty() -> ConditionedFrame:
        floats = {
            "rms": 0.0,
            "bass_energy": 0.0,
            "vocal_presence": 0.0,
            "onset_strength": 0.0,
            "bpm": config.BPM_DEFAULT,
        }
        floats.update({k: 0.0 for k in BANK_IDS})
        return ConditionedFrame(
            triggers={k: False for k in (*TRIGGERS, *BANK_IDS)},
            floats=floats,
        )


class _FloatChannel:
    def __init__(self, window_n: int) -> None:
        self.history: deque[float] = deque(maxlen=max(8, window_n))
        self.smoothed = 0.0

    def reset(self) -> None:
        self.history.clear()
        self.smoothed = 0.0

    def resize(self, window_n: int) -> None:
        data = list(self.history)
        self.history = deque(data[-max(8, window_n) :], maxlen=max(8, window_n))


class Conditioner:
    """
    Floats: raw → gate → mix(absolute, slow level) → clamp 0..1 → attack/release EMA → makeup
    Triggers: rising-edge vs threshold + refractory (Tune-live)

    Kick is multi-gated and NOT derived from bass_energy alone.
    """

    FLOAT_KEYS = ("rms", "bass_energy", "vocal_presence", "onset_strength")

    def __init__(
        self,
        sample_rate: int = config.SAMPLE_RATE,
        block_size: int = config.BLOCK_SIZE,
        tune: TuneParams | None = None,
    ) -> None:
        self.dt = block_size / sample_rate
        self._sample_rate = sample_rate
        self._block_size = block_size
        self.tune = (tune or preset_normal()).clamped()
        window_n = max(8, int(round(config.NORM_WINDOW_S / self.dt)))
        self._channels = {k: _FloatChannel(window_n) for k in self.FLOAT_KEYS}
        for key in BANK_IDS:
            self._channels[key] = _FloatChannel(window_n)
        self._prev_trig_level = {k: 0.0 for k in (*TRIGGERS, *BANK_IDS)}
        self._last_bang_t = {k: -1e9 for k in (*TRIGGERS, *BANK_IDS)}
        self._time = 0.0
        self.banks: list[BankParams] = default_banks()

    def reset(self) -> None:
        for ch in self._channels.values():
            ch.reset()
        self._prev_trig_level = {k: 0.0 for k in (*TRIGGERS, *BANK_IDS)}
        self._last_bang_t = {k: -1e9 for k in (*TRIGGERS, *BANK_IDS)}
        self._time = 0.0

    def apply_tune(self, tune: TuneParams) -> None:
        """Live-update dynamics / trigger knobs (no restart required)."""
        self.tune = tune.clamped()
        # Slow reference window (8–12 s). Amount only blends; it does not shorten.
        window_n = max(8, int(round(config.NORM_WINDOW_S / self.dt)))
        for ch in self._channels.values():
            ch.resize(window_n)

    def apply_banks(self, banks: list[BankParams]) -> None:
        self.banks = ensure_four(banks)

    def process(self, raw: RawFrame, bank_raw: dict[str, float] | None = None) -> ConditionedFrame:
        self._time += self.dt
        floats: dict[str, float] = {}

        raw_map = {
            "rms": raw.rms,
            "bass_energy": raw.bass_energy,
            "vocal_presence": raw.vocal_presence,
            "onset_strength": raw.onset_strength,
        }
        for key, value in raw_map.items():
            floats[key] = self._condition_float(key, float(value))

        floats["bpm"] = float(raw.bpm)

        onset_e = floats["onset_strength"]
        snare_e = self._drum_level(
            raw.snare_flux,
            raw.snare_attack,
            config.SNARE_MIN_FLUX,
            config.SNARE_MIN_ATTACK,
            kick_shape=raw.kick_shape,
            kick_flux=raw.kick_flux,
            kind="snare",
            kick_from_stem=raw.kick_from_stem,
        )
        hihat_e = self._drum_level(
            raw.hihat_flux,
            raw.hihat_attack,
            config.HIHAT_MIN_FLUX,
            config.HIHAT_MIN_ATTACK,
            kick_shape=raw.kick_shape,
            kick_flux=raw.kick_flux,
            kind="hihat",
            kick_from_stem=raw.kick_from_stem,
        )
        beat_e = 1.0 if raw.beat_pulse else 0.0

        kick_score, kick_ok = self._kick_score(raw)

        levels = {
            "onset": onset_e,
            "kick": kick_score if kick_ok else 0.0,
            "snare": snare_e,
            "hihat": hihat_e,
            "beat": beat_e,
        }
        triggers: dict[str, bool] = {}
        for name in TRIGGERS:
            if name == "kick":
                triggers[name] = self._kick_bang(levels["kick"], kick_ok)
            else:
                triggers[name] = self._bang(
                    name,
                    levels[name],
                    force_pulse=(name == "beat" and raw.beat_pulse),
                )

        for k in FLOATS:
            floats.setdefault(k, 0.0 if k != "bpm" else config.BPM_DEFAULT)

        bank_raw = bank_raw or {}
        for bank in self.banks:
            key = bank.key
            active = bank.enabled and bank.valid()
            if not active:
                floats[key] = 0.0
                triggers[key] = False
                self._prev_trig_level[key] = 0.0
                continue
            cond = self._condition_float(key, float(bank_raw.get(key, 0.0)))
            floats[key] = cond
            triggers[key] = self._bank_bang(key, cond, bank.threshold)

        return ConditionedFrame(triggers=triggers, floats=floats)

    def _kick_score(self, raw: RawFrame) -> tuple[float, bool]:
        flux = float(max(0.0, min(1.0, raw.kick_flux)))
        attack = float(max(0.0, min(1.0, raw.kick_attack)))
        harm = float(max(0.0, min(1.0, raw.kick_harmonicity)))
        shape = float(max(0.0, min(1.0, raw.kick_shape)))
        beater = float(max(0.0, min(1.0, raw.kick_beater)))

        harm_max = kick_strictness_to_harmonicity_max(self.tune.kick_strictness)
        min_flux = config.KICK_MIN_FLUX * sensitivity_to_scale(self.tune.sensitivity)
        # sensitivity high → slightly easier flux gate
        min_flux = max(0.08, min_flux)

        # Stems: kick = drums-low bang. Mix-piano harmonicity must not veto.
        if getattr(raw, "kick_from_stem", False):
            gates_ok = flux >= min_flux and attack >= config.KICK_MIN_ATTACK
            score = 0.55 * flux + 0.35 * attack + config.KICK_BEATER_WEIGHT * beater
            return float(max(0.0, min(1.0, score))), gates_ok

        gates_ok = (
            flux >= min_flux
            and attack >= config.KICK_MIN_ATTACK
            and harm <= harm_max
            and shape >= config.KICK_MIN_SHAPE
        )
        unpitched = 1.0 - harm
        score = (
            0.34 * flux
            + 0.26 * attack
            + 0.22 * unpitched
            + 0.18 * shape
            + config.KICK_BEATER_WEIGHT * beater
        )
        return float(max(0.0, min(1.0, score))), gates_ok

    def _kick_bang(self, score: float, gates_ok: bool) -> bool:
        scale = sensitivity_to_scale(self.tune.sensitivity)
        thr = (config.KICK_THRESHOLD * scale) + kick_strictness_to_threshold_boost(
            self.tune.kick_strictness
        )
        thr = max(0.25, min(0.95, thr))
        # Kick uses max(global hold, kick refractory) so Hold slider matters
        refr = max(self.tune.hold_ms, config.KICK_REFRACTORY_MS) / 1000.0
        level = score if gates_ok else 0.0
        prev = self._prev_trig_level["kick"]
        rising = gates_ok and (prev < thr) and (level >= thr)
        self._prev_trig_level["kick"] = level
        if not rising:
            return False
        if self._time - self._last_bang_t["kick"] < refr:
            return False
        self._last_bang_t["kick"] = self._time
        return True

    def _condition_float(self, key: str, raw: float) -> float:
        t = self.tune
        ch = self._channels[key]
        x = max(0.0, raw - t.threshold)
        ch.history.append(x)
        if not ch.history:
            ref = 0.0
        elif len(ch.history) < 8:
            ref = max(ch.history)
        else:
            ref = float(
                np.percentile(
                    np.asarray(ch.history, dtype=np.float64), config.NORM_PERCENTILE
                )
            )
        adaptive = max(0.0, min(1.0, x / (ref + config.NORM_EPSILON)))
        # Amount 0 = absolute unit dynamics; 1 = slow 80th-percentile level
        soft = max(0.0, min(1.0, x))
        norm = (1.0 - t.amount) * soft + t.amount * adaptive

        if norm >= ch.smoothed:
            tau = max(t.attack_s, 1e-4)
        else:
            tau = max(t.release_s, 1e-4)
        alpha = 1.0 - pow(2.718281828, -self.dt / tau)
        ch.smoothed = ch.smoothed + alpha * (norm - ch.smoothed)
        out = ch.smoothed * t.makeup
        return float(max(0.0, min(1.0, out)))

    @staticmethod
    def _flux_norm(flux: float) -> float:
        return float(max(0.0, min(1.0, flux)))

    def _drum_level(
        self,
        flux: float,
        attack: float,
        min_flux: float,
        min_attack: float,
        kick_shape: float,
        kick_flux: float,
        kind: str,
        kick_from_stem: bool = False,
    ) -> float:
        """Own-band snare/hat level — no global onset mix (brief G)."""
        flux = self._flux_norm(flux)
        attack = self._flux_norm(attack)
        if flux < min_flux or attack < min_attack:
            return 0.0
        # Kick-only loops: thud/click must not lift snare/hat to threshold
        # (skip when Stems: kick_shape is forced 1.0 and is not mix-piano).
        if not kick_from_stem:
            if kind == "snare" and kick_shape >= 0.58:
                return 0.0
            if kind == "hihat" and (kick_shape >= 0.65 or flux < kick_flux * 1.25):
                return 0.0
        return float(min(1.0, 0.62 * flux + 0.38 * attack))

    def _bang(self, name: str, level: float, force_pulse: bool = False) -> bool:
        scale = sensitivity_to_scale(self.tune.sensitivity)
        base = config.TRIGGER_THRESHOLDS.get(name, config.TRIGGER_THRESHOLD)
        thr = max(0.15, min(0.95, base * scale))
        refr = self.tune.hold_ms / 1000.0
        prev = self._prev_trig_level[name]
        rising = (prev < thr) and (level >= thr)
        if force_pulse:
            rising = True
        self._prev_trig_level[name] = level
        if not rising:
            return False
        if self._time - self._last_bang_t[name] < refr:
            return False
        self._last_bang_t[name] = self._time
        return True

    def _bank_bang(self, name: str, level: float, threshold: float) -> bool:
        """Honest threshold + Hold only — no kick multi-gate / sensitivity scale."""
        thr = float(max(0.05, min(0.95, threshold)))
        refr = self.tune.hold_ms / 1000.0
        prev = self._prev_trig_level.get(name, 0.0)
        rising = (prev < thr) and (level >= thr)
        self._prev_trig_level[name] = level
        if not rising:
            return False
        if self._time - self._last_bang_t.get(name, -1e9) < refr:
            return False
        self._last_bang_t[name] = self._time
        return True
