---
status: Approved
type: update
from: Designer agent
to: Programming agent
parent: docs/briefs/programming-agent-full.md
date: 2026-08-11
related:
  - docs/briefs/programming-agent-update-kick-accuracy.md
  - docs/briefs/programming-agent-update-tune-mute.md
---

# Update — User frequency banks (custom Hz + threshold)

**Why:** Built-in kick/snare/hihat are fixed-band heuristics. They shipped items 1–5 but still misfire on real tracks. Users need a few **custom bands** they can tune per song (frequency range + threshold) and send to TouchDesigner.

**Does not replace** factory signals (`kick`, `snare`, `hihat`, `bass_energy`, …). Banks are **extra** user instruments.

---

## 1. Goal

Give the user **4 banks**. Each bank: a frequency range + threshold → one **conditioned float** + one **trigger bang**, streamed on new locked OSC/MIDI paths.

---

## 2. Screens / surfaces

**In scope**
- Native UI section **Banks** (collapsible, like Tune), scrollable with the rest of the window
- Per bank: enable, Hz low, Hz high, threshold, live meter + trigger flash
- Optional name field (display only; OSC ids stay `bank1`…`bank4`)
- Live-update while running (no restart)

**Out of scope**
- Unlimited banks, EQ drawing, FFT waterfall editor
- Removing or renaming factory `/ma/trigger/kick` etc.
- Saving banks to disk this update (session + 3 built-in bank presets enough)
- ML / stem separation

---

## 3. Layout & hierarchy

```
… Monitor …
▸ Tune          (existing)
▸ Banks         (new, collapsed by default)
    Bank presets: [Kick-ish | Snare-ish | Hat-ish | Reset]
    ┌ Bank 1 ☑  name: ________  [flash]
    │  Low Hz ────●──  High Hz ────●──
    │  Threshold ────●──           [meter]
    ├ Bank 2 …
    ├ Bank 3 …
    └ Bank 4 …
… Status …
```

If space is tight: each bank is one compact block (enable + Hz + threshold + mini meter). Do not hide High Hz.

**Empty / invalid:** if Low ≥ High, show short error on that bank and **disable** its output (float 0, no bangs) until fixed.

---

## 4. Visual tokens

Unchanged dark utility. Bank meters/flashes use the same accent as factory monitor. Disabled bank: muted chrome, no OSC traffic (or send 0 — pick one, document).

---

## 5. Components

### 5.1 Bank definition

```text
Bank N (N = 1..4):
  enabled: bool
  name: str          # UI only, default "Bank N"
  lo_hz: float
  hi_hz: float
  threshold: float   # 0–1, trigger gate on conditioned band energy
```

**Defaults (usable starting points, user will retune):**

| Bank | Default Hz | Default thr | Intent |
|------|------------|-------------|--------|
| 1 | 40–120 | 0.55 | kick / sub |
| 2 | 150–800 | 0.50 | snare / low-mid |
| 3 | 2000–6000 | 0.45 | hat / beater / presence |
| 4 | 300–3400 | 0.50 | vocal-ish (off by default) |

Bank 4 **starts disabled**. 1–3 start **enabled**.

**Slider ranges**

```text
lo_hz / hi_hz: 20 – 10000  (log-scale sliders strongly preferred)
threshold: 0.05 – 0.95
```

Clamp and enforce `hi_hz > lo_hz` (auto-nudge hi if user crosses, or block output — auto-nudge by ~10 Hz is friendlier).

### 5.2 DSP (per enabled bank, every analysis frame)

Reuse the existing FFT / magnitude from `Analyser` (do not run a second full pipeline).

```
band energy (mean mag in [lo, hi))
  → same conditioner path as other floats
       (floor / adaptive norm / clamp / attack-release / makeup from global Tune)
  → float out 0–1

trigger: rising edge of that conditioned float vs bank.threshold
  → global Hold (Tune hold_ms) refractory
  → bang
```

Do **not** run the kick multi-gate on banks. Banks are honest **frequency + threshold** tools. That is the point.

### 5.3 OSC (new, locked)

Default host/port unchanged. **Every frame** send 0/1 for triggers (same TD pulse rule as factory triggers).

