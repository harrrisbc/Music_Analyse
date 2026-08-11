---
status: Implemented
type: update
from: Designer agent
to: Programming agent
parent: docs/briefs/programming-agent-full.md
date: 2026-08-11
related:
  - docs/briefs/programming-agent-update-pro-mode.md
  - docs/briefs/programming-agent-update-user-banks.md
  - docs/briefs/programming-agent-update-tap-tempo.md
  - docs/briefs/programming-agent-update-accuracy-audit.md
---

# Update — Dual extractors: Filters + Stems (both in Live and Pro)

**Why:** FFT bins cannot tell a kick from a low piano. Two better ways to turn audio into TD data:

1. **Filters** — IIR band-pass + envelope (no FFT). Fast, honest Hz, good for banks/floats.
2. **Stems** — split mix into vocals / drums / bass / other, **then** measure. Better kick/vocal identity.

**Both extractors must work in Live and in Pro.** Live/Pro stays a **latency / quality budget**, not “which algorithm.”

OSC addresses and signal names stay locked.

---

## 1. Goal

Add an **Extract** choice: **Filters | Stems**.  
Each works under **Live** and **Pro**. Same conditioner, Tune, banks UI, TAP, OSC/MIDI.

---

## 2. Screens / surfaces

**In scope**

Transport / analysis row:

```
Mode:     ( Live )  ( Pro )          [existing]
Extract:  ( Filters )  ( Stems )
```

When **Stems**: one muted hint, e.g. `stems · +~40 ms` (Live) or `stems · +~120 ms` (Pro) — show the **real** extra delay you implement.

**Out of scope**

- New OSC namespaces
- Per-stem mixer UI, waveform editors
- Shipping a huge GPU-only model as the only path
- Removing TAP (beat still user-tap first)

---

## 3. Layout & hierarchy

Put **Extract** on the same row as Mode, or the next row (do not hide it inside Tune).

```
2. Transport
   Start | Stop | Mute | TAP + BPM
   Mode: Live | Pro     Extract: Filters | Stems
   [Pro look-ahead row — unchanged]
```

Switching Extract while running: same rule as Mode — restart analyser safely (`switching…`).

---

## 4. Visual tokens

Unchanged. Active Extract radio uses the same accent as Live/Pro.

---

## 5. Architecture (read this first)

Split the pipeline into **Extract → Measure → Condition → Out**.

```
Audio block
    │
    ├─ Extract: Filters
    │     IIR bands on the mix → envelopes
    │
    └─ Extract: Stems
          separator → 4 waveforms {vocals, drums, bass, other}
          then Filters/RMS/onset **on the chosen stem**
    │
    ▼
Measure (same for both)
    envelopes / RMS / onset → raw floats
    rising-edge + Hold → triggers
    TAP clock → bpm + beat
    │
    ▼
Conditioner (existing Tune) → OSC / MIDI / UI
```

**Do not** keep inventing kick identity from mix-FFT bins when Stems is on.  
**Do not** require FFT for Filters path (factory bands + user banks).

Live vs Pro only changes **budget**:

| | Live | Pro |
|--|------|-----|
| **Filters** | Causal IIR + envelope, hop as today (~23 ms). No look-ahead required. | Same filters + existing Pro look-ahead / confirmation on **triggers only**. |
| **Stems** | Light / low-latency separator (or HPSS-lite 2-way if neural not ready). Keep delay modest. | Better separator and/or more context. May use Pro look-ahead on triggers. |

If a neural stem model cannot meet Live budget, Live+Stems must still run: fall back to **causal HPSS** (harmonic vs percussive) mapped as `vocals≈harmonic`, `drums≈percussive`, `bass≈low-passed mix or percussive-low`, `other≈residual`. Document the fallback in README. **Do not** disable Stems in Live.

---

## 6. Extractor A — Filters (IIR + envelope)

### 6.1 DSP

Per band, sample-accurate or per-block equivalent:

```
x  →  SOS / biquad band-pass [lo_hz, hi_hz]
   →  abs (or half-wave)
   →  attack / release envelope   (reuse Tune attack_s / release_s or band-local)
   →  raw float (then existing conditioner)
```

