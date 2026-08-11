# Music Analyse

Local **Python desktop** tool: analyse **one** audio source (file **or** live mic) → **condition** signals → stream **triggers + floats** to **TouchDesigner** via **OSC** (required) and **MIDI** (toggleable).

UI: **tkinter** (stdlib) — native window, **no browser / Gradio**.

## Setup

```bash
cd /Users/haha/Music_Analyse
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
source .venv/bin/activate
python main.py
```

Opens a desktop window (not a URL).

**Mute defaults ON** — File playback speakers are silenced; analysis + OSC/MIDI + meters still run. Unmute in Transport when you want to hear the file. Live mode has no speaker monitor (Mute is a no-op there).

Headless OSC smoke (no UI):

```bash
python main.py --smoke-osc
```

## Pipeline

```
AudioSource → Extract (Filters | Stems) → measure → conditioner → ConditionedFrame
                                                                    ├─ OSC
                                                                    ├─ MIDI (if enabled)
                                                                    └─ UI meters / flashes
```

Analysis rate: **~43 Hz** frames in both modes (Live hop 512 @ 22050; Pro hop 1024 @ 44100).  
OSC floats every frame. Triggers are sent **every frame as `1.0` (bang) or `0.0`** so TouchDesigner OSC In CHOP does not hold a sticky `1`.

**Mode** (Live | Pro) is a **latency / quality budget**. **Extract** (Filters | Stems) is **how** the mix becomes floats/triggers. Both extractors work in both modes.

## Live vs Pro

Same OSC/MIDI addresses. Switch under **Transport → Mode**. Default is **Live**.

| | **Live** (default) | **Pro** |
|--|--|--|
| Latency | Hop ~23 ms. Filters add no extra wait. | Triggers late by look-ahead (**60 / 120 / 200 ms**, default **120**) |
| Sample rate | 22050 | **44100** (hop 1024). Live mic falls back to 22050 if the device refuses 44.1 |
| Extract | Same Filters / Stems as Pro (Live hop / 2048 HPSS window if Stems) | Same extractors; Stems uses a longer HPSS context (4096). Look-ahead on **triggers only** |
| Triggers | Conditioner bangs go out immediately | Look-ahead **confirms** local peak + decay (banks use **raw** IIR energy). Floats are **not** delayed |
| Use | Shows / timing-critical TD | Studio — confirm bangs; pair with **Stems** for piano-heavy mixes |

Switching Mode or Extract auto-restarts if already running (status `switching…`). Look-ahead can change while Pro is running.

## Extract: Filters | Stems

Switch under **Transport → Extract**. Default is **Filters**.

| | **Filters** (default) | **Stems** |
|--|--|--|
| What | Causal `scipy` SOS IIR + per-block envelope. **No FFT** for factory floats or user banks. | Stem-lite: causal median HPSS → `{drums, vocals, bass, other}`, **then** the same IIR / RMS on the chosen stem |
| Banks | IIR on the **mix** (your Low/High Hz) | Same — banks stay on the mix |
| `vocal_presence` / `bass_energy` | IIR 300–3400 / 20–150 on the mix | RMS of **vocals** / **bass** stems |
| `kick` / `snare` / `hihat` / onset | IIR on the mix (kick 40–120, etc.) | IIR on the **drums** stem (kick = drums-low bang; mix-piano harmonicity is **not** a veto) |
| Extra delay | ~0 beyond the hop | HPSS window ≈ **n_fft / 2** (~**46 ms** Live and Pro). UI shows the real `stems · +~N ms` |
| Piano vs kick | Piano can still leak into kick (Hz overlap) — expected | Kick tracks percussion, not a low piano note |

**Stem-lite** (shipped): `drums` ← percussive, `vocals` ← harmonic mid (300–3400), `bass` ← LPF mix (~150 Hz), `other` ← residual. No neural / ONNX / Demucs in this build — Live+Stems is always this lite path (never disabled).

