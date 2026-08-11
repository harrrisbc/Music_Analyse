---
status: Implemented
type: update
from: Designer agent
to: Programming agent
parent: docs/briefs/programming-agent-full.md
date: 2026-08-11
---

# Update — Live / Pro analysis modes

**Why:** Current **Live** path delay feels perfect. Accuracy is limited by one-block heuristics (no look-ahead, small FFT, no HPSS). User wants an optional **Pro** path that may add delay in exchange for cleaner kicks/vocals/beats.

**Do not** fork a second app. Same window, same OSC addresses, one engine with two analysers.

---

## 1. Goal

Add **Live** (default, current latency) and **Pro** (look-ahead + heavier analysis). User can switch; TD patch does not change.

---

## 2. Screens / surfaces

**In scope**
- Transport: mode toggle **Live | Pro**
- When Pro: short latency hint + optional look-ahead control
- Switching mode **stops and must Start again** (or auto-restart if already running — prefer auto-restart with a brief “switching…” status)

**Out of scope**
- Separate Pro binary / paid wall / cloud
- Unreal
- Changing OSC path names
- On-device ML drum kits (unless a tiny optional later)

---

## 3. Layout & hierarchy

```
2. Transport
   Start | Stop | Mute
   Mode: (• Live)  ( Pro )
   [Pro only] Look-ahead: 60 | 120 | 200 ms     hint: “+120 ms · more accurate”
```

Live selected → hide look-ahead row.  
Default mode: **Live**. Default Pro look-ahead: **120 ms**.

---

## 4. Visual tokens

Unchanged. Active mode uses accent. Pro hint = muted monospace.

---

## 5. What each mode is

### Live (keep as-is)

- Current block analyser (~22050 / 512, ~23 ms hop, ~43 Hz)
- Heuristic kick gates, simple beat IOI
- **Do not regress** this path. Delay must stay as today’s feel.

### Pro (new)

Same `ConditionedFrame` / banks / Tune / OSC / MIDI. Only **raw analysis + when a bang is committed** changes.

Spend the extra delay on these, in this order (all required unless a library blocks you — then skip HPSS and document):

| # | Technique | Why it costs delay | Accuracy win |
|---|---------|-------------------|--------------|
| 1 | **Look-ahead commit** | Wait `L` ms after a candidate peak before sending bang | Reject piano/false spikes that don’t decay like a drum |
| 2 | **Larger FFT** | e.g. `n_fft` 2048–4096, hop may stay 512 | Better harmonicity / pitch vs thud |
| 3 | **Peak-pick with pre/post** | Need future frames in the `L` buffer | Cleaner onset/kick/snare/hat/bank bangs |
| 4 | **HPSS** on a rolling buffer | librosa `hpss` (or equivalent) every N hops | Kick/snare/hat on **percussive**; vocal on **harmonic** |
| 5 | **Better beat/BPM** | Rolling 6–8 s buffer, update ~1 s (librosa `beat_track` OK) | Stable grid vs IOI jitter |

**Look-ahead commit (required even if HPSS slips):**

```
candidate bang at t
  hold until t + L
  if still the local peak / drum-like after confirmation
    send bang at t+L   (late by L, but fewer fakes)
  else
    suppress
```

Floats (`rms`, bands, vocal, banks) still stream every hop — **do not** delay the whole float stream by `L` if you can avoid it. Prefer delaying **triggers only**. If implementation is much simpler with a global delay line of `L` on all Pro outputs, that is allowed — document it in README and show the real delay in the UI hint.

### Shared rules

- Banks still use user Hz + threshold; in Pro, energy should come from the Pro spectrogram (percussive residual optional for bank triggers if it helps)
- Tune knobs still apply
- Mute / OSC 0–1 pulse contract unchanged
- Scope plots the same conditioned floats (may look slightly smoother in Pro)

### Suggested config

```text
MODE_DEFAULT = "live"          # live | pro
PRO_LOOKAHEAD_MS = 120         # 60 | 120 | 200
PRO_N_FFT = 2048               # or 4096
PRO_HOP = 512                  # keep ~43 Hz if possible
PRO_BEAT_BUFFER_S = 8.0
```

UI look-ahead options must write `PRO_LOOKAHEAD_MS` live (restart analyser if needed).

### CPU

Pro may use more CPU. If a hop overruns, drop HPSS rate (run HPSS every 2–4 hops) rather than glitching audio. Never let Pro break Live.

---

## 6. Acceptance criteria

- [ ] Transport shows **Live | Pro**; default Live
- [ ] Live behavior / latency matches today’s analyser (no “always Pro”)
- [ ] Pro uses look-ahead (60/120/200, default 120) and larger FFT
- [ ] Pro kick/onset false positives clearly better on piano-heavy material at default 120
- [ ] Pro still fires kicks on a normal drum/EDM test (recall not destroyed)
- [ ] OSC addresses unchanged; 0/1 trigger pulse rule unchanged
- [ ] UI shows Pro extra delay; README explains Live vs Pro and the trade
- [ ] Switching mode is safe (no leaked streams)
- [ ] Append **Implemented** on this file

---

## 7. Do / Don't

**Do**
- One app, two modes
- Spend delay on look-ahead + confirmation + HPSS/beat, not on UI chrome
- Keep Live sacred for timing-critical TD

**Don't**
- Don’t replace Live with Pro
- Don’t add a second OSC namespace
- Don’t ship a separate “Music Analyse Pro” repo
- Don’t add >200 ms look-ahead in this update

---

## Done means

User keeps **Live** for shows (current delay). For studio / tough mixes they switch **Pro**, accept ~+120 ms, and get fewer fake kicks / more stable vocal & beat — same TD addresses.

---

## Implemented (Programming agent — fill in)

- Transport: **Live | Pro** (default Live, accent on active). Pro-only look-ahead **60 / 120 / 200 ms** (default 120) + muted hint `+N ms · more accurate`.
- Live path unchanged: `Analyser` 512 FFT, no look-ahead.
- Pro: `ProAnalyser` (`n_fft` 2048, hop 512), cheap median HPSS every N hops (perc drums / harm vocal; librosa `hpss` skipped — hop overrun). `beat_track` on 8 s buffer ~1 s in a background thread. `TriggerLookahead` delays **triggers only** (local peak + decay confirm). Floats stream every hop.
- Mode switch swaps analyser and auto-restarts if running (`switching`). Look-ahead updates live. OSC 0/1 pulse + addresses unchanged.
- README: Live vs Pro trade. Config: `MODE_DEFAULT`, `PRO_LOOKAHEAD_MS`, `PRO_N_FFT`, `PRO_HOP`, `PRO_BEAT_BUFFER_S`.
