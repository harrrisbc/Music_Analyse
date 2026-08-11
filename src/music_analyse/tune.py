"""Live-tunable dynamics / trigger params + built-in presets."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from music_analyse import config


@dataclass
class TuneParams:
    """UI-facing Tune knobs (compressor-like floats + trigger feel)."""

    # Floats dynamics
    threshold: float = config.NOISE_FLOOR  # 0–0.1 noise floor / gate
    amount: float = 1.0  # 0–1 adaptive-norm strength
    attack_s: float = config.ATTACK_S  # 0.005–0.1
    release_s: float = config.RELEASE_S  # 0.05–1.0
    makeup: float = 1.0  # 0.5–2.0 post gain then clamp

    # Triggers
    sensitivity: float = 0.5  # 0–1; higher → lower thresholds / more bangs
    hold_ms: float = config.REFRACTORY_MS  # refractory / min interval
    kick_strictness: float = 0.5  # 0–1; higher → tighter piano rejection

    def clamped(self) -> TuneParams:
        return TuneParams(
            threshold=float(max(0.0, min(0.1, self.threshold))),
            amount=float(max(0.0, min(1.0, self.amount))),
            attack_s=float(max(0.005, min(0.1, self.attack_s))),
            release_s=float(max(0.05, min(1.0, self.release_s))),
            makeup=float(max(0.5, min(2.0, self.makeup))),
            sensitivity=float(max(0.0, min(1.0, self.sensitivity))),
            hold_ms=float(max(20.0, min(300.0, self.hold_ms))),
            kick_strictness=float(max(0.0, min(1.0, self.kick_strictness))),
        )

    def to_dict(self) -> dict:
        return asdict(self.clamped())


def preset_normal() -> TuneParams:
    """Match shipped conditioner / kick defaults."""
    return TuneParams(
        threshold=config.NOISE_FLOOR,
        amount=1.0,
        attack_s=config.ATTACK_S,
        release_s=config.RELEASE_S,
        makeup=1.0,
        sensitivity=0.5,
        hold_ms=config.REFRACTORY_MS,
        kick_strictness=0.55,  # ≈ KICK_HARMONICITY_MAX 0.45
    )


def preset_gentle() -> TuneParams:
    return TuneParams(
        threshold=0.03,
        amount=0.65,
        attack_s=0.06,
        release_s=0.45,
        makeup=0.95,
        sensitivity=0.30,
        hold_ms=120.0,
        kick_strictness=0.55,
    )


def preset_tight() -> TuneParams:
    return TuneParams(
        threshold=0.005,
        amount=1.0,
        attack_s=0.012,
        release_s=0.10,
        makeup=1.1,
        sensitivity=0.75,
        hold_ms=50.0,
        kick_strictness=0.45,
    )


def preset_kick_safe() -> TuneParams:
    """Normal-ish floats + high kick strictness + slightly fewer kicks."""
    return replace(
        preset_gentle(),
        threshold=0.02,
        amount=0.9,
        attack_s=0.035,
        release_s=0.28,
        makeup=1.0,
        sensitivity=0.40,
        hold_ms=100.0,
        kick_strictness=0.90,
    )


PRESETS: dict[str, TuneParams] = {
    "Gentle": preset_gentle(),
    "Normal": preset_normal(),
    "Tight": preset_tight(),
    "Kick safe": preset_kick_safe(),
}


def sensitivity_to_scale(sensitivity: float) -> float:
    """Higher sensitivity → lower trigger thresholds (scale < 1)."""
    # sens 0 → 1.35× thr (fewer), sens 0.5 → 1.0×, sens 1 → 0.65×
    s = max(0.0, min(1.0, sensitivity))
    return float(1.35 - 0.70 * s)


def kick_strictness_to_harmonicity_max(strictness: float) -> float:
    """Higher strictness → lower harmonicity ceiling (reject piano harder)."""
    s = max(0.0, min(1.0, strictness))
    # lenient 0.70 → strict 0.22
    return float(0.70 - 0.48 * s)


def kick_strictness_to_threshold_boost(strictness: float) -> float:
    """Slightly raise kick score threshold when strict."""
    s = max(0.0, min(1.0, strictness))
    return float(0.0 + 0.12 * s)
