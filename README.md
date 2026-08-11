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
AudioSource → analysis (raw) → conditioner → ConditionedFrame
                                              ├─ OSC
                                              ├─ MIDI (if enabled)
                                              └─ UI meters / flashes
```

Analysis rate: **22050 Hz**, block **512** → **~43 Hz** frames.  
OSC floats every frame. Triggers are sent **every frame as `1.0` (bang) or `0.0`** so TouchDesigner OSC In CHOP does not hold a sticky `1`.

## Conditioner (`config.py`)

Floats (`rms`, `bass_energy`, `vocal_presence`, `onset_strength`):

`raw → floor → adaptive normalize (rolling max ~3s) → clamp 0..1 → attack/release EMA`

| Knob | Default |
|------|---------|
| `NOISE_FLOOR` | `0.01` |
| `NORM_WINDOW_S` | `3.0` |
| `ATTACK_S` | `0.03` |
| `RELEASE_S` | `0.25` |
| `TRIGGER_THRESHOLD` / per-trigger | `~0.5` |
| `REFRACTORY_MS` | `80` |

`bpm` stays as BPM on `/ma/float/bpm` (not forced 0–1).  
MIDI CC for floats uses **conditioned** 0–1 → 0–127; bpm CC scales 60–180 → 0–127.

### `bass_energy` vs `kick`

- **`bass_energy`** is a continuous **low-band energy** float (0–1, conditioned). Low piano notes **may and should** move it — useful for TD bass looks.
- **`kick`** is a **drum-like bang** only. It is **not** `threshold(bass_energy)`. A kick fires only when multi-gates pass: low-band **transient**, **fast attack**, **low harmonicity/pitch** (reject piano-like frames), and **sub vs mid-harmonic shape**, then `KICK_THRESHOLD` + `KICK_REFRACTORY_MS`.

| Kick knob | Default | Meaning |
|-----------|---------|---------|
| `KICK_THRESHOLD` | `0.58` | Combined score crossing for bang |
| `KICK_HARMONICITY_MAX` | `0.45` | Above → pitched → suppress kick |
| `KICK_MIN_FLUX` | `0.22` | Min low-band transient |
| `KICK_MIN_ATTACK` | `0.18` | Min envelope sharpness |
| `KICK_MIN_SHAPE` | `0.35` | Prefer sub thud vs mid harmonics |
| `KICK_REFRACTORY_MS` | `110` | Min ms between kick bangs |

Shape (analyser): `E(40–150) / (E(40–150) + E(200–2000))`.  
Harmonicity: spectral peakiness 100–1500 Hz + autocorr clarity ~80–400 Hz.

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
| Threshold | noise floor / gate | 0–0.1 |
| Amount | adaptive-norm strength (0=soft absolute, 1=full rolling-max norm) + shorter window when high | 0–1 |
| Attack | EMA attack_s | 0.005–0.1 s |
| Release | EMA release_s | 0.05–1.0 s |
| Makeup | post gain then clamp 0–1 | 0.5–2.0 |

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
| **Normal** | shipped defaults |
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

Factory `kick` is a multi-gate drum detector (transient + attack + harmonicity + shape).  
**Banks** are honest **frequency range + threshold** tools — park Bank 1 on the thud you hear when factory kick misfires. They use the same Tune compressor (floor / norm / attack-release / makeup) and **Hold**, but **not** kick strictness.

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

## UI layout

1. **Source** — File \| Live  
2. **Transport** — Start / Stop / **Mute**  
3. **Outputs** — OSC + MIDI  
4. **Monitor** — trigger flash + float meters + **3s heartbeat scope** (default `vocal_presence`; same conditioned values as OSC)  
5. **Tune** — collapsed; presets + dynamics + trigger knobs  
6. **Banks** — collapsed; 4 user Hz bands + presets  
7. **Status** — idle / running / error  

## Project layout

```
src/music_analyse/
  ui_tk.py / app.py     # tkinter UI
  engine.py             # source → analyse → condition → out
  config.py
  banks.py              # user frequency banks
  audio/source.py
  audio/analysis.py     # raw features
  audio/condition.py    # normalize + smooth + bangs
  output/osc_out.py
  output/midi_out.py
  output/addresses.py
main.py
docs/briefs/programming-agent-full.md
```