| | Filters | Stems |
|--|--|--|
| **Live** | Default. Causal IIR. No trigger look-ahead. | Stem-lite. No look-ahead. |
| **Pro** | Same IIR + existing trigger look-ahead. | Stem-lite + look-ahead on drum/vocal triggers. |

## Tap tempo

Transport **TAP** (or **Space**, unless an entry/combobox is focused) sets BPM from click intervals.

- BPM = `60 / median(last 3–8 intervals)` in the 40–240 range. One tap keeps the current BPM and **resets beat phase** to that click. Two or more taps update BPM.
- Gap **> 2.5 s** starts a new tap sequence (old intervals discarded). Phase still follows the latest tap.
- After the first tap this run, tempo is **locked**: Live IOI and Pro `beat_track` do not overwrite `/ma/float/bpm` or `/ma/trigger/beat`. The beat grid is free-running from the last tap.
- **− / +** change BPM by 1 and **keep phase** (the grid does not jump).
- **Stop** unlocks (auto BPM is the fallback again). Start / Live↔Pro restart keeps a lock if you already tapped.
- Kick / onset / floats are not delayed by tap. In Pro, tap `beat` skips look-ahead so it stays on your click.

## Conditioner (`config.py`)

Floats (`rms`, `bass_energy`, `vocal_presence`, `onset_strength`):

`raw → gate (Threshold) → mix(absolute, slow 80th-percentile level) → clamp 0..1 → attack/release EMA → Makeup`

Band energies **and RMS** are **power → dB → 0–1** (`BAND_DB_MIN`…`BAND_DB_MAX`, default **−55…−15**) before this chain so a normal phrase uses most of 0–1.

| Knob | Default |
|------|---------|
| `NOISE_FLOOR` / `THRESHOLD_MAX` | `0.03` / `0.4` |
| `AMOUNT_DEFAULT` | `0.35` |
| `NORM_WINDOW_S` | `10.0` |
| `NORM_PERCENTILE` | `80` |
| `BAND_DB_MIN` / `BAND_DB_MAX` | `-55` / `-15` |
| `FLUX_ABS_FLOOR` | `0.08` |
| `ATTACK_S` | `0.03` |
| `RELEASE_S` | `0.25` |
| `TRIGGER_THRESHOLD` / per-trigger | `~0.5` |
| `REFRACTORY_MS` | `80` |
| `SNARE_MIN_FLUX` / `SNARE_MIN_ATTACK` | `0.20` / `0.16` |
| `HIHAT_MIN_FLUX` / `HIHAT_MIN_ATTACK` | `0.18` / `0.14` |
| `LIVE_N_FFT` | `2048` |
| `PRO_SAMPLE_RATE` / `PRO_HOP` / `PRO_N_FFT` | `44100` / `1024` / `4096` |

`bpm` stays as BPM on `/ma/float/bpm` (not forced 0–1).  
MIDI CC for floats uses **conditioned** 0–1 → 0–127; bpm CC scales 60–180 → 0–127.

### `bass_energy` vs `kick`

- **`bass_energy`** is a continuous **low** float (0–1, conditioned). Filters: 20–150 Hz IIR on the mix (piano **may and should** move it). Stems: RMS of the **bass** stem.
- **`kick`** is a **drum-like bang** only. It is **not** `threshold(bass_energy)`.
  - **Filters:** multi-gate on mix IIR (transient + attack + mid-vs-thud hint + threshold). Piano can still leak.
  - **Stems:** drums-low envelope bang + Hold. Mix-piano harmonicity is **not** a veto.

| Kick knob | Default | Meaning |
|-----------|---------|---------|
| `KICK_THRESHOLD` | `0.58` | Combined score crossing for bang |
| `KICK_HARMONICITY_MAX` | `0.45` | Above → pitched → suppress kick |
| `KICK_MIN_FLUX` | `0.22` | Min low-band transient |
| `KICK_MIN_ATTACK` | `0.18` | Min envelope sharpness |
| `KICK_MIN_SHAPE` | `0.35` | Prefer sub thud vs mid harmonics |
| `KICK_REFRACTORY_MS` | `110` | Min ms between kick bangs |

