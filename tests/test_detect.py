import numpy as np
import soundfile as sf

from haris_music_analyser.detect import detect_cues


def test_detect_synthetic_drums(tmp_path):
    sr = 22050
    t = np.linspace(0, 1.0, sr, endpoint=False)
    y = np.zeros_like(t)
    i = int(0.1 * sr)
    y[i : i + 200] = np.sin(2 * np.pi * 80 * np.linspace(0, 0.04, 200))
    wav = tmp_path / "drums.wav"
    sf.write(wav, y, sr)
    sheet = detect_cues(wav)
    assert len(sheet.cues) >= 1
    assert sheet.cues[0].type in ("kick", "snare")
