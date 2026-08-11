"""User frequency banks — extra Hz + threshold instruments (not factory kick)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from music_analyse.output.addresses import BANK_IDS

HZ_MIN = 20.0
HZ_MAX = 10_000.0
THR_MIN = 0.05
THR_MAX = 0.95


@dataclass
class BankParams:
    index: int  # 1..4
    enabled: bool = True
    name: str = "Bank"
    lo_hz: float = 40.0
    hi_hz: float = 120.0
    threshold: float = 0.55

    @property
    def key(self) -> str:
        return f"bank{self.index}"

    def valid(self) -> bool:
        return self.hi_hz > self.lo_hz

    def to_dict(self) -> dict:
        b = self.clamped()
        return {
            "index": b.index,
            "enabled": b.enabled,
            "name": b.name,
            "lo_hz": b.lo_hz,
            "hi_hz": b.hi_hz,
            "threshold": b.threshold,
        }

    @classmethod
    def from_dict(cls, data: object) -> BankParams | None:
        if not isinstance(data, dict):
            return None
        try:
            index = int(data.get("index", 0))
        except (TypeError, ValueError):
            return None
        if index < 1 or index > 4:
            return None

        def _float(key: str, fallback: float) -> float:
            try:
                return float(data.get(key, fallback))
            except (TypeError, ValueError):
                return fallback

        return BankParams(
            index=index,
            enabled=bool(data.get("enabled", True)),
            name=str(data.get("name") or f"Bank {index}"),
            lo_hz=_float("lo_hz", 40.0),
            hi_hz=_float("hi_hz", 120.0),
            threshold=_float("threshold", 0.55),
        ).clamped()

    def clamped(self) -> BankParams:
        lo = float(max(HZ_MIN, min(HZ_MAX, self.lo_hz)))
        hi = float(max(HZ_MIN, min(HZ_MAX, self.hi_hz)))
        if hi <= lo:
            hi = min(HZ_MAX, lo + 10.0)
        return BankParams(
            index=int(max(1, min(4, self.index))),
            enabled=bool(self.enabled),
            name=(self.name or f"Bank {self.index}").strip() or f"Bank {self.index}",
            lo_hz=lo,
            hi_hz=hi,
            threshold=float(max(THR_MIN, min(THR_MAX, self.threshold))),
        )


def default_banks() -> list[BankParams]:
    """Shipped defaults: banks 1–3 on, 4 off."""
    return [
        BankParams(1, True, "Bank 1", 40.0, 120.0, 0.55),
        BankParams(2, True, "Bank 2", 150.0, 800.0, 0.50),
        BankParams(3, True, "Bank 3", 2000.0, 6000.0, 0.45),
        BankParams(4, False, "Bank 4", 300.0, 3400.0, 0.50),
    ]


def preset_kick_ish() -> list[BankParams]:
    return [
        BankParams(1, True, "Bank 1", 40.0, 100.0, 0.58),
        BankParams(2, True, "Bank 2", 80.0, 160.0, 0.55),
        BankParams(3, True, "Bank 3", 2000.0, 6000.0, 0.50),
        BankParams(4, False, "Bank 4", 300.0, 3400.0, 0.50),
    ]


def preset_snare_ish() -> list[BankParams]:
    return [
        BankParams(1, True, "Bank 1", 150.0, 400.0, 0.50),
        BankParams(2, True, "Bank 2", 1000.0, 4000.0, 0.48),
        BankParams(3, True, "Bank 3", 6000.0, 10000.0, 0.45),
        BankParams(4, False, "Bank 4", 300.0, 3400.0, 0.50),
    ]


def preset_hat_ish() -> list[BankParams]:
    return [
        BankParams(1, True, "Bank 1", 5000.0, 8000.0, 0.42),
        BankParams(2, True, "Bank 2", 8000.0, 10000.0, 0.40),
        BankParams(3, True, "Bank 3", 2000.0, 5000.0, 0.48),
        BankParams(4, False, "Bank 4", 300.0, 3400.0, 0.50),
    ]


BANK_PRESETS: dict[str, list[BankParams]] = {
    "Kick-ish": preset_kick_ish(),
    "Snare-ish": preset_snare_ish(),
    "Hat-ish": preset_hat_ish(),
    "Reset": default_banks(),
}


def hz_to_pos(hz: float) -> float:
    """Map 20–10000 Hz → 0–1 log scale."""
    hz = max(HZ_MIN, min(HZ_MAX, float(hz)))
    return math.log(hz / HZ_MIN) / math.log(HZ_MAX / HZ_MIN)


def pos_to_hz(pos: float) -> float:
    """Map 0–1 log scale → 20–10000 Hz."""
    pos = max(0.0, min(1.0, float(pos)))
    return float(HZ_MIN * ((HZ_MAX / HZ_MIN) ** pos))


def ensure_four(banks: list[BankParams]) -> list[BankParams]:
    by_i = {b.index: b.clamped() for b in banks}
    out: list[BankParams] = []
    for i, default in enumerate(default_banks(), start=1):
        out.append(by_i.get(i, default).clamped())
    assert len(out) == len(BANK_IDS)
    return out
