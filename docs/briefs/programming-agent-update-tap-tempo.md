---
status: Implemented
type: update
from: Designer agent
to: Programming agent
parent: docs/briefs/programming-agent-full.md
date: 2026-08-11
---

# Update — Tap-tempo BPM (user click)

**Why:** Auto BPM (IOI / librosa) is unstable. For TD, a **user-tapped tempo** is more accurate than guessing. Delay of other signals stays as-is.

**Change:** BPM is primarily set by the user clicking a **Tap** button. The `beat` trigger follows that tempo and the last tap’s phase.

---

## 1. Goal

Let the user set BPM by clicking (tap tempo). `/ma/float/bpm` and `/ma/trigger/beat` use the tapped value, not a drifting auto estimate.

---

## 2. Screens / surfaces

**In scope**
- Transport area: **Tap** button + large BPM readout
- Optional small **− / +** (1 BPM) next to the number
- Optional **Clear** / return-to-auto (not required if Tap-only is simpler)

**Out of scope**
- Tap pad as a separate window
- MIDI clock in
- Changing OSC addresses

---

## 3. Layout & hierarchy

```
2. Transport
   Start | Stop | Mute
   Mode: Live | Pro …
   Tempo:  [ TAP ]   128.0 BPM   [ − ] [ + ]
```

- **TAP** is the primary control (accent when recently tapped)
- BPM number: monospace, always readable (light on dark — same contrast fix as bank values)
- Place on its own row under Start/Stop so it is easy to hit while running

---

## 4. Visual tokens

Unchanged dark utility. TAP uses Accent after a hit (~100 ms flash), then returns to normal. BPM text: `#e8e8e8` or accent chip like bank readouts.

---

## 5. Behavior

### Tap tempo

- Each click of **TAP** records `time.monotonic()`
- BPM = `60 / median(last N intervals)` where N = last **3–8** intervals
- Ignore intervals outside ~BPM 40–240 (or clamp to `BPM_MIN`/`BPM_MAX` after computing)
- If only **one** tap so far: keep previous BPM, but **reset beat phase** to that tap (so the next `beat` lands on the user’s click)
- After **two** valid taps: update BPM immediately
- Time out: if no tap for **> 2.5 s**, start a **new** tap sequence (don’t average an old interval with a new song section). Phase from the latest tap still applies.

### Beat clock (once BPM is user-set)

- `beat` fires on a **free-running grid**: period = `60 / bpm`, phase locked to the **most recent tap**
- Do **not** re-nudge the grid from audio flux while in tap mode
- Hold / refractory still apply so you don’t double-fire

### Auto BPM

- **Before any tap this session:** keep current auto BPM as a fallback (so `/ma/float/bpm` isn’t empty)
- **After the first tap:** lock to tap mode until Stop, or until user hits Clear if you add it
- Live and Pro both honor tap lock the same way (don’t let Pro `beat_track` overwrite a tapped BPM)

### Engine API (suggested)

```text
engine.tap_tempo()           # call from UI button
engine.set_bpm(float)        # for − / +
engine.clear_tap_tempo()     # optional
snapshot() includes bpm, tap_locked: bool
```

Analyser `raw.bpm` / `beat_pulse` should read the engine (or a shared TempoClock) when tap-locked, instead of writing their own.

### OSC / MIDI

- `/ma/float/bpm` = tapped (or fallback auto) BPM — still every frame
- `/ma/trigger/beat` = grid bangs, 0/1 every frame as already specified
- MIDI CC 24 still scaled 60–180 → 0–127

Keyboard: binding **Space** to TAP while the window is focused is nice-to-have (don’t steal Space from text fields).

---

## 6. Acceptance criteria

- [ ] TAP button visible in Transport; readable BPM number
- [ ] Two+ taps set BPM; readout updates
- [ ] Last tap sets beat phase; `beat` OSC follows that grid
- [ ] After tap lock, auto/librosa BPM does not overwrite
- [ ] − / + change BPM by 1 and keep phase (or reset phase — pick one, document)
- [ ] Live latency of other signals unchanged
- [ ] OSC addresses unchanged
- [ ] README: how to tap, what lock means
- [ ] Append **Implemented** on this file

---

## 7. Do / Don't

**Do**
- Treat user click as source of truth for tempo + phase
- Keep TAP easy to hit while audio is running

**Don't**
- Don’t require typing a BPM as the only method
- Don’t keep blending auto IOI into the value after the user has tapped
- Don’t add delay to kick/onset/floats

---

## Done means

User taps along with the track a few times, BPM readout settles, and TouchDesigner `/ma/trigger/beat` stays on that grid.

---

## Implemented (Programming agent — fill in)

- Transport row: **TAP** + accent BPM chip + **− / +**. Space taps unless focus is an entry/combobox (or the TAP button itself).
- `TempoClock` (`tempo.py`): median of last 3–8 intervals (40–240 BPM); 2.5 s gap resets the sequence; one tap = keep BPM + reset phase; two+ taps update BPM.
- After first tap: `tap_locked` until **Stop**. Auto IOI / Pro `beat_track` cannot overwrite. `beat` is a free-running grid from the last tap (Pro look-ahead does **not** delay tap beats).
- `− / +` = ±1 BPM, **phase kept**. `engine.tap_tempo()` / `set_bpm()` / `clear_tap_tempo()`; snapshot has `bpm`, `tap_locked`.
- Start / mode restart does not clear lock. OSC addresses unchanged.