| Bank | Float | Trigger |
|------|-------|---------|
| 1 | `/ma/float/bank1` | `/ma/trigger/bank1` |
| 2 | `/ma/float/bank2` | `/ma/trigger/bank2` |
| 3 | `/ma/float/bank3` | `/ma/trigger/bank3` |
| 4 | `/ma/float/bank4` | `/ma/trigger/bank4` |

Disabled bank: send `0.0` on both (so TD never sticks).

### 5.4 MIDI

| Bank | Note (bang) | CC (float 0–1 → 0–127) |
|------|-------------|-------------------------|
| 1 | 48 | 30 |
| 2 | 49 | 31 |
| 3 | 50 | 32 |
| 4 | 51 | 33 |

Same channel conventions as existing map. Document in README.

### 5.5 Bank presets (fill all 4 slots)

| Preset | Bank1 | Bank2 | Bank3 | Bank4 |
|--------|-------|-------|-------|-------|
| **Kick-ish** | 40–100 thr 0.58 | 80–160 thr 0.55 | 2k–6k thr 0.50 (beater) | off |
| **Snare-ish** | 150–400 thr 0.50 | 1k–4k thr 0.48 | 6k–10k thr 0.45 | off |
| **Hat-ish** | 5k–8k thr 0.42 | 8k–10k thr 0.40 | 2k–5k thr 0.48 | off |
| **Reset** | restore shipped defaults above (1–3 on, 4 off) |

Presets only write bank Hz/threshold/enable — do not overwrite Tune compressor knobs.

### 5.6 UI monitor

Each bank: small meter = that bank’s conditioned float; flash on its bang. Factory Monitor section stays as-is.

### 5.7 Code shape (suggested)

```text
config or banks.py — BankParams, defaults, presets
analyser — band energy for arbitrary lo/hi (already has _band_energy)
conditioner or engine — condition 4 extra floats + 4 extra bangs
addresses.py — BANK_FLOATS / BANK_TRIGGERS
ui_tk.py — Banks panel
```

Keep factory `ConditionedFrame` fields and add `bank_floats` / `bank_triggers` **or** extend the dicts — either is fine if OSC/UI stay consistent.

---

## 6. Acceptance criteria

- [ ] 4 banks in UI; 1–3 on, 4 off by default
- [ ] User can set Low Hz, High Hz, Threshold per bank; live while running
- [ ] Each enabled bank outputs conditioned 0–1 float + bang (threshold + Hold)
- [ ] OSC: `/ma/float/bankN` and `/ma/trigger/bankN` with 0/1 every frame
- [ ] Disabled banks send 0
- [ ] Invalid range (lo ≥ hi) does not crash; bank outputs 0
- [ ] Bank presets apply Hz/thr/enable only
- [ ] Factory kick/snare/hihat/bass paths unchanged
- [ ] Window still scrollable with Banks expanded
- [ ] README: what banks are, OSC/MIDI table, vs factory kick
- [ ] Append **Implemented** on this file

---

## 7. Do / Don't

**Do**
- Treat banks as user EQ-gates: honest frequency + threshold
- Reuse FFT + global Tune dynamics + Hold
- Keep factory detectors; banks are the accuracy escape hatch

**Don't**
- Don’t make banks run kick harmonicity gates
- Don’t add more than 4 banks this update
- Don’t rename existing `/ma/trigger/kick` etc.
- Don’t require file save/load yet

---

## Done means

On a piano-heavy or odd-mix track, user can park **Bank 1** on the actual kick thud Hz they hear, raise threshold, and drive TD from `/ma/trigger/bank1` when factory `kick` is still messy.

---

## Implemented (Programming agent — 2026-08-11)

- 4 banks (`banks.py`): defaults 1–3 on / 4 off; presets Kick-ish / Snare-ish / Hat-ish / Reset
- DSP: reuse analyser FFT `band_energy_hz`; conditioner path + Hold; no kick multi-gate
- OSC `/ma/float/bankN` + `/ma/trigger/bankN` every-frame 0/1; disabled → 0
- MIDI notes 48–51, CC 30–33
- UI ▸ 6. Banks (collapsed), log Hz sliders, live apply, meters/flashes
- README: banks vs factory kick + OSC/MIDI tables
