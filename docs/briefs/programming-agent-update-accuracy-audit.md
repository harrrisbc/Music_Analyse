---
status: Implemented
type: update
from: Designer agent
to: Programming agent
parent: docs/briefs/programming-agent-full.md
date: 2026-08-11
---

# Update — Accuracy audit (Live + Pro)

Designer read the current code. Structure is good. This brief lists **specific accuracy bottlenecks found in the code** and the fix for each, ordered by impact.

**Hard constraint:** Live-mode latency must not regress. Items marked **Live-safe** cost no added delay. Items marked **Pro-only** may spend the look-ahead budget.

Do not change OSC/MIDI addresses or the signal list.

---

## 1. Goal

Raise trigger precision (fewer false kicks/snares, more honest onsets, steadier beat) without touching Live latency feel.

---

## 2. Findings and fixes

### A. Frequency resolution is too coarse for low-band work — **Live-safe**

**Where:** `analysis.py` uses `n_fft = BLOCK_SIZE = 512` at 22050 Hz → **~43 Hz per bin**.

**Why it hurts:** the kick band 40–150 Hz is roughly **2–3 bins**. Sub-bass, kick fundamental, and a low piano note land in the same bin, so `kick_shape` and `bass_energy` cannot separate them, and user Bank 1 (40–120 Hz) is nearly a single bin.

**Fix:** keep hop 512 (latency unchanged), but window a **zero-padded / longer analysis frame** for the spectrum — e.g. `n_fft = 2048` over the last 2048 samples with hop 512 (same pattern `pro_analysis.py` already uses via `_overlap`). Latency added ≈ frame fill only, not extra waiting once running.

**Acceptance:** bins in the kick band go from ~3 to ~12; Bank 1 at 40–120 Hz uses >5 bins.

---

### B. Band energy uses `mean(magnitude)` — **Live-safe**

**Where:** `_band_energy` in both analysers: `float(np.mean(mag[mask]))`.

**Why it hurts:** linear magnitude mean is dominated by the loudest bin, has no perceptual scaling, and makes thresholds song-dependent (why users must retune per track).

**Fix:**
- Use **power** (`mag**2`) summed over the band, then convert to **dB** (e.g. `10*log10(p + eps)`), then map dB to 0–1 over a fixed range (e.g. −60…0 dB) before the conditioner.
- Keep the conditioner's adaptive normalize on top.

**Acceptance:** thresholds behave similarly across a quiet acoustic track and a loud master; `bank` thresholds no longer need big changes per song.

---

### C. Onset flux is full-spectrum mean, not spectral-flux best practice — **Live-safe**

**Where:** `flux = mean(max(mag - prev_mag, 0))`.

**Why it hurts:** no log compression, no per-band normalization, so bass energy dominates the onset signal, and hats/vocal consonants barely register.

**Fix:** compute flux on **log-magnitude** (`log1p(mag)` or dB), optionally on a **mel/band-grouped** spectrum (e.g. 20–40 bands), then sum positive differences. This is the standard superflux-style improvement and is cheap.

**Acceptance:** `onset_strength` responds to hats and vocal attacks, not only to low-end.

---

### D. Per-band flux ratio saturates and is not comparable across bands — **Live-safe**

**Where:**
```
kick_flux = max(0, e - prev) / (e + prev + 1e-9)
```

**Why it hurts:** this ratio maxes at 1.0 whenever the band was near-silent (0 → anything = 1.0). Quiet passages produce full-scale "flux", which is a real false-positive source, and `KICK_MIN_FLUX = 0.22` then behaves inconsistently.

**Fix:** gate the ratio by an absolute floor: require the band's **current energy** to exceed a small absolute (dB) floor before the ratio counts; or use `(e - prev) / (running_median(e) + eps)` so the denominator reflects recent context rather than the last frame only.

**Acceptance:** near-silence no longer produces flux ≈ 1; kicks after a break still register.

---

### E. `kick_attack` is derived from broadband RMS, not the kick band — **Live-safe**

**Where:** `_attack_score(rms)` — dual EMA on **overall** RMS.

**Why it hurts:** a loud snare, a vocal shout, or a full-mix hit all raise broadband RMS, so the "fast attack" gate passes on non-kick events. It is effectively a generic loudness-jump detector.

**Fix:** run the same dual-EMA attack on the **kick-band energy** (and give snare/hihat their own band attack if reused). Keep the broadband version only as a weak tiebreak if wanted.

**Acceptance:** attack gate stops passing on non-low-band transients.

---

### F. Harmonicity autocorrelation runs on a 512-sample block — **Live-safe (bounded)**

**Where:** `_harmonicity` autocorrelation over lags for 80–400 Hz.

