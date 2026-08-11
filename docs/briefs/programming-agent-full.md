---
status: Approved
from: Designer agent
to: Programming agent
project: Music_Analyse
engine_priority: TouchDesigner
date: 2026-08-11
supersedes:
  - docs/briefs/programming-agent-day1.md
  - docs/briefs/programming-agent-day1-update-conditioning.md
updates:
  - docs/briefs/programming-agent-update-kick-accuracy.md
  - docs/briefs/programming-agent-update-tune-mute.md
  - docs/briefs/programming-agent-update-scroll-osc-pulse.md
  - docs/briefs/programming-agent-update-user-banks.md
  - docs/briefs/programming-agent-update-scope.md
  - docs/briefs/programming-agent-update-pro-mode.md
---

# Programming brief — Full (Python-only UI)

This is the **single source of truth** for the baseline app. Older Day 1 briefs are superseded where they conflict.

**Active updates (also implement):**
- [`programming-agent-update-kick-accuracy.md`](./programming-agent-update-kick-accuracy.md) — kick vs `bass_energy`; reduce piano false kicks
- [`programming-agent-update-tune-mute.md`](./programming-agent-update-tune-mute.md) — Tune panel (dynamics/triggers) + Mute audio monitor
- [`programming-agent-update-scroll-osc-pulse.md`](./programming-agent-update-scroll-osc-pulse.md) — scrollable Tune + OSC 0/1 pulses for TD
- [`programming-agent-update-user-banks.md`](./programming-agent-update-user-banks.md) — 4 user Hz/threshold banks → extra OSC floats/triggers
- [`programming-agent-update-scope.md`](./programming-agent-update-scope.md) — 3s heartbeat scope (default vocal)
- [`programming-agent-update-pro-mode.md`](./programming-agent-update-pro-mode.md) — Live vs Pro (look-ahead accuracy)

**Critical UI change:** replace the **Gradio / HTML server** control panel with a **native Python GUI only**. No local web server for the app UI.

---

## 1. Goal

Ship a local **Python-only** desktop tool that:

1. Analyses **one** audio source at a time — **File** *or* **Live** (never both)
2. Conditions signals (normalize + smooth) into TD-ready values
3. Streams **triggers + floats** to **TouchDesigner** via **OSC** (required) and **MIDI** (toggleable)
4. Exposes a **native window** (not a browser, not Gradio, not Flask/FastAPI UI)

Keep existing analysis / OSC / MIDI / `Engine` pipeline where possible; **swap the UI layer**.

---

## 2. Screens / surfaces

### In scope — one native control window

| Section | Contents |
|---------|----------|
| **Source** | Mode: File \| Live (mutually exclusive). File picker path, or live input-device dropdown |
| **Transport** | **Start** / **Stop** (primary actions) |
| **Outputs** | OSC enable + host + port; MIDI enable + output port dropdown |
| **Monitor** | Float meters (bars + numeric). Trigger indicators that flash on bang |
| **Status** | `idle` \| `running` \| `error` + short error message |

### Out of scope

- Gradio, Streamlit, FastAPI/Starlette pages, Electron, any `http://127.0.0.1:….` app UI
- Unreal targets, multi-source mix, cloud, auth, marketing/landing UI
- Dual `/ma/raw/*` OSC namespace (unless user asks later)

---

## 3. Layout & hierarchy

Single window, top → bottom:

```
[ Music Analyse ]
1. Source     → mode toggle → file path / Browse  OR  device dropdown
2. Transport  → Start | Stop
3. Outputs    → OSC (enable, host, port) | MIDI (enable, port)
4. Monitor    → trigger row (flash) → float meters
5. Status     → idle / running / error text
```

**States**

| State | Behavior |
|-------|----------|
| `idle` | Not analysing; Start enabled when source valid |
| `running` | Analysing + sending; Stop enabled |
| `error` | Show message; release audio/MIDI safely; return toward idle |

Empty: no file / no device → disable Start + short hint.  
Switching File ↔ Live while running → stop current source first.

---

## 4. Visual tokens (utility dark)

- Background: `#0d0d0d`–`#121212`
- Text: light gray / white (`#e8e8e8`)
- Accent (running / meter fill / trigger flash): cool green/cyan e.g. `#2ee6a6` — **not purple**
- Meters: simple horizontal bars
- Triggers: ~50–100ms flash on bang
- Monospace OK for numeric readouts
- Tool panel — not a marketing layout; no card-heavy chrome

---

## 5. UI technology (locked)

