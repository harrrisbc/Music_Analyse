---
status: Approved
target: Programming agent
engine: TouchDesigner first
handoff: docs/briefs/programming-agent-full.md
---

# Day 1 MVP — Music → OSC/MIDI bridge

Designer product summary. **Programming agent implements:** [`programming-agent-full.md`](./programming-agent-full.md).

## Goal

Local tool: analyse music (file **or** live, one at a time) → conditioned triggers + floats → TouchDesigner via **OSC** + **MIDI**.

## UI (updated)

**Python-native window only** (prefer tkinter). **No** Gradio / HTML server control panel.

## Signals

**Triggers:** beat, kick, snare, hihat, onset  
**Floats:** rms, bass_energy, vocal_presence, onset_strength (0–1 conditioned), bpm  

## Conditioning

raw → floor → adaptive norm → clamp 0–1 → attack/release smooth → out  
Triggers: threshold + refractory on conditioned energy.

## Out of scope

Unreal, multi-source, marketing UI, `/ma/raw/*` (for now).
