"""Play audio and fire OSC from a locked cue sheet."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from haris_music_analyser.models import CueSheet
from haris_music_analyser.osc import OscCueSender
from haris_music_analyser.profile import load_profile


def play_with_osc(
    audio_path: Path | str,
    sheet: CueSheet,
    *,
    osc_host: str = "127.0.0.1",
    osc_port: int = 9000,
    profile: str | Path = "default",
    device: int | str | None = None,
) -> None:
    if not sheet.detection.locked:
        raise ValueError("cue sheet must be locked before playback (hma cues lock)")

    try:
        import sounddevice as sd
    except OSError as exc:
        raise OSError(
            "PortAudio is required for playback. On macOS: brew install portaudio. "
            "On Linux: install libportaudio2 / portaudio19-dev."
        ) from exc

    audio_path = Path(audio_path)
    cfg = load_profile(profile)
    pb = cfg["playback"]
    tol = float(pb["trigger_tolerance_sec"])
    lookahead = float(pb["lookahead_sec"])

    data, sr = sf.read(audio_path, dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.column_stack([data, data])

    cues = sheet.sorted_cues()
    osc = OscCueSender(osc_host, osc_port, profile=profile)
    print(f"[play] {audio_path.name} → speakers + OSC {osc.endpoint}")

    state = {"pos": 0, "running": True, "next_idx": 0}
    lock = threading.Lock()

    def callback(outdata, frames, _time_info, status):
        if status:
            print(f"[play] stream status: {status}")
        with lock:
            start = state["pos"]
            end = min(len(data), start + frames)
            chunk = data[start:end]
            if len(chunk) < frames:
                pad = np.zeros((frames - len(chunk), chunk.shape[1]), dtype=np.float32)
                chunk = np.vstack([chunk, pad])
                state["running"] = False
            outdata[:] = chunk
            t0 = start / sr
            t1 = end / sr
            _fire_cues_in_range(cues, state, t0, t1, lookahead, tol, osc)
            state["pos"] = end

    stream = sd.OutputStream(
        samplerate=sr,
        channels=2,
        callback=callback,
        blocksize=2048,
        device=device,
    )
    stream.start()
    try:
        while state["running"]:
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("[play] interrupted")
    finally:
        stream.stop()
        stream.close()
    print("[play] done")


def _fire_cues_in_range(cues, state, t0, t1, lookahead, tol, osc: OscCueSender) -> None:
    idx = state["next_idx"]
    while idx < len(cues):
        trigger_t = cues[idx].time - lookahead
        if trigger_t > t1 + tol:
            break
        if trigger_t >= t0 - tol:
            osc.send(cues[idx].type, cues[idx].velocity)
        idx += 1
    state["next_idx"] = idx
