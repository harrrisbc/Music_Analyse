---
status: Implemented
type: update
from: Designer agent
to: Programming agent
parent: docs/briefs/programming-agent-full.md
date: 2026-08-11
priority_order:
  - 3_last_used
  - 1_named_session
  - 2_show_view
---

# Update — Last-used restore, named Sessions, Show view

**Why:** Opening the app always resets to factory defaults. That is the easiest way to blow a show. The window is also too tall to hit Start/TAP while scrolling Tune/Banks.

**Ship in this order (do not start 2 before 1; do not start 1 before 3):**

3. **Last-used restore** — auto-remember on quit, restore on launch  
1. **Named Session** — Save / Load Tune + Banks + I/O + Mode/TAP  
2. **Show view** — compact live surface; Setup stays scrollable  

Native Python UI only. No new OSC addresses.

---

## 1. Goal

Next launch feels like “yesterday’s rig.” User can also save/load named show files. During performance they get a compact **Show** view.

---

## 2. Screens / surfaces

**In scope**

- Silent last-used file (no UI required for step 3)
- Session **Save… / Load…** (step 1)
- View toggle **Show | Setup** (step 2)

**Out of scope**

- Cloud sync, multi-user, encryption
- Auto-start playback on launch
- Redesign of Tune/Banks internals (only visibility)

---

## 3. Implementation order

### Phase 3 — Last-used restore (do first)

On **quit** (`WM_DELETE_WINDOW` and any clean exit), write a JSON sidecar.

On **launch**, after widgets exist, load it and apply **before** first Start. Missing/corrupt file → factory defaults, no crash, no modal.

**Path:** `~/.music_analyse/last_used.json`  
(or `Path.home() / ".music_analyse" / "last_used.json"`). Create the directory if needed. Do not put secrets. Add `last_used.json` to `.gitignore` if you ever write it inside the repo (you should not).

**Do not** auto-Start. Restore settings only.

### Phase 1 — Named Session Save / Load

Same payload schema as last-used (reuse one `SessionState` serialize/deserialize).

UI (Setup only is fine):

```
Session:  [ Save… ]  [ Load… ]
```

Place near Status or Transport — not buried only in a menu. File dialog:

- Save: `~/Documents` or last folder; filter `*.ma.json` (or `*.json`)
- Default filename: `show.ma.json`

Load applies immediately (engine Tune/Banks/Mode/outputs). If running, apply live where possible; restart analyser only if Mode/Extract/device change requires it.

**Save does not replace last-used** — quit still writes last-used separately. Loading a session should also update the in-memory state that quit will persist.

### Phase 2 — Show view

Two views, one window:

| View | Contains |
|------|----------|
| **Show** (default after this ships) | Start / Stop / Mute / TAP + BPM / trigger flashes / float meters / scope / short status+error |
| **Setup** | Everything today (Source, Outputs, Mode/Extract, Tune, Banks, Session Save/Load) + same transport strip |

Toggle: **Show | Setup** top-right (or under title). Persist last view in last-used.

Show view:

- **No vertical scroll required** at 1280×800 / typical laptop. Target window ~560×520 or whatever fits the compact stack without clipping TAP.
- Meters + scope stay; Tune/Banks/Outputs/file browser **hidden**
- If user needs a knob mid-show: switch to Setup, change, switch back — values stay

Do not duplicate a second Engine. Hide/show frames.

---

## 4. Visual tokens

Unchanged dark utility. Show view: larger TAP and Start (easier hit). BPM readout stays high-contrast (accent chip OK).

---

## 5. Session schema (shared)

Version the file. Unknown keys ignored; missing keys → defaults.

