---
status: Approved
type: update
from: Designer agent
to: Programming agent
parent: docs/briefs/programming-agent-full.md
project: Music_Analyse
date: 2026-08-11
---

# Update — Kick vs bass accuracy (false piano hits)

**Problem:** Mid/low **piano** (and similar pitched notes) often fire **kick** and feel like they “are” bass triggers. Low-band energy alone cannot tell a kick from a low piano note.

**Scope of this update:** items **1–3** only (product split + stricter kick detector + config). No drum-stem ML, no Unreal, no OSC address renames.

---

## 1. Goal

Reduce false **kick** bangs on pitched low/mid instruments (especially piano), while keeping **`bass_energy`** as a useful continuous low-frequency float for TD (piano energy allowed).

---

## 2. Screens / surfaces

**In scope**
- No new screens required
- Optional: expose kick sensitivity knobs in the native UI if easy; otherwise **config.py (+ README)** is enough for this update

**Out of scope**
- New OSC paths, snare/hihat redesign (unless a shared helper is reused), ML separation

---

## 3. Layout & hierarchy

Unchanged. Monitor still shows `bass_energy` meter and `kick` flash — they must **diverge** more often on piano-heavy material (bass moves, kick stays quiet).

---

## 4. Visual tokens

Unchanged.

---

## 5. Components / product + DSP rules

### 5.1 Product rule (do this first — conceptual + code)

| Signal | Role | Piano low notes |
|--------|------|-----------------|
| **`bass_energy`** | Continuous **low-band energy** float (0–1, conditioned) | **OK / expected** — may rise |
| **`kick`** | **Drum-like bang** trigger only | **Should NOT** bang under normal thresholds |

**Do not** derive `kick` primarily as `f(bass_energy)` alone.  
Current-style blend (`bass_energy * … + flux`) is too weak — replace kick decision with **multi-condition** logic below.

`bass_energy` pipeline (floor → adaptive norm → clamp → attack/release) can stay as-is unless a small band tweak helps clarity. This update is mainly about **kick**.

### 5.2 Kick detector — multi-condition (all required unless noted)

A **kick bang** only on **rising edge** when **all** gates pass, then **refractory**:

1. **Low transient** — strong short-term increase in sub/low band (flux / positive difference), not merely sustained loud low energy  
2. **Fast attack** — envelope / onset sharpness gate (kick-like hit, not slow pad swell)  
3. **Low harmonicity / weak pitch** — reject clearly pitched frames (piano harmonic series). Use a lightweight heuristic, e.g.:
   - harmonic peakiness / pitch salience / autocorrelation clarity in the low-mid range, **or**
   - spectral flatness / “inharmonic thud” score in the kick band  
   Bang only if harmonicity/pitch score is **below** `kick_harmonicity_max` (name flexible; meaning = “too pitched → not kick”)  
4. **Band / spectral shape (ratio)** — prefer kick-like shape, e.g.:
   - strong **sub / low** relative to clear mid harmonic banding, **and/or**
   - limited sustained harmonic peaks above the thud  
   Exact formula is implementer choice; must be documented in code comments + README in one short paragraph  
5. **Threshold + refractory** — `kick_threshold` on the combined kick score; `kick_refractory_ms` (or shared refractory with kick-specific override)

**Optional soft bonus (not required to ship):** coincident energy in a “beater” band (~2–6 kHz) can **raise** kick score, but must not be the only condition (some kicks are dark).

**Snare / hihat / beat / onset:** leave behavior unless they share utilities; do not regress them.

### 5.3 Config (required)

Add clear, tunable knobs in `config.py` (names may match style of existing `TRIGGER_THRESHOLDS`; keep a single home):

```text
kick_threshold          # score 0–1 crossing for bang (replace/override vague old kick thresh)
kick_harmonicity_max    # above this → treat as pitched → suppress kick
kick_min_flux           # minimum low-band transient (optional if folded into score)
kick_refractory_ms      # e.g. 80–150ms for kick
```

Also document how **`bass_energy`** differs from **`kick`** in README (2–4 sentences).

UI: exposing these as sliders is **nice-to-have**, not blocking.

### 5.4 OSC / MIDI

- Addresses **unchanged** (`/ma/trigger/kick`, `/ma/float/bass_energy`, …)
- Same conditioning rules as full brief for floats
- Kick MIDI note still only on bang

### 5.5 Suggested test material (manual)

Programming should sanity-check with:

- Drum loop / EDM kick — kick still fires  
- Solo low/mid piano — `bass_energy` may move; **kick rarely/never** at defaults  
- Mix with both — kicks on drums, not every piano stab  

---

## 6. Acceptance criteria

- [ ] `bass_energy` remains a conditioned 0–1 float driven by low-band energy (piano may affect it)
- [ ] `kick` is **not** essentially `bass_energy` with a threshold
- [ ] Kick requires **transient + attack + low-pitch/harmonicity gate + shape/ratio** (multi-condition)
- [ ] `kick_threshold` and `kick_harmonicity_max` (and refractory) live in config and are documented
- [ ] On piano-heavy test audio, false kick rate is **clearly lower** than before at default settings
- [ ] On kick/drum test audio, kicks still fire reliably at defaults (tune defaults until both feel OK)
- [ ] OSC paths unchanged; UI still shows both meter + kick flash
- [ ] README explains bass vs kick + new config knobs
- [ ] Append short **Implemented** note to this file when done

---

## 7. Do / Don't

**Do**
- Split product meaning: bass float vs kick bang
- Multi-gate kick; prefer fewer false positives over max recall
- Keep heuristics lightweight (CPU OK for ~block-rate analysis)

**Don't**
- Don’t rename OSC addresses
- Don’t “fix” bass_energy so piano never appears — that float is allowed to include piano
- Don’t add Demucs / heavy source separation in this update
- Don’t retune the whole drum kit unless necessary for shared code

---

## Done means

User can play piano-heavy material without constant fake kicks, while `bass_energy` still drives TD low-frequency looks; real kicks still bang.

---

## Implemented (Programming agent — 2026-08-11)

- Split product meaning: `bass_energy` stays low-band float (piano OK); `kick` is multi-gated drum bang (not `f(bass_energy)`)
- Kick gates: low transient (`KICK_MIN_FLUX`) + fast attack + harmonicity ≤ `KICK_HARMONICITY_MAX` + sub/mid shape ≥ `KICK_MIN_SHAPE` → score vs `KICK_THRESHOLD` + `KICK_REFRACTORY_MS`
- Features from analyser: `kick_flux`, `kick_attack`, `kick_harmonicity`, `kick_shape`, optional beater bonus
- Config + README documented; OSC paths unchanged