**Why it hurts:** at 22050 Hz, 80 Hz needs a lag of ~276 samples inside a 512-sample block — barely two periods, so the low-frequency clarity estimate is noisy exactly where piano-vs-kick matters. Also a Python `for` loop over lags each hop.

**Fix:**
- Compute autocorrelation over the **longer overlap buffer** (the same 2048 window from item A), not the 512 hop.
- Vectorize via FFT-based autocorrelation instead of the Python loop.

**Acceptance:** `kick_harmonicity` is stable frame-to-frame on sustained piano; CPU per hop does not rise.

---

### G. Snare/hihat levels are contaminated by `onset_strength` — **Live-safe**

**Where:** `condition.py`:
```
snare_e = onset_e * 0.45 + snare_flux * 0.9
hihat_e = onset_e * 0.35 + hihat_flux * 0.95
```

**Why it hurts:** `onset_e` is the **conditioned** global onset (with ~250 ms release), so a kick or any loud event lifts snare and hihat levels toward their thresholds. This creates correlated false bangs — every kick nudges snare.

**Fix:** drive snare/hihat from their **own band flux + own band attack** (mirroring the kick gate structure, minus the piano-specific harmonicity rule). Use the global onset only as a small optional bonus, or drop it.

**Acceptance:** on a kick-only loop, snare/hihat do not approach threshold.

---

### H. Beat tracking is IOI-median on *every* flux frame — **Pro-only + Live-safe part**

**Where:** `analysis.py` collects `ioi` whenever `flux > 1e-6` (essentially every frame with any energy), takes a rolling median of 24, and free-runs a phase accumulator.

**Why it hurts:** the IOI list is filled with non-beat intervals, so BPM is a median of noise; the phase accumulator then drifts and re-syncs on any in-tolerance flux.

**Fix:**
- **Live-safe:** only feed IOI from **peak-picked onsets** (local maximum above an adaptive threshold), not every frame with flux.
- **Pro:** `pro_analysis.py` already has a rolling audio buffer — use autocorrelation of the onset envelope (or `librosa.beat.beat_track`, already a dependency) over 6–8 s to set BPM **and** phase, then predict beats forward.

**Acceptance:** BPM stays stable on a steady loop (±2 BPM) instead of wandering; `beat` lands on-grid.

---

### I. Adaptive normalize uses rolling **max** — **Live-safe**

**Where:** `_condition_float`: `peak = max(history)` over ~3 s.

**Why it hurts:** a single click or clipped sample sets the ceiling for the whole window, collapsing everything else toward 0 for 3 seconds. This is a common "meters went dead" cause.

**Fix:** use a **high percentile** (e.g. 95th) of the window instead of max, or decay the peak toward the recent percentile. The brief already said "rolling max **or high percentile**" — percentile is the robust choice.

**Acceptance:** one transient spike no longer flattens the channel for seconds.

---

### J. Look-ahead confirmation can be fooled by its own inputs — **Pro-only**

**Where:** `lookahead.py::_confirm` compares the candidate against future frames of the **same** strength signal, with `DRUM_LIKE` sustain check.

**Why it hurts:** for banks it uses the **conditioned** float (long release), so the "did it decay" test is measuring the EMA, not the instrument. Comment in `_strength` acknowledges this for drums but banks still use conditioned values.

**Fix:** give banks a **raw band energy** strength (the analyser already exposes `band_energy_hz`) so decay confirmation sees the real envelope. Keep a short pre-window check too: a true drum hit should have **low energy immediately before** the candidate.

**Acceptance:** Pro bank triggers reject sustained pads/piano in the same band, while short hits still pass.

---

### K. Pro HPSS window is short and beat buffer is underused — **Pro-only**

**Where:** `_maybe_hpss` runs median filtering over a rolling spec of up to 48 frames, every 3 hops.

**Why it hurts:** ~1 s of context with a small median kernel gives weak separation; the percussive residual still contains piano transients. Meanwhile `PRO_BEAT_BUFFER_S = 8` audio is retained but only lightly used.

**Fix:**
- Increase HPSS context (longer spec deque) and/or use `librosa.decompose.hpss` on a periodically-refreshed buffer, caching the mask for reuse between refreshes.
- Consider computing HPSS masks less often but over a bigger window — accuracy comes from context, not from running it every hop.

**Acceptance:** in Pro, a piano-only passage shows visibly lower percussive-band energy than in Live.

---

### L. Everything is mono-summed at 22.05 kHz — **Live-safe (config)**

**Where:** `SAMPLE_RATE = 22_050`, `CHANNELS = 1`.

**Why it hurts:** 22.05 kHz caps analysis at ~11 kHz, which clips real hi-hat/cymbal energy (much of it 8–16 kHz). `HIHAT_BAND` is 5–10 kHz, right at the ceiling.

