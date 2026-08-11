"""User tap-tempo clock — source of truth for BPM + beat phase once locked."""

from __future__ import annotations

import math
import statistics
import time

from music_analyse import config


class TempoClock:
    """
    Tap: BPM = 60 / median(last 3–8 valid intervals).
    One tap keeps BPM and resets phase. Two+ taps update BPM.
    Gap > TAP_TIMEOUT_S starts a new interval sequence (phase still from latest tap).
    """

    def __init__(self, bpm: float = config.BPM_DEFAULT) -> None:
        self.bpm = float(bpm)
        self.locked = False
        self._taps: list[float] = []
        self._phase_t0: float | None = None
        self._last_poll: float | None = None
        self._pending_beat = False

    def tap(self, now: float | None = None) -> float:
        now = time.monotonic() if now is None else float(now)
        if self._taps and (now - self._taps[-1]) > config.TAP_TIMEOUT_S:
            self._taps = []
        self._taps.append(now)
        self._phase_t0 = now
        self.locked = True
        self._pending_beat = True
        self._last_poll = now

        if len(self._taps) >= 2:
            intervals = [
                self._taps[i] - self._taps[i - 1] for i in range(1, len(self._taps))
            ]
            lo = 60.0 / config.TAP_BPM_HI
            hi = 60.0 / config.TAP_BPM_LO
            valid = [iv for iv in intervals if lo <= iv <= hi]
            valid = valid[-config.TAP_MAX_INTERVALS :]
            if valid:
                med = statistics.median(valid)
                if med > 1e-9:
                    self.bpm = float(
                        max(config.TAP_BPM_LO, min(config.TAP_BPM_HI, 60.0 / med))
                    )
        if len(self._taps) > config.TAP_MAX_INTERVALS + 1:
            self._taps = self._taps[-(config.TAP_MAX_INTERVALS + 1) :]
        return self.bpm

    def set_bpm(self, bpm: float) -> float:
        """Nudge BPM by UI −/+. Keeps current phase (grid does not jump)."""
        self.bpm = float(max(config.TAP_BPM_LO, min(config.TAP_BPM_HI, bpm)))
        self.locked = True
        return self.bpm

    def restore(self, bpm: float, locked: bool) -> None:
        """Restore BPM (+ optional lock). Beat phase starts fresh — no re-tap required."""
        self.bpm = float(max(config.TAP_BPM_LO, min(config.TAP_BPM_HI, bpm)))
        self.locked = bool(locked)
        self._taps = []
        self._phase_t0 = None
        self._last_poll = None
        self._pending_beat = False

    def clear(self) -> None:
        """Unlock — auto BPM may write again. Last BPM stays as fallback."""
        self.locked = False
        self._taps = []
        self._phase_t0 = None
        self._last_poll = None
        self._pending_beat = False

    def follow_auto(self, bpm: float) -> None:
        if self.locked:
            return
        if bpm > 0 and bpm == bpm:
            self.bpm = float(bpm)

    def poll(self, now: float | None = None) -> bool:
        """True if a grid beat falls in (last_poll, now], or a tap just landed."""
        now = time.monotonic() if now is None else float(now)
        if self._pending_beat:
            self._pending_beat = False
            self._last_poll = now
            return True
        if self._phase_t0 is None:
            self._last_poll = now
            return False
        if self._last_poll is None:
            self._last_poll = now
            return False
        period = 60.0 / max(self.bpm, 1.0)
        t0 = self._phase_t0
        prev = self._last_poll
        self._last_poll = now
        # Beat times t0 + i*period that fall in (prev, now]
        i0 = 0 if prev < t0 else math.floor((prev - t0) / period) + 1
        i1 = math.floor((now - t0) / period)
        return i1 >= i0 >= 0
