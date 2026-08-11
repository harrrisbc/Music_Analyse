---
status: Implemented
type: update
from: Designer agent
to: Programming agent
parent: docs/briefs/programming-agent-full.md
date: 2026-08-11
---

# Update — Windows PC support (docs + MIDI fallback)

**Why:** The app is portable Python and should run on a Windows show machine. Virtual MIDI and README were Mac-shaped. User asked for Windows setup in README (done) and a brief so code does not assume macOS.

---

## 1. Goal

Windows launch works for **UI + file/live audio + OSC**. MIDI works via **loopMIDI** (or any hardware port), not via `virtual=True` as the only path.

---

## 2. Screens / surfaces

No new screens. Outputs → MIDI dropdown must list loopMIDI / hardware names after Refresh.

**Out of scope:** ASIO control panel, installer/exe, WSL.

---

## 3. Layout

Unchanged.

---

## 4. Visual tokens

Unchanged.

---

## 5. Behavior / code rules

| Topic | Rule |
|-------|------|
| Paths | Keep `Path.home() / ".music_analyse"` and `Path.home() / "Documents"` — these are correct on Windows. Never hardcode `/Users/...`. |
| Virtual MIDI | `mido.open_output(name, virtual=True)` is **macOS/Linux**. On Windows it usually **fails**. If `virtual=True` raises, **retry as a normal output** with the same name (user created it in loopMIDI). Do not crash the app; show the MIDI error in Status and keep OSC running. |
| Enumerate | Keep subprocess Refresh probe (harmless on Windows). |
| Audio | `sounddevice` / PortAudio is the Windows backend. Do not import CoreAudio-only APIs. |
| Tk | Mousewheel already handles Windows `delta/120`. Keep that. |
| Python | Document 3.11–3.12 for Windows. Do not require 3.14. |

README already has a **Windows** setup block + loopMIDI steps. Keep it in sync if MIDI open logic changes.

---

## 6. Acceptance

- [ ] App starts on Windows with `python main.py` after `pip install -r requirements.txt`
- [ ] OSC to local TD works without MIDI
- [ ] If virtual port fails, retry non-virtual; Status explains if still failing
- [ ] last-used path works under `%USERPROFILE%\.music_analyse`
- [ ] README Windows + loopMIDI section remains accurate
- [ ] Append **Implemented** if you change MIDI open logic

---

## 7. Do / Don't

**Do** — treat OSC as the primary Windows path; MIDI is optional + loopMIDI.  
**Don't** — require a Mac virtual port for the app to start.

---

## Implemented (Designer — 2026-08-11)

- README: macOS + Windows setup, Python 3.11/3.12, loopMIDI, last-used Windows path
- MIDI map note: virtual on Mac, loopMIDI on Windows

## Implemented (Programming agent — fill in if code changes)

**2026-08-11**

- `MidiOutput._open_named`: try `mido.open_output(name, virtual=True)`, then the same name without `virtual` (loopMIDI / hardware).
- Both fail → `RuntimeError` with a loopMIDI hint. Engine still catches it as Status `MIDI: …`, disables MIDI, **does not** `_fail` the run — OSC continues.
- `MidiOutput.__init__` never raises (startup cannot die on MIDI).
- README Windows MIDI section matches this fallback.
