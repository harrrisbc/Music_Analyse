---
status: Approved
type: update
from: Designer agent
to: Programming agent
parent: docs/briefs/programming-agent-full.md
project: Music_Analyse
date: 2026-08-11
related:
  - docs/briefs/programming-agent-update-kick-accuracy.md
---

# Update — Tune panel + Mute (audio monitor)

**Why**
- Users need hands-on **threshold / smoothing** (compressor-like) without editing `config.py`
- File/live **audio always playing out** the speakers is annoying during long TD sessions

**Depends on:** conditioning pipeline already in the full brief. Kick-accuracy update can ship in parallel; Tune should expose kick strictness once that config exists.

---

## 1. Goal

Add a native-UI **Tune** section (presets + dynamics + trigger knobs) and a **Mute** control that silences **program audio monitoring/playback** while analysis + OSC/MIDI continue.

---

## 2. Screens / surfaces

**In scope**
- Transport area: **Mute** toggle
- New collapsible **Tune** block under Monitor (or between Outputs and Monitor)
- Live apply: changing Tune/Mute while `running` updates the engine **without** requiring Stop/Start when possible

**Out of scope**
- Per-float independent compressors
- Exposing raw FFT band edges
- Muting OSC/MIDI (separate feature later if needed)
- Saving user presets to disk (session + built-in presets enough for this update)

---

## 3. Layout & hierarchy

```
1. Source
2. Transport     → Start | Stop | Mute
3. Outputs       → OSC / MIDI
4. Monitor       → triggers + floats
5. Tune          → collapsed by default (▸ Tune)
      Preset: Gentle | Normal | Tight | Kick safe
      --- Floats (dynamics) ---
      Threshold | Amount | Attack | Release | Makeup (optional)
      --- Triggers ---
      Sensitivity | Hold | Kick strictness
6. Status
```

**Mute** sits with Transport (high visibility).  
**Tune** stays collapsed so daily use stays clean.

---

## 4. Visual tokens

Unchanged dark utility look.

- Mute **on** (silenced): accent or clear “MUTED” state so user knows speakers are off
- Mute **off**: quieter labeling (“Mute”)
- Tune sliders: compact; monospace value readouts OK
- Tooltips: one short line each (see mapping below)

---

## 5. Components & behavior

### 5.1 Mute (audio monitor only)

| | |
|--|--|
| **What it mutes** | App **speaker / headphone output** — file playback monitor and any live input passthrough/monitoring |
| **What it does NOT mute** | Analysis, conditioned signals, **OSC**, **MIDI**, UI meters |
| **Default** | **Muted ON** (safer for studio / TD sessions). Document in README. |
| **Persistence** | Session is enough; remembering last state in config is nice-to-have |
| **UI** | Toggle button or checkbutton labeled **Mute** next to Start/Stop |

If current architecture plays file audio via the same stream as analysis, implement mute as **output gain = 0** (or `sounddevice` output disabled) — **do not** stop the analyser.

Live mode: if there is no monitor passthrough, Mute can be disabled/grayed with hint “No monitor in Live”, **or** still shown for consistency but no-op — pick one and document.

### 5.2 Tune — Float dynamics (global, compressor-like)

Applies to conditioned floats: `rms`, `bass_energy`, `vocal_presence`, `onset_strength`.  
**Does not** reshape `bpm` tempo value.

| UI label | Maps to (engine) | Feel | Tooltip |
|----------|------------------|------|---------|
| **Threshold** | noise floor / gate before norm | cuts rumble | “Ignore levels below this” |
| **Amount** | how hard adaptive norm / dynamic depth pulls toward 0–1 | flatter vs punchier | “How hard levels are normalized” |
| **Attack** | EMA `attack_s` | snappier follow | “How fast levels rise” |
| **Release** | EMA `release_s` | longer tails | “How fast levels fall” |
| **Makeup** (optional) | post gain then re-clamp 0–1 | overall lift | “Boost after dynamics” |

Wire sliders to the existing conditioner config paths (extend `config` if needed). Prefer a single **Dynamics** object on the engine/conditioner updated from UI.

Suggested slider ranges (tune defaults to match current good behavior ≈ **Normal** preset):

```text
Threshold:  0.0 – 0.1
Amount:     0.0 – 1.0   (internal: maps to norm strength / window behavior — document mapping)
Attack:     0.005 – 0.1 s
Release:    0.05 – 1.0 s
Makeup:     0.5 – 2.0    (1.0 = unity; optional control)
```

### 5.3 Tune — Triggers

| UI label | Maps to | Tooltip |
|----------|---------|---------|
| **Sensitivity** | global trigger threshold scale (higher sensitivity = lower thresholds / more bangs) | “More / fewer triggers” |
| **Hold** | refractory / min interval (ms) | “Min time between bangs” |
| **Kick strictness** | inverse of pitch rejection ceiling (`kick_harmonicity_max` or equivalent from kick-accuracy brief) | “Reject pitched lows (piano)” |

If kick-accuracy knobs are not merged yet, implement Sensitivity + Hold now; add Kick strictness as soon as that config exists (same Tune row).

### 5.4 Presets

Buttons or segmented control. Setting a preset writes all Tune fields; user can then tweak.

| Preset | Intent |
|--------|--------|
| **Gentle** | higher threshold, slower attack/release, lower sensitivity — calm TD |
| **Normal** | match current shipped defaults |
| **Tight** | lower threshold, faster attack, shorter release, higher sensitivity |
| **Kick safe** | Normal/Gentle floats + **high kick strictness** + slightly lower kick sensitivity — fewer piano false kicks |

Exact numeric tables: Programming chooses values that feel distinct; list them in README.

### 5.5 OSC / MIDI

Unchanged addresses. Mute must **not** stop sending `/ma/...`.

---

## 6. Acceptance criteria

- [ ] **Mute** silences app audio monitor/playback; analysis + OSC + MIDI + meters keep running
- [ ] Default session starts **Muted**
- [ ] Mute control visible in Transport; clear on/off state
- [ ] **Tune** panel exists, collapsed by default
- [ ] Float knobs: Threshold, Amount, Attack, Release (+ Makeup if implemented) affect conditioned floats live
- [ ] Trigger knobs: Sensitivity, Hold; Kick strictness if kick config available
- [ ] Presets Gentle / Normal / Tight / Kick safe apply a full Tune snapshot
- [ ] Changing Tune while running updates behavior without requiring restart (best effort)
- [ ] README: Mute meaning, Tune controls, preset intent, default Muted
- [ ] Append **Implemented** note on this file when done

---

## 7. Do / Don't

**Do**
- Treat Mute as **speaker monitor**, not “pause outputs”
- Keep Tune global and compressor/gate-shaped
- Live-update conditioner when sliders move

**Don't**
- Don’t mute OSC/MIDI when Mute is on
- Don’t stop the engine to mute
- Don’t dump every internal DSP constant into the UI
- Don’t require Advanced per-signal pages in this update

---

## Done means

User can leave the app running into TD with **speakers quiet (Mute)**, and open **Tune** to feel compressor-like float control + trigger sensitivity — especially **Kick safe** for piano-heavy tracks.

---

## Implemented (Programming agent — 2026-08-11)

- **Mute** in Transport: default ON; silences File `output_gain` only — analysis/OSC/MIDI/meters continue; Live = no monitor (hint shown)
- **Tune** collapsible panel: Threshold / Amount / Attack / Release / Makeup + Sensitivity / Hold / Kick strictness; live `apply_tune`
- Presets: Gentle / Normal / Tight / Kick safe (`tune.py`)
- README updated for Mute + Tune mappings
