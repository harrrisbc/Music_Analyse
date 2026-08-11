#!/usr/bin/env python3
"""Entry point: python main.py → native desktop window."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> None:
    parser = argparse.ArgumentParser(description="Music Analyse — audio → OSC/MIDI")
    parser.add_argument(
        "--smoke-osc",
        action="store_true",
        help="Send fake OSC bangs/floats then exit (no UI)",
    )
    args = parser.parse_args()

    if args.smoke_osc:
        from music_analyse import config
        from music_analyse.output.addresses import (
            BANK_IDS,
            FLOATS,
            OSC_FLOAT_ADDR,
            OSC_TRIGGER_ADDR,
            TRIGGERS,
        )
        from music_analyse.output.osc_out import OscOutput

        out = OscOutput(config.OSC_HOST, config.OSC_PORT, enabled=True)
        print(f"Sending smoke OSC → {config.OSC_HOST}:{config.OSC_PORT}")
        all_trigs = (*TRIGGERS, *BANK_IDS)
        idle_floats = {f: 0.0 for f in (*FLOATS, *BANK_IDS)}
        for name in all_trigs:
            out.send_frame({n: n == name for n in all_trigs}, idle_floats)
            print(f"  pulse {OSC_TRIGGER_ADDR[name]} = 1.0")
            out.send_frame({n: False for n in all_trigs}, idle_floats)
            print(f"  pulse {OSC_TRIGGER_ADDR[name]} = 0.0")
        floats = {
            "rms": 0.5,
            "bass_energy": 0.4,
            "vocal_presence": 0.3,
            "onset_strength": 0.6,
            "bpm": 120.0,
            "bank1": 0.2,
            "bank2": 0.3,
            "bank3": 0.4,
            "bank4": 0.0,
        }
        out.send_frame({n: False for n in all_trigs}, floats)
        for name, addr in OSC_FLOAT_ADDR.items():
            print(f"  float {addr} = {floats.get(name, 0.0)}")
        print("Done.")
        return

    from music_analyse.app import launch

    launch()


if __name__ == "__main__":
    main()