| Choice | Rule |
|--------|------|
| **Required** | Native Python GUI process only |
| **Preferred** | **`tkinter`** (stdlib) — no extra UI server, fewer moving parts |
| **Allowed alternative** | PySimpleGUI / Dear PyGui / PySide only if tkinter blocks meters badly — **must justify in README** |
| **Forbidden** | Gradio, Streamlit, local HTML/JS dashboard as the primary UI |

### Migration (current repo)

Code today uses **Gradio** (`src/music_analyse/app.py`, browser on `:7860`).

**Do this:**

1. Implement native UI (prefer `ui_tk.py` or rewrite `app.py`)
2. Wire the same `Engine` (or equivalent) — do not rewrite DSP unless needed for conditioning
3. Remove Gradio as a dependency from `requirements.txt` when native UI works
4. Update `main.py` + `README.md` — run opens a **desktop window**, not a URL
5. Drop Gradio `--port` UX; keep `--smoke-osc` (and similar CLI smoke tests)

Audio analysis + OSC/MIDI must keep working **headlessly** for smoke tests (no UI required for `--smoke-osc`).

---

## 6. Architecture & components

### Suggested layout

```
src/music_analyse/
  __init__.py
  main entry via ../../main.py
  config.py                 # OSC/MIDI + conditioner + audio defaults
  engine.py                 # orchestration: source → analyse → condition → out
  app.py / ui_tk.py         # native UI only
  audio/
    source.py               # FileSource | LiveSource (one active)
    analysis.py             # raw features
    condition.py            # normalize + smooth + trigger edges
  output/
    addresses.py            # OSC/MIDI map (single source of truth)
    osc_out.py
    midi_out.py
README.md
requirements.txt
```

### Data flow (mandatory)

```
AudioSource
  → analysis (raw features)
  → conditioner (normalize / smooth / trigger bangs)
  → ConditionedFrame
       → OscOutput
       → MidiOutput (if enabled)
       → UI meters / flashes
```

**One source of truth:** UI and OSC/MIDI all read **conditioned** values. Never send raw magnitudes on `/ma/float/*`.

### ConditionedFrame

```text
floats:
  rms, bass_energy, vocal_presence, onset_strength   # 0–1
  bpm                                                # tempo float (not forced 0–1)

triggers:   # True only on bang frame (edge), else False
  beat, kick, snare, hihat, onset
```

---

## 7. Signal conditioning (required)

### Float pipeline (rms, bass_energy, vocal_presence, onset_strength)

```
raw → floor → adaptive normalize → clamp 0..1 → attack/release EMA → out
```

| Stage | Behavior |
|-------|----------|
| Floor | `x = max(0, raw - noise_floor)` |
| Normalize | Divide by rolling max (or high percentile) over `norm_window_s` (~3s); use epsilon |
| Clamp | `[0, 1]` |
| Smooth | EMA with separate **attack_s** / **release_s** (rise faster than fall) |

**`bpm`:** keep as BPM on `/ma/float/bpm`. Optional `/ma/float/bpm_n` = `clamp((bpm-60)/120, 0, 1)` — nice-to-have, not blocking.

### Trigger pipeline

```
conditioned energy / onset_strength
  → rising edge vs threshold
  → refractory_ms gate
  → single bang
```

| Trigger | Basis (heuristic OK) |
|---------|----------------------|
| `onset` | conditioned `onset_strength` |
| `beat` | beat pulse + min interval / refractory |
| `kick` | low-band transient on conditioned energy |
| `snare` | mid transient |
| `hihat` | high-band transient |

No ML required. Perfect drum separation not required.

### Config defaults (live in `config.py`)

```text
noise_floor: ~0.01
norm_window_s: 3.0
attack_s: 0.01–0.05
release_s: 0.1–0.4
trigger_threshold: ~0.5 (per-trigger overrides OK)
refractory_ms: 50–100
```

Document these in README. Do not scatter magic numbers only inside the DSP loop.

---

## 8. OSC map (locked)

Default: **`127.0.0.1:8000`**

| Signal | Address | Args |
|--------|---------|------|
| beat | `/ma/trigger/beat` | `1.0` on bang frame, else `0.0` |
| kick | `/ma/trigger/kick` | `1.0` / `0.0` |
| snare | `/ma/trigger/snare` | `1.0` / `0.0` |
| hihat | `/ma/trigger/hihat` | `1.0` / `0.0` |
| onset | `/ma/trigger/onset` | `1.0` / `0.0` |
| rms | `/ma/float/rms` | float 0–1 conditioned |
| bass | `/ma/float/bass_energy` | float 0–1 |
| vocal | `/ma/float/vocal_presence` | float 0–1 |
| onset strength | `/ma/float/onset_strength` | float 0–1 |
| bpm | `/ma/float/bpm` | float BPM |