Shape (Filters): `E(40–120) / (E(40–120) + E(200–2000))` from IIR envelopes.  
Harmonicity (Filters): mid vs thud ratio (no mix-FFT). Unused as a veto when Extract=Stems.

## Mute (audio monitor)

| | |
|--|--|
| **Mutes** | App speaker / headphone **file playback** monitor (`output gain = 0`) |
| **Does not mute** | Analysis, conditioned floats/triggers, **OSC**, **MIDI**, UI meters |
| **Default** | **Muted ON** (`MUTE_DEFAULT = True`) |
| **Live** | No monitor passthrough — Mute shown for consistency, no-op on speakers |

## Tune panel (▸ collapsed by default)

Live-applied compressor-like dynamics + trigger feel (`tune.py` → conditioner). No Stop/Start needed.

### Floats

| Control | Maps to | Range |
|---------|---------|-------|
| Threshold | noise **gate** — ignore levels below this. Raising it does **not** open the range | 0–0.4 |
| Amount | 0 = full phrase dynamics; 1 = slow 10 s / 80th-percentile leveling. **Down** = more movement | 0–1 |
| Attack | EMA attack_s | 0.005–0.1 s |
| Release | EMA release_s | 0.05–1.0 s |
| Makeup | post gain then clamp 0–1. **Up** = louder / more travel | 0.5–2.0 |

### Triggers

| Control | Maps to |
|---------|---------|
| Sensitivity | scales thresholds (higher → more bangs) |
| Hold | refractory / min interval (ms) |
| Kick strictness | lowers harmonicity ceiling + slight kick threshold boost (reject piano) |

### Presets

| Preset | Intent |
|--------|--------|
| **Gentle** | higher threshold, slower dynamics, lower sensitivity — calm TD |
| **Normal** | light leveling (`Amount` 0.35) — phrase should use most of 0–1 |
| **Tight** | snappy attack/release, higher sensitivity, short Hold |
| **Kick safe** | calmer floats + **high kick strictness** + slightly fewer kicks |

## OSC map (TouchDesigner)

Default: **`127.0.0.1:8000`**

| Signal | Address | Args |
|--------|---------|------|
| beat | `/ma/trigger/beat` | `1.0` bang frame, else `0.0` |
| kick | `/ma/trigger/kick` | `1.0` / `0.0` |
| snare | `/ma/trigger/snare` | `1.0` / `0.0` |
| hihat | `/ma/trigger/hihat` | `1.0` / `0.0` |
| onset | `/ma/trigger/onset` | `1.0` / `0.0` |
| rms | `/ma/float/rms` | float 0–1 conditioned |
| bass | `/ma/float/bass_energy` | float 0–1 |
| vocal | `/ma/float/vocal_presence` | float 0–1 |
| onset strength | `/ma/float/onset_strength` | float 0–1 |
| bpm | `/ma/float/bpm` | BPM float |
| bank1–4 | `/ma/float/bankN` | float 0–1 conditioned (user Hz band) |
| bank1–4 | `/ma/trigger/bankN` | `1.0` / `0.0` every frame |

Disabled banks still send `0.0` on both paths so TD never sticks.

### User banks vs factory kick

Factory `kick` is a drum detector (Filters: multi-gate on mix IIR; Stems: drums-low bang).  
**Banks** are honest **IIR frequency range + threshold** tools — park Bank 1 on the thud you hear when factory kick misfires. They use the same Tune compressor (floor / norm / attack-release / makeup) and **Hold**, but **not** kick strictness. Always measured on the **mix**.

| Bank default | Hz | Thr | On |
|--------------|----|-----|----|
| 1 | 40–120 | 0.55 | yes |
| 2 | 150–800 | 0.50 | yes |
| 3 | 2k–6k | 0.45 | yes |
| 4 | 300–3400 | 0.50 | **off** |