- Use `scipy.signal.butter` + `sosfilt` (keep state across blocks — **zi**).
- Causal only (no `sosfiltfilt`).
- User **Banks 1–4**: these filters **are** the bank (Low/High Hz already in UI). Stop using `band_energy_hz` FFT mean for banks when Extract=Filters.
- Factory floats from fixed filter bands (may match current Hz):

| Float | Default band (start here; document) |
|-------|-------------------------------------|
| `bass_energy` | 20–150 Hz |
| `vocal_presence` | 300–3400 Hz |
| `rms` | no band — full-band envelope / RMS |
| `onset_strength` | high-pass or wide mid (e.g. 200–8000) envelope **derivative** / positive flux of that envelope — not mix-FFT flux |

### 6.2 Triggers on Filters

- `onset` — rising edge of `onset_strength` (threshold + Hold), same as now.
- `kick` / `snare` / `hihat` — **not** “FFT bin identity.” Use envelopes of:
  - kick: 40–120 Hz (or Bank-1 defaults)
  - snare: 150–800 + 2–6 kHz click (product or OR of two envelopes; keep simple)
  - hihat: 5–10 kHz (Live 22.05k) / 5–16 kHz if sr allows  
  plus existing multi-gate **only if it still helps**; prefer envelope peak + Hold. Piano will still leak into kick on Filters — that is expected. Stems is the identity fix.
- `beat` — **TAP clock only** when tap-locked (existing tap brief). Filters must not overwrite tapped BPM.

### 6.3 Why this exists

User-tunable Hz that actually means Hz (unlike 3 FFT bins). Low CPU. Works offline and live.

---

## 7. Extractor B — Stems then measure

### 7.1 Stems

Always produce four mono (or mid) signals, same sample rate as analysis:

| Stem | Meaning |
|------|---------|
| `vocals` | singing / lead voice |
| `drums` | kit / percussion |
| `bass` | bass instruments |
| `other` | the rest |

Implementation order (ship 1, then 2 if time):

1. **Stem-lite (required):** causal / block HPSS + low crossover  
   - `drums` ← percussive  
   - `vocals` ← harmonic mid (300–3400) **or** harmonic residual  
   - `bass` ← low-pass mix (~20–150)  
   - `other` ← mix − drums − vocals − bass (energy-safe, no negative blow-up)
2. **Stem-neural (optional, Pro-preferred):** small real-time model (ONNX / open-unmix / similar) if it runs on CPU without dropouts. If it only fits Pro, Live keeps Stem-lite automatically and UI hint says `stems (lite)`.

Do **not** block this update on Demucs-class offline models.

### 7.2 Measure after stems (this is the accuracy win)

| Signal | Measure on |
|--------|------------|
| `vocal_presence` | envelope / RMS of **vocals** |
| `bass_energy` | envelope / RMS of **bass** |
| `rms` | mix (unchanged) |
| `onset_strength` | onset / envelope flux of **drums** (not the full mix) |
| `kick` | low envelope (40–120 Hz **Filters** on **drums** stem) + Hold |
| `snare` | mid/click Filters on **drums** |
| `hihat` | high Filters on **drums** |
| User banks | IIR on **mix** by default; optional later: route bank to a stem. Day-1 of this brief: banks stay on mix so UI Hz still makes sense. |

Kick multi-gate harmonicity on the **mix** is the wrong tool once drums are separated. On Stems, kick = **drums-low envelope bang**. Drop mix-piano harmonicity as a required gate (it may stay as a weak extra, not a veto).

### 7.3 Latency

- Stem-lite: document hop / crossover delay.
- Neural: process on a **side thread** + ring buffer if needed so the audio callback never blocks (StemgenRT-style). Live may show slightly older stems; never glitch the file/live device.

---

## 8. Live × Pro × Extract (matrix)

| | Filters | Stems |
|--|---------|--------|
| **Live** | Default extract. Causal IIR. No trigger look-ahead. | Stem-lite (or neural if it meets budget). No / short look-ahead. |
| **Pro** | Same IIR, **plus** existing trigger look-ahead / confirmation. | Better stem (neural if available) + look-ahead on drum/vocal triggers. |

Defaults:

- Extract default: **Filters** (keeps today’s delay feel).
- Mode default: **Live** (unchanged).

---

## 9. Code shape (suggested)

