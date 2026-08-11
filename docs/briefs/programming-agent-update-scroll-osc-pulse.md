---
status: Implemented
type: update
from: Designer agent
to: Programming agent
parent: docs/briefs/programming-agent-full.md
date: 2026-08-11
---

# Update — Scrollable Tune + OSC trigger pulse (0/1)

## 1. Goal

Fix two blockers: Tune sliders must be reachable (window scroll), and TouchDesigner must see triggers as **pulses**, matching the in-app viewer.

## 2–4. Screens / tokens

Unchanged layout. Window must **scroll** when Tune is expanded. No new visual tokens.

## 5. Behavior

### Scroll

- Native window content is taller than the viewport when **Tune** is open
- Add a vertical scrollbar + mouse-wheel scroll over the panel
- Expanding Tune should scroll toward the sliders

### OSC triggers (contract change)

TouchDesigner **OSC In CHOP holds the last received value**. Sending `1` only on bang leaves channels stuck at 1 — viewer looked correct (timed flash) while TD stayed “always on”.

**New rule:** every analysis frame, send each `/ma/trigger/*` as:

- `1.0` on bang frame  
- `0.0` otherwise  

Addresses unchanged. MIDI note-on-bang can stay edge-only.

## 6. Acceptance

- [x] Can scroll to all Tune parameters
- [x] OSC trigger channels return to 0 between bangs in TD

## 7. Do / Don't

**Do** send explicit 0 for idle triggers.  
**Don't** rely on “message only on bang” for TD CHOPs.

## Implemented (Designer hotfix — 2026-08-11)

- `ui_tk.py`: scrollable canvas + mousewheel; Tune expand jumps toward sliders
- `osc_out.py`: send `1.0`/`0.0` every frame for all triggers

## Implemented (Programming agent — 2026-08-11)

- Verified scroll canvas + Tune expand `yview_moveto` and OSC every-frame 0/1 pulse
- `python main.py --smoke-osc` now sends bang `1.0` then idle `0.0` per trigger (TD CHOP-safe)
