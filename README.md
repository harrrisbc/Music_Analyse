# Haris Music Analyser (v1)

Offline-first pipeline: **stereo mix → Demucs drums stem → kick/snare cue sheet → edit → lock → live OSC** while the track plays on a Mac. Built for **TouchDesigner** and **Unreal** receivers on the same UDP stream.

This is **not** a live RMS/spectrum clone of TouchDesigner’s audio analysis — v1 only follows **pre-baked, editable** kick/snare hits.

## What v1 does

| Stage | Where | What |
|-------|--------|------|
| Separate | Windows + NVIDIA (optional) | Demucs `htdemucs` two-stems → `drums.wav` |
| Detect | Same machine (CPU OK) | Onset + spectral classify → `cues.json` |
| Edit | Any | JSON edit or `hma cues add/remove` |
| Lock | Any | `hma cues lock` → `*.locked.json` |
| Play + OSC | MacBook (no GPU) | Play mix; send `/music/kick` and `/music/snare` floats |

**Out of scope:** live pitch-to-MIDI, vocals/melody/chords, IR, TD/Unreal UI plugins (only receive docs below).

## Requirements

- **Python 3.11+** (3.12 recommended on Windows)
- **PyTorch** + **Demucs** for separation (install torch for CPU or CUDA separately)
- **Mac playback:** `sounddevice` + PortAudio (no Demucs required if you only play locked cues)

## Install

```bash
cd Music_Analyse
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

### PyTorch (separation)

**Windows + NVIDIA (faster):**

```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
```

**CPU only (Mac or no GPU):**

```bash
pip install torch torchaudio
```

Demucs is pulled in via `pip install -e .`; separation is only needed on the offline Windows path.

## CLI (`hma`)

```bash
hma --help
```

### 1. Windows offline — full pipeline

```bat
hma pipeline "C:\tracks\song.wav" -w C:\tracks\song_work --device cuda
```

Outputs in `song_work/`:

- `drums.wav`
- `cues.json`
- `cues.mid`

Use `--device cpu` if CUDA is unavailable (much slower).

### Step-by-step

```bash
hma separate mix.wav -o work/drums.wav --device cuda
hma detect work/drums.wav --mix mix.wav -o work/cues.json
hma export work/cues.json -o work/
```

### 2. Edit cues

Edit `work/cues.json` in any editor, or:

```bash
hma cues list work/cues.json
hma cues add work/cues.json 1.25 kick --velocity 0.9
hma cues remove work/cues.json 3
```

Tune detection for the next run via `profiles/default.yaml` (copy to `profiles/my_song.yaml` and pass `--profile my_song`).

| Knob | Effect |
|------|--------|
| `onset.delta` | Higher → fewer onsets |
| `onset.min_interval_sec` | Minimum time between hits |
| `classification.kick_centroid_max_hz` | Stricter kick band |
| `classification.snare_centroid_min_hz` | Stricter snare band |
| `velocity.onset_strength_*` | Maps hit strength → cue velocity |

### 3. Lock

```bash
hma cues lock work/cues.json -o work/cues.locked.json
```

Playback requires `detection.locked: true`.

### 4. Mac — play + OSC

```bash
hma play mix.wav --cues work/cues.locked.json --osc-host 127.0.0.1 --osc-port 9000
```

Smoke test without audio:

```bash
hma osc-test --host 127.0.0.1 --port 9000
```

## Cue JSON

See [examples/schema.md](examples/schema.md), [examples/cues.example.json](examples/cues.example.json), and [examples/cues.empty.json](examples/cues.empty.json).

## Receiving OSC

### TouchDesigner

1. Add **OSC In** CHOP, network port **9000** (or your `--osc-port`).
2. Channels from addresses `/music/kick` and `/music/snare` (float 0–1).
3. Use **Filter** or **Logic** CHOPs to turn velocity spikes into triggers if needed.

### Unreal Engine

1. Enable **OSC** plugin.
2. Add an **OSC Server** on port **9000**.
3. Bind `/music/kick` and `/music/snare` to Blueprint events (float argument = velocity).

Same packets work for both engines; no per-target format in v1.

## Project layout

```
src/haris_music_analyser/
  separate.py    # Demucs drums
  detect.py      # Kick/snare onsets
  export.py      # JSON + MIDI
  playback.py    # Audio + OSC
  cli.py         # `hma` entry
profiles/        # Detection defaults (also under package)
examples/        # Sample cue JSON + schema notes
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT — Haris Wong
