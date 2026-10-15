# Cue JSON schema (v1)

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Must be `"1.0"` |
| `source.audio_path` | string? | Original stereo mix |
| `source.drums_stem_path` | string? | Demucs drums stem |
| `source.duration_sec` | number? | Mix duration |
| `source.sample_rate` | integer? | Audio sample rate |
| `detection.profile` | string | YAML profile name or path |
| `detection.locked` | boolean | Must be `true` for `hma play` |
| `detection.notes` | string? | Free text |
| `cues[]` | array | Sorted by `time` recommended |
| `cues[].time` | number | Seconds from start |
| `cues[].type` | `"kick"` \| `"snare"` | Drum class |
| `cues[].velocity` | number | 0.0–1.0, sent on OSC as float |
| `cues[].bar` | integer? | Optional bar number for editors |

## OSC (live playback)

| Address | Type | Value |
|---------|------|--------|
| `/music/kick` | float | kick velocity 0–1 |
| `/music/snare` | float | snare velocity 0–1 |

Default UDP port: **9000** (configure in `profiles/*.yaml` and `hma play --osc-port`).

## MIDI export

- Kick → note **36**, snare → note **38** (GM drums)
- Velocity maps from cue `velocity` × 127