**Fix:** offer **44.1 kHz** analysis (at least in Pro). Keep hop proportional so frame rate stays ~43 Hz if desired (hop 1024 at 44.1 kHz).

**Acceptance:** hi-hat detection improves on bright material; no dropouts.

---

## 3. Suggested order

1. **A** larger analysis window (unlocks C, E, F quality)
2. **B** dB/power band energy
3. **G** independent snare/hihat gates
4. **D** flux floor
5. **I** percentile normalize
6. **E** band-specific attack
7. **C** log/band-grouped flux
8. **H** peak-picked IOI → Pro beat tracking
9. **F** FFT autocorrelation on long window
10. **J**, **K**, **L** Pro refinements

Ship in small steps; verify Live latency feel after each.

---

## 4. Acceptance criteria (overall)

- [ ] Live latency feel unchanged (user confirms)
- [ ] Piano-heavy material: fewer false `kick` at default Tune than today
- [ ] Kick-only loop: `snare` / `hihat` stay below threshold
- [ ] Silence → first hit does not produce a burst of triggers
- [ ] One loud spike does not flatten meters for seconds
- [ ] BPM stable within ±2 on a steady loop
- [ ] Thresholds need less per-song retuning (dB scaling)
- [ ] CPU still real-time in both modes; Pro degrades gracefully
- [ ] README notes any new config knobs
- [ ] Append **Implemented** to this file with what shipped and what was skipped

---

## 5. Do / Don't

**Do**
- Keep Live and Pro sharing one conditioner/OSC contract
- Prefer dB / percentile / band-local statistics over raw linear means
- Make each fix independently revertable

**Don't**
- Don’t add latency to Live
- Don’t rename OSC addresses or signals
- Don’t introduce heavy ML/stem separation in this pass
- Don’t rewrite the UI

---

## Implemented (Programming agent — fill in)

Shipped 2026-08-11. Live hop unchanged (512 @ 22050). OSC/MIDI untouched. No UI rewrite.

| Item | What shipped | Notes |
|------|----------------|-------|
| **A** | Live `n_fft = LIVE_N_FFT` (2048) over `_overlap`, hop 512 | Kick band **10 bins** (not 12); Bank 1 40–120 Hz **8 bins** |
| **B** | Power → dB → 0–1 (`BAND_DB_MIN` −80 … `BAND_DB_MAX` 0), scaled by `n_fft²` | Conditioner still adaptive-norms on top |
| **C** | Onset = positive flux on 32 log-spaced bands of `log1p` mag | Small absolute floor `0.012` so noise does not adaptive-norm to 1 |
| **D** | `FluxTracker`: ratio vs rolling median, gated by `FLUX_ABS_FLOOR` (0.05) | Near-silence no longer yields flux ≈ 1 |
| **E** | Dual-EMA attack on **kick / snare / hihat band energy** (`AttackTracker`) | Broadband RMS attack removed |
| **F** | `kick_harmonicity` on the 2048/4096 overlap buffer; FFT autocorr (vectorized) | Python lag loop gone |
| **G** | Snare/hat from own flux+attack + shape exclusivity; **no** `onset_e` mix | Kick-only loop: snare/hat stay 0 |
| **H** | Live IOI only from `OnsetPeakPicker` local maxima; Pro `beat_track(..., units="time")` sets BPM **and** phase | Live ~123 BPM on a 120 loop (was ~143) |
| **I** | Conditioner peak = **95th percentile** of the norm window | Single spike no longer sets the ceiling |
| **J** | Banks use **raw** `band_energy_hz` in look-ahead; pre-window check on banks only | Drum look-ahead postpones a couple hops if a later peak is stronger (long FFT rise) |
| **K** | HPSS context `PRO_SPEC_FRAMES` 128, median kernels 31/21, every 6 hops | `librosa.decompose.hpss` still skipped (too slow per hop) |
| **L** | Pro **44100 / hop 1024 / n_fft 4096**; hat band 5–16 kHz | Live mic falls back to 22050 if the device refuses 44.1 |

**Verify (synth):** Live kick 16/16 @ 120 BPM, 0 snare/hat crosstalk, 0 piano kicks, 1 kick after silence, −40 dB still 16/16, BPM 123, ~0.5 ms/hop. Pro fires the same kicks ~130–160 ms late (120 ms look-ahead + peak wait), BPM 120, ~3 ms/hop (p95 ~11, under 23 ms).

**Skipped / follow-ups:** librosa HPSS; Live still 22.05 kHz (hats above 11 kHz only in Pro); FileSource still uses `np.interp` (aliasing on resampled files — not in this brief).