Bank presets (**Kick-ish / Snare-ish / Hat-ish / Reset**) only write Hz / threshold / enable — they do not change Tune.

### TD `oscin`

1. Add **OSC In** CHOP or DAT  
2. Active on, UDP port **8000**  
3. Map `/ma/trigger/*` (0/1 pulse each frame) and `/ma/float/*` continuous values  
4. Use a **rising-edge** / Trail / Count if you only want a bang — do not treat a held `1` as “always on” (we send `0` when idle)  

## MIDI map

Virtual port: **`Music Analyse`** (default). Toggle off in UI if unused.  
Hardware ports are listed only when you click **Refresh** (probed in a subprocess — CoreMIDI/rtmidi can abort the main process if enumerated at launch).

| Signal | MIDI |
|--------|------|
| beat | Note 36, ch 1 |
| kick | Note 36, ch 10 |
| snare | Note 38, ch 10 |
| hihat | Note 42, ch 10 |
| onset | Note 37, ch 1 |
| rms…onset_strength | CC 20–23, ch 1 |
| bpm | CC 24, ch 1 (60–180 → 0–127) |
| bank1–4 | Note 48–51, ch 1 (bang); CC 30–33, ch 1 (float) |

## Show vs Setup

Top-right toggle. Default after this ships is **Show**. Last view is restored with last-used.

| **Show** | Start / Stop / Mute / TAP + BPM (larger hit targets) · trigger flashes · float meters · scope · status. No vertical scroll at ~560×520. |
| **Setup** | Everything: Source, Mode/Extract, Outputs, Monitor, Tune, Banks, **Session Save… / Load…**, status. Scrollable (~560×720). |

Switching views does **not** stop the engine or reset knobs.

## Session + last-used

- **Last-used** (automatic): `~/.music_analyse/last_used.json` — written on quit (and ~1.5 s after Tune/Banks/etc). Restored on launch. Missing or corrupt → factory defaults, no modal. **Never auto-Starts.**
- **Named session**: Setup → `Session: [ Save… ] [ Load… ]`. Files are `*.ma.json` (default `show.ma.json` in `~/Documents`). Same JSON schema as last-used. Save does **not** replace last-used; quit still writes last-used. Load applies immediately (restart analyser only if Mode / Extract / device / file requires it).
- Schema `version: 1` — unknown keys ignored; missing keys use defaults. No audio files inside the JSON.

## UI layout

**Show** — transport + monitor + status  

**Setup**

1. **Source** — File \| Live  
2. **Transport** — Start / Stop / **Mute** · **TAP** + BPM −/+  
3. **Mode / Extract** — Live \| Pro · Filters \| Stems · Pro look-ahead  
4. **Outputs** — OSC + MIDI  
5. **Monitor** — trigger flash + float meters + **3s heartbeat scope** (default `vocal_presence`; same conditioned values as OSC)  
6. **Tune** — collapsed; presets + dynamics + trigger knobs  
7. **Banks** — collapsed; 4 user Hz bands + presets  
8. **Session** — Save… / Load…  
9. **Status** — idle / running / error  

## Project layout

```
src/music_analyse/
  ui_tk.py / app.py     # tkinter UI (Show | Setup)
  engine.py             # source → analyse → condition → out
  session.py            # last-used + named *.ma.json
  config.py
  banks.py              # user frequency banks
  audio/source.py
  audio/filters.py      # causal SOS IIR + envelope
  audio/stems.py        # Stem-lite HPSS → vocals/drums/bass/other
  audio/measure.py      # Extract → RawFrame (shared)
  audio/analysis.py     # Live budget wrapper
  audio/pro_analysis.py # Pro budget wrapper
  audio/spectrum.py     # dB map, flux, attack
  audio/lookahead.py    # Pro trigger confirm (delay bangs only)
  audio/condition.py    # normalize + smooth + bangs
  output/osc_out.py
  output/midi_out.py
  output/addresses.py
main.py
docs/briefs/programming-agent-full.md
```