```json
{
  "version": 1,
  "view": "show",
  "source": {
    "mode": "file",
    "file_path": "/absolute/or/empty",
    "live_device_label": "2: BlackHole 2ch"
  },
  "transport": {
    "mute": true
  },
  "analysis": {
    "mode": "live",
    "lookahead_ms": 120,
    "extract": "filters"
  },
  "tempo": {
    "bpm": 128.0,
    "tap_locked": false
  },
  "osc": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 8000
  },
  "midi": {
    "enabled": true,
    "port": "Music Analyse"
  },
  "tune": { },
  "banks": [ ]
}
```

`tune`: dump `TuneParams.to_dict()`.  
`banks`: list of `{index, enabled, name, lo_hz, hi_hz, threshold}`.

**Restore rules**

- File path: if missing on disk, keep mode File, clear path, hint “file not found”, do not crash.
- Live device: match label; if gone, first available device.
- MIDI port: same — fall back to first / default name.
- `extract`: if that feature is not in the build yet, ignore.
- `tap_locked` + `bpm`: restore BPM number; do not require re-tapping. Beat phase can start fresh.
- Never restore “running”.

**When to write last-used**

- On quit (required)
- Optional: debounce-write 1–2 s after Tune/Banks change (nice). Do not write every slider tick synchronously if it hitchs the UI.

---

## 6. Components

Suggested:

```
src/music_analyse/session.py   # SessionState, load/save path, last_used path
ui_tk.py                       # apply/collect state; Show/Setup frames; Save/Load buttons
```

Keep JSON in stdlib (`json`). No new deps.

Window title may show session name after Load (`Music Analyse — club.json`); optional.

---

## 7. Acceptance criteria

### Phase 3

- [ ] Quit and relaunch: mute, Live/Pro, look-ahead, Tune, Banks, OSC host/port, MIDI enable/port, last file or device, TAP BPM restore
- [ ] Corrupt/missing last-used → defaults, app still opens
- [ ] Does not auto-play

### Phase 1

- [ ] Save… writes `*.ma.json` with the schema above
- [ ] Load… restores the same set
- [ ] Two shows can keep two files (club vs rehearsal)

### Phase 2

- [ ] **Show** fits without scrolling for transport + meters + scope
- [ ] **Setup** still has full Tune/Banks/Outputs + Session buttons
- [ ] Toggle does not reset knobs or stop the engine
- [ ] Last view restored on launch (via last-used)

### Shared

- [ ] README: last-used path, session file, Show vs Setup
- [ ] Append **Implemented** with which phases shipped

---

## 8. Do / Don't

**Do**

- 3 then 1 then 2
- One schema for last-used and named files
- Fail soft on missing devices/files

**Don't**

- Don’t auto-Start on launch
- Don’t store audio files inside the JSON
- Don’t require Show view to ship last-used
- Don’t block on Extract if that UI is not merged yet (field optional)

---

## Done means

User closes the app after a rehearsal, opens it next day, knobs/I/O/TAP BPM are back. They Save `friday.ma.json` for the gig. On stage they switch **Show** and only hit Start / Mute / TAP.

---

## Implemented (Programming agent — fill in)

**2026-08-11 — Phases 3, then 1, then 2 shipped**

- **Phase 3:** `~/.music_analyse/last_used.json` on quit (`WM_DELETE_WINDOW`) + 1.5 s debounce after Tune/Banks/Mode/Extract/Mute/TAP/view. Launch restores mute, Live/Pro, look-ahead, Extract, Tune, Banks, OSC, MIDI name (no port enumerate), last file or device label, TAP BPM + lock (phase fresh). Missing/corrupt → defaults, no modal, no auto-Start.
- **Phase 1:** Setup `Session: [ Save… ] [ Load… ]`. Same schema (`version: 1`, `*.ma.json`, default `show.ma.json`). Save does not overwrite last-used. Load applies live; restarts analyser only if Mode/Extract/source changed. Window title `Music Analyse — file.ma.json` after Load/Save.
- **Phase 2:** Top-right **Show | Setup**. Show is default (~560×520, no scrollbar): large Start/TAP, meters, scope, status. Setup is the full scrollable panel. One Engine; hide/show frames. Last view stored in last-used.
