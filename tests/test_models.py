from pathlib import Path

from haris_music_analyser.models import Cue, CueSheet, DetectionMeta
from haris_music_analyser.profile import load_profile


def test_cue_roundtrip():
    sheet = CueSheet(
        cues=[Cue(time=1.0, type="kick", velocity=0.5, bar=1)],
        detection=DetectionMeta(profile="default", locked=False),
    )
    d = sheet.to_dict()
    back = CueSheet.from_dict(d)
    assert len(back.cues) == 1
    assert back.cues[0].type == "kick"


def test_load_default_profile():
    p = load_profile("default")
    assert p["playback"]["osc_kick_address"] == "/music/kick"


def test_example_json_loads():
    path = Path(__file__).resolve().parents[1] / "examples" / "cues.example.json"
    sheet = CueSheet.load(path)
    assert len(sheet.cues) == 4