- Floats: every analysis frame (~block rate; document actual Hz)
- Triggers: **every frame, 0 or 1**. TouchDesigner OSC In CHOP holds last value — never send `1` without a following `0`.
- Do **not** rename addresses without Designer approval

---

## 9. MIDI defaults (toggleable; same logical signals)

| Signal | MIDI |
|--------|------|
| beat | Note 36 |
| kick | Note 36 (ch 10 OK, or ch 1 if simpler — document) |
| snare | Note 38 |
| hihat | Note 42 |
| onset | Note 37 |
| rms | CC 20 |
| bass_energy | CC 21 |
| vocal_presence | CC 22 |
| onset_strength | CC 23 |
| bpm | CC 24 scaled 60–180 → 0–127 **or** skip CC and document |

Port name preference: virtual **`Music Analyse`** when OS allows; else list ports in UI.

CC values must use **conditioned** 0–1 → 0–127.

---

## 10. Audio rules

- Sample pipeline may stay ~**22050 Hz**, block **512** (~43 Hz) unless you have a reason to change — document if changed
- File and Live share the same analyse → condition → output path
- Start/Stop must open/close devices cleanly (no leaked streams/callbacks)
- Day 1 heuristics OK for drums/vocal presence

---

## 11. Dependencies

- Keep: numpy, scipy, librosa, sounddevice, soundfile, python-osc, mido, python-rtmidi
- **Remove** Gradio (and related web stack) once native UI ships
- Prefer **no new UI package** if using tkinter
- Pin whatever you add in `requirements.txt`

Existing venv: `source .venv/bin/activate`

---

## 12. Acceptance criteria

### Source & engine

- [ ] File **or** Live; never both at once
- [ ] Start/Stop clean; no device leaks
- [ ] Headless `--smoke-osc` (or equivalent) still works without opening UI logic that requires a display server beyond normal desktop

### Conditioning

- [ ] Outbound floats (except `bpm`) stay in **0–1** in normal use
- [ ] Noticeably smoother than raw; adaptive norm handles quiet/loud
- [ ] Triggers are short bangs; refractory prevents machine-gun doubles
- [ ] UI meters === OSC values (conditioned)

### Outputs

- [ ] OSC addresses match table; TD can receive at `127.0.0.1:8000`
- [ ] MIDI implemented and toggleable

### UI

- [ ] **Native Python window only** — no Gradio/HTML server for the control panel
- [ ] All sections present: Source, Transport, Outputs, Monitor, Status
- [ ] Dark utility look per tokens
- [ ] `README.md` updated: venv, `python main.py`, OSC map, MIDI map, conditioner knobs, TD `oscin` notes
- [ ] Gradio removed from deps/docs when migration done

---

## 13. Do / Don't

**Do**

- Python-native UI; reuse `Engine` / outputs where possible
- Condition before every consumer
- Stable OSC paths; config-driven thresholds
- Prefer low latency and reliability over visual polish

**Don't**

- Don’t keep Gradio/HTML as the primary UI
- Don’t send raw analysis on `/ma/float/*`
- Don’t change OSC path names or signal ids without Designer approval
- Don’t add Unreal, multi-input mix, or extra agents
- Don’t block on perfect drum ML

---

## 14. Implementation order

1. Confirm conditioner module exists (or add it) on the shared pipeline
2. Build **tkinter** (or approved native) window bound to `Engine`
3. Parity check: meters + OSC + MIDI match conditioned frame
4. Remove Gradio entrypath + dependency; update README
5. Smoke: file → TD OSC; live mic → meters; `--smoke-osc`

---

## 15. Done means

User runs `python main.py`, gets a **desktop Python window** (no browser), plays a file or selects live input, and TouchDesigner receives **smooth 0–1 floats** and **clean trigger bangs** on the locked `/ma/...` addresses.

---

## Note to Programming agent

When finished, append a short **Implemented** section at the bottom of **this** file (date + bullets: UI toolkit chosen, Gradio removed Y/N, conditioner status).

---

## Implemented (Programming agent — 2026-08-11)

- **UI:** `tkinter` (`ui_tk.py` / `app.py`) — native desktop window; `python main.py`
- **Gradio removed:** Y — dropped from `requirements.txt` and entrypath; no `:7860` UI
- **Conditioner:** `audio/condition.py` on shared pipeline (floor → adaptive norm → clamp → attack/release EMA; trigger edge + refractory)
- **Engine:** `analyse → condition → OSC/MIDI/UI` all consume `ConditionedFrame`
- **Smoke:** `python main.py --smoke-osc` (headless)
