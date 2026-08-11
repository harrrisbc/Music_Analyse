---
status: Approved
type: update
from: Designer agent
to: Programming agent
parent: docs/briefs/programming-agent-full.md
date: 2026-08-11
---

# Update — Short-time scope (heartbeat graph)

**Why:** Bar meters hide phrasing. Vocal (and a few other floats) need a short scrolling graph so the user can see whether the signal actually follows the music.

Implement now. User is AFK; do not wait for more design questions unless blocked.

---

## 1. Goal

Add one compact **heartbeat / ECG-style scope** under Monitor: last ~**3 seconds** of a chosen conditioned float (default **`vocal_presence`**).

---

## 2. Screens / surfaces

**In scope**
- Native UI: one scope strip in Monitor
- Channel picker (which float to plot)
- Window length ~3s (optional slider 2–4s; fixed 3s OK if faster)
- Optional threshold hairline
- Trigger ticks under the same plot (not separate graphs)

**Out of scope**
- One graph per signal
- Fancy chart libraries, spectrograms, TD-side plots
- Graphing `bpm` as a waveform

---

## 3. Layout & hierarchy

```
4. Monitor
   trigger flashes …
   float meters …
   Scope  [ vocal_presence ▾ ]   (optional: Window 3.0s)
   ┌─────────────────────────────────────────┐
   │  ~3s scrolling polyline (left = old)    │  ← ~80–100px tall
   │  ·  ·     ·      trigger ticks          │
   └─────────────────────────────────────────┘
5. Tune …
6. Banks …
```

Keep the strip short. Window must stay **scrollable**.

---

## 4. Visual tokens

- Plot bg: `#1a1a1a`
- Trace: accent `#2ee6a6`, 1–2px
- Threshold line (if shown): muted `#888888` dashed
- Trigger ticks: small accent marks on the baseline
- No grid chrome beyond a faint midline optional

---

## 5. Components

### Signal

- Plot **conditioned** values (same as OSC / meters), **not** raw
- Default channel: `vocal_presence`
- Picker must include: `vocal_presence`, `rms`, `onset_strength`, `bass_energy`
- If user-banks exist: also `bank1`…`bank4`
- Do **not** offer `bpm` in the picker

### Time

- History: **3.0 s** at analysis rate (~43 Hz → ~130 points)
- Scroll: oldest left → newest right (or right-edge is “now” — pick one, stay consistent)
- Update with UI poll (~50ms) from a ring buffer the engine/UI fills each conditioned frame

### Triggers on the scope

- When the **selected** channel has a related bang, draw a tick:
  - `onset_strength` → `onset`
  - `bass_energy` → none required (or `kick` tick, optional)
  - `vocal_presence` → no factory vocal trigger; ticks optional/off
  - `bankN` → `bankN` bang if banks shipped
- Do **not** draw five stacked ECG traces

### Threshold hairline

- If selected channel is a **bank**, draw that bank’s threshold (0–1) as a horizontal line
- Otherwise omit, or use Tune float Threshold only if it maps cleanly — omit if confusing

### Tech

- `tkinter.Canvas` polyline is enough — **no** matplotlib / web chart
- Cap points; do not leak memory

### OSC / MIDI

Unchanged. Scope is display-only.

---

## 6. Acceptance criteria

- [ ] Scope visible under Monitor, ~80–100px, last ~3s
- [ ] Default plot is conditioned `vocal_presence`
- [ ] User can switch rms / onset_strength / bass_energy (and banks if present)
- [ ] Trace updates while running; idle is flat/empty, not a crash
- [ ] Related trigger ticks on the same strip (where defined)
- [ ] No new Python chart dependency
- [ ] Scrollable window still works with scope + Tune + Banks
- [ ] README: one sentence what the scope shows
- [ ] Append **Implemented** on this file

---

## 7. Do / Don't

**Do** — one scope, conditioned data, short time, vocal default  
**Don't** — graph every param, don't use bpm as a wave, don't add a browser/chart lib

---

## Done means

User plays a vocal track, sees a heartbeat-like line move with the voice, and can switch the scope to rms/onset/banks to tune by eye.

---

## Implemented (Programming agent — 2026-08-11)

- One tkinter Canvas scope (~90px) under Monitor; last **3.0s**, left=old / right=now
- Default channel `vocal_presence`; picker: rms / onset_strength / bass_energy / bank1–4 (no bpm)
- Engine ring buffer filled each analysis frame; bank threshold hairline; ticks: onset / kick / bankN
- No new chart library; README one-liner
