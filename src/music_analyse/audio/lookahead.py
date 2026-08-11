"""Pro-mode trigger look-ahead: confirm local peak + decay before committing a bang."""

from __future__ import annotations

from collections import deque

from music_analyse.output.addresses import BANK_IDS, TRIGGERS


class TriggerLookahead:
    """
    Delay trigger bangs by `lookahead_ms` and emit only if the candidate
    stays a local peak and (for drum-like ids) decays — rejects piano sustains.
    Floats are not delayed.
    """

    DRUM_LIKE = frozenset({"kick", "snare", "hihat", "onset", *BANK_IDS})

    def __init__(self, hop_s: float, lookahead_ms: float = 120.0) -> None:
        self.hop_s = hop_s
        self._delay_n = 1
        self._hist: dict[str, deque[float]] = {}
        self._pending: dict[str, list[tuple[int, float]]] = {}
        self.set_lookahead_ms(lookahead_ms)
        self.reset()

    def set_lookahead_ms(self, lookahead_ms: float) -> None:
        ms = float(max(60.0, min(200.0, lookahead_ms)))
        self._delay_n = max(2, int(round((ms / 1000.0) / max(self.hop_s, 1e-4))))
        # Keep pending; ages still work. Trim history maxlen.
        for name in (*TRIGGERS, *BANK_IDS):
            old = list(self._hist.get(name, ()))
            self._hist[name] = deque(old[-self._delay_n - 6 :], maxlen=self._delay_n + 6)

    @property
    def delay_frames(self) -> int:
        return self._delay_n

    def reset(self) -> None:
        self._hist = {
            name: deque(maxlen=self._delay_n + 6) for name in (*TRIGGERS, *BANK_IDS)
        }
        self._pending = {name: [] for name in (*TRIGGERS, *BANK_IDS)}

    def process(
        self,
        triggers: dict[str, bool],
        floats: dict[str, float],
        raw: object | None = None,
        bank_raw: dict[str, float] | None = None,
    ) -> dict[str, bool]:
        out = {name: False for name in (*TRIGGERS, *BANK_IDS)}
        for name in (*TRIGGERS, *BANK_IDS):
            strength = self._strength(name, triggers, floats, raw, bank_raw)
            self._hist[name].append(strength)
            if triggers.get(name):
                self._pending[name].append((0, strength))

            still: list[tuple[int, float]] = []
            for age, cand in self._pending[name]:
                if age >= self._delay_n:
                    hist = list(self._hist[name])
                    future = hist[-self._delay_n :] if len(hist) > self._delay_n else hist[1:]
                    later = max(future) if future else 0.0
                    # Long analysis windows rise over several hops — nudge wait, don't restart
                    if later > cand * 1.08:
                        still.append((max(0, self._delay_n - 2), later))
                        continue
                    if self._confirm(name, cand):
                        out[name] = True
                    continue
                still.append((age + 1, cand))
            self._pending[name] = still
        return out

    def _strength(
        self,
        name: str,
        triggers: dict[str, bool],
        floats: dict[str, float],
        raw: object | None,
        bank_raw: dict[str, float] | None = None,
    ) -> float:
        # Prefer raw transients — conditioned floats have ~250 ms release
        # and look like sustain to a 60–200 ms look-ahead.
        if name == "kick":
            if raw is not None:
                return float(getattr(raw, "kick_flux", 0.0))
            return float(floats.get("onset_strength", 0.0))
        if name == "snare":
            if raw is not None:
                return float(getattr(raw, "snare_flux", 0.0))
            return float(floats.get("onset_strength", 0.0))
        if name == "hihat":
            if raw is not None:
                return float(getattr(raw, "hihat_flux", 0.0))
            return float(floats.get("onset_strength", 0.0))
        if name == "onset":
            if raw is not None:
                return float(getattr(raw, "onset_strength", 0.0))
            return float(floats.get("onset_strength", 0.0))
        if name == "beat":
            return 1.0 if triggers.get("beat") else 0.0
        if name in BANK_IDS:
            if bank_raw is not None:
                return float(bank_raw.get(name, 0.0))
            return float(floats.get(name, 0.0))
        return float(floats.get("onset_strength", 0.0))

    def _confirm(self, name: str, cand: float) -> bool:
        hist = list(self._hist[name])
        if not hist or cand <= 1e-9:
            return False
        # Samples after the candidate (hist oldest→newest; candidate is delay_n hops ago)
        future = hist[-self._delay_n :] if len(hist) > self._delay_n else hist[1:]
        if future and max(future) > cand * 1.08:
            return False
        if name in self.DRUM_LIKE and future:
            tail = future[-max(2, len(future) // 3) :]
            if (sum(tail) / len(tail)) > cand * 0.92:
                return False
            if name in BANK_IDS:
                # True hit rises from quiet — reject pads already sitting in-band
                pre_end = len(hist) - self._delay_n
                pre = hist[max(0, pre_end - 3) : pre_end]
                if pre and (sum(pre) / len(pre)) > cand * 0.75:
                    return False
        return True
