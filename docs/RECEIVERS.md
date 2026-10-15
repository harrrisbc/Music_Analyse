# OSC receivers (v1)

## Addresses

| OSC address | Type | Meaning |
|-------------|------|---------|
| `/music/kick` | float32 | Kick velocity 0.0–1.0 |
| `/music/snare` | float32 | Snare velocity 0.0–1.0 |

Default UDP port: **9000** (override with `hma play --osc-port`).

Messages are sent once per locked cue when the audio playhead reaches the cue time (see `playback.lookahead_sec` in profile YAML).

## TouchDesigner

- **OSC In CHOP** → Port `9000`, active.
- Map channel names to `/music/kick` and `/music/snare`.
- Optional: **Lag** or threshold on float to drive pulse triggers.

## Unreal Engine 5

- Project Settings → Plugins → **OSC** enabled.
- Place **OSC Server** actor, listen port `9000`.
- In Blueprint, use **OSC Server Receive** events for address `/music/kick` and `/music/snare`; bind float to your VFX/audio logic.
