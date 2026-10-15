"""Command-line interface for the v1 pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from haris_music_analyser import __version__
from haris_music_analyser.cues_cmd import add_cue, list_cues, load_or_raise, lock_sheet, remove_cue
from haris_music_analyser.detect import detect_cues
from haris_music_analyser.export import export_bundle
from haris_music_analyser.separate import separate_drums


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hma",
        description="Haris Music Analyser v1 — offline drums cues → OSC playback",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sep = sub.add_parser("separate", help="Demucs: extract drums stem from stereo mix")
    p_sep.add_argument("mix", type=Path, help="Stereo mix WAV/FLAC/etc.")
    p_sep.add_argument("-o", "--output", type=Path, required=True, help="Output drums.wav path")
    p_sep.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    p_sep.add_argument("--model", default="htdemucs")

    p_det = sub.add_parser("detect", help="Kick/snare onset cues from drums stem")
    p_det.add_argument("drums", type=Path)
    p_det.add_argument("-o", "--output", type=Path, required=True, help="cues.json")
    p_det.add_argument("--mix", type=Path, default=None, help="Original mix path for metadata")
    p_det.add_argument("--profile", default="default")

    p_exp = sub.add_parser("export", help="Write cues.json + cues.mid from a cue sheet")
    p_exp.add_argument("cues", type=Path)
    p_exp.add_argument("-o", "--out-dir", type=Path, required=True)
    p_exp.add_argument("--profile", default="default")

    p_cues = sub.add_parser("cues", help="Edit or lock cue JSON")
    c_sub = p_cues.add_subparsers(dest="cues_cmd", required=True)
    p_list = c_sub.add_parser("list", help="Print cues")
    p_list.add_argument("file", type=Path)
    p_lock = c_sub.add_parser("lock", help="Mark sheet locked and save")
    p_lock.add_argument("file", type=Path)
    p_lock.add_argument("-o", "--output", type=Path, default=None, help="Default: <file>.locked.json")
    p_add = c_sub.add_parser("add", help="Append one cue")
    p_add.add_argument("file", type=Path)
    p_add.add_argument("time", type=float)
    p_add.add_argument("type", choices=("kick", "snare"))
    p_add.add_argument("--velocity", type=float, default=1.0)
    p_add.add_argument("--bar", type=int, default=None)
    p_rm = c_sub.add_parser("remove", help="Remove cue by sorted index")
    p_rm.add_argument("file", type=Path)
    p_rm.add_argument("index", type=int)

    p_play = sub.add_parser("play", help="Play mix + send OSC from locked cues (Mac OK)")
    p_play.add_argument("audio", type=Path)
    p_play.add_argument("--cues", type=Path, required=True)
    p_play.add_argument("--osc-host", default="127.0.0.1")
    p_play.add_argument("--osc-port", type=int, default=9000)
    p_play.add_argument("--profile", default="default")
    p_play.add_argument("--device", default=None, help="sounddevice output device name or index")

    p_pipe = sub.add_parser("pipeline", help="separate → detect → export (Windows offline)")
    p_pipe.add_argument("mix", type=Path)
    p_pipe.add_argument("-w", "--work-dir", type=Path, required=True)
    p_pipe.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    p_pipe.add_argument("--profile", default="default")

    p_osc = sub.add_parser("osc-test", help="Send one kick + snare OSC message")
    p_osc.add_argument("--host", default="127.0.0.1")
    p_osc.add_argument("--port", type=int, default=9000)

    args = parser.parse_args(argv)

    try:
        if args.command == "separate":
            separate_drums(args.mix, args.output, device=args.device, model=args.model)
        elif args.command == "detect":
            sheet = detect_cues(args.drums, profile=args.profile, mix_path=args.mix)
            sheet.save(args.output)
            print(f"[detect] wrote {args.output}")
        elif args.command == "export":
            sheet = load_or_raise(args.cues)
            export_bundle(sheet, args.out_dir, profile=args.profile)
        elif args.command == "cues":
            _run_cues(args)
        elif args.command == "play":
            from haris_music_analyser.playback import play_with_osc

            sheet = load_or_raise(args.cues)
            if not sheet.detection.locked:
                print("Error: cues file is not locked. Run: hma cues lock <file>", file=sys.stderr)
                return 2
            play_with_osc(
                args.audio,
                sheet,
                osc_host=args.osc_host,
                osc_port=args.osc_port,
                profile=args.profile,
                device=args.device,
            )
        elif args.command == "pipeline":
            work = args.work_dir
            work.mkdir(parents=True, exist_ok=True)
            drums = work / "drums.wav"
            cues = work / "cues.json"
            separate_drums(args.mix, drums, device=args.device)
            sheet = detect_cues(drums, profile=args.profile, mix_path=args.mix)
            sheet.save(cues)
            export_bundle(sheet, work, profile=args.profile)
            print(f"[pipeline] work dir: {work.resolve()}")
            print("  Next: edit cues.json, then `hma cues lock`, then play on Mac with `hma play`")
        elif args.command == "osc-test":
            from haris_music_analyser.osc import OscCueSender

            s = OscCueSender(args.host, args.port)
            s.send("kick", 0.9)
            s.send("snare", 0.75)
            print(f"Sent test OSC → {s.endpoint}")
        else:
            parser.error(f"unknown command {args.command}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def _run_cues(args: argparse.Namespace) -> None:
    if args.cues_cmd == "list":
        sheet = load_or_raise(args.file)
        print(list_cues(sheet))
    elif args.cues_cmd == "lock":
        sheet = load_or_raise(args.file)
        lock_sheet(sheet)
        out = args.output or args.file.with_suffix(".locked.json")
        sheet.save(out)
        print(f"[cues] locked → {out}")
    elif args.cues_cmd == "add":
        sheet = load_or_raise(args.file)
        if sheet.detection.locked:
            raise ValueError("cannot add to a locked sheet; copy to a new file first")
        add_cue(sheet, args.time, args.type, velocity=args.velocity, bar=args.bar)
        sheet.save(args.file)
        print(f"[cues] added {args.type} @ {args.time}s")
    elif args.cues_cmd == "remove":
        sheet = load_or_raise(args.file)
        if sheet.detection.locked:
            raise ValueError("cannot remove from a locked sheet")
        remove_cue(sheet, args.index)
        sheet.save(args.file)
        print(f"[cues] removed index {args.index}")


if __name__ == "__main__":
    raise SystemExit(main())