```
src/music_analyse/audio/
  filters.py      # SOS band + envelope, zi state, factory + bank instances
  stems.py        # StemSeparator protocol; HpssLiteSeparator; optional NeuralSeparator
  measure.py      # stem-or-mix → RawFrame fields (or keep in analyser)
  analysis.py     # Live analyser becomes: extract + measure (FFT optional/legacy)
  pro_analysis.py # same extractors, Pro budget
engine.py         # extract_mode = "filters" | "stems"  (independent of analysis_mode)
ui_tk.py          # Extract radios
config.py         # EXTRACT_DEFAULT, stem/filter constants
```

`Engine.set_extract_mode("filters"|"stems")` + restart-if-running, parallel to `set_analysis_mode`.

`snapshot()` includes `extract_mode` for UI.

Reuse Tune conditioner on whatever raw floats Measure emits. Do not bypass conditioner.

---

## 10. OSC / MIDI / TAP

Unchanged addresses.  
`/ma/float/*` still 0–1 conditioned (except `bpm`).  
Triggers still **0/1 every frame**.  
TAP still owns BPM/beat when locked.

---

## 11. Acceptance criteria

- [ ] UI: Extract **Filters | Stems** visible; works in **Live and Pro** (2×2)
- [ ] Filters: user banks and factory floats come from **IIR + envelope**, not FFT bin mean
- [ ] Filters stays real-time; Live delay feel not worse than today
- [ ] Stems always available in Live (lite fallback if neural missing/slow)
- [ ] Stems: `vocal_presence` tracks vocal stem; `kick` tracks **drums-low**, not mix-piano
- [ ] Piano-heavy file: Stems+kick clearly fewer fakes than Filters+kick at defaults
- [ ] Drum loop: Stems kick still fires
- [ ] Switching Extract or Mode does not leak devices
- [ ] OSC paths unchanged; TAP still wins for beat
- [ ] README: Extract vs Mode matrix, Stem-lite vs neural, latency hints
- [ ] Append **Implemented** (what separator shipped, Live stems = lite or neural)

---

## 12. Do / Don't

**Do**

- Offer **both** extractors in **both** modes
- Measure kick/vocal **after** stems when Stems is on
- Keep Filters as the low-latency, user-Hz tool
- Keep TAP for tempo

**Don't**

- Don’t make Stems Pro-only
- Don’t make Filters Live-only
- Don’t wait on a giant GPU separator to ship Filters
- Don’t rename `/ma/...`
- Don’t send raw mix-FFT as `vocal_presence` when Stems is selected

---

## Done means

User can stay on **Live + Filters** for tight TD timing and tweak bank Hz like analog EQ; switch **Stems** (still Live or Pro) when they need kick/vocal to mean instruments, not frequency.

---

## Implemented (Programming agent — fill in)

**2026-08-11 — shipped**

- Extract **Filters | Stems** in Transport (same row as Live | Pro). Both work in both modes. Default Extract = **Filters**. Switching Extract/Mode remakes the analyser and restarts if running (`switching…`).
- Pipeline: `filters.py` (causal `butter` SOS + `zi`) · `stems.py` (`HpssLiteSeparator`) · `measure.py` (`ExtractingAnalyser`) · Live/Pro wrappers only change budget (`22050/512/2048` vs `44100/1024/4096`).
- **Filters:** factory floats + user banks are IIR envelopes (no FFT bin mean). Kick/snare/hat = band envelopes on the mix. Weak mid-vs-thud hint only — piano can still leak (expected).
- **Stems:** Stem-lite only (no neural). `drums` ← perc, `vocals` ← harmonic mid 300–3400, `bass` ← LPF mix ~150 Hz, `other` ← residual. Then measure: vocal/bass RMS on those stems; kick/snare/hat/onset IIR on **drums**. Banks stay on the mix. `RawFrame.kick_from_stem` skips mix-piano harmonicity / shape veto and the snare/hat kick-shape mute.
- Extra Stems delay = **n_fft / 2** ≈ **46 ms** (Live and Pro). UI hint: `stems · +~46 ms`. Pro look-ahead still applies on top to triggers only. TAP still owns BPM/beat. OSC `/ma/...` unchanged.
- Live+Stems is never disabled. Neural separator not shipped.
