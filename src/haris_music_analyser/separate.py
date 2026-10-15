"""Demucs drums stem separation (Windows + NVIDIA optional)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def separate_drums(
    mix_path: Path | str,
    output_wav: Path | str,
    *,
    device: str = "cuda",
    model: str = "htdemucs",
    jobs: int = 1,
) -> Path:
    """
    Run Demucs two-stems (drums) and copy the drums WAV to ``output_wav``.

    Falls back to CPU if CUDA is requested but unavailable.
    """
    mix_path = Path(mix_path).resolve()
    output_wav = Path(output_wav).resolve()
    if not mix_path.is_file():
        raise FileNotFoundError(mix_path)

    work = output_wav.parent / ".demucs_tmp"
    work.mkdir(parents=True, exist_ok=True)

    dev = _resolve_device(device)
    cmd = [
        sys.executable,
        "-m",
        "demucs",
        "--two-stems",
        "drums",
        "-n",
        model,
        "-d",
        dev,
        "-j",
        str(jobs),
        "-o",
        str(work),
        str(mix_path),
    ]
    print(f"[separate] demucs device={dev} model={model}")
    subprocess.run(cmd, check=True)

    stem = work / model / mix_path.stem / "drums.wav"
    if not stem.is_file():
        # Demucs may sanitize filenames
        candidates = list((work / model).rglob("drums.wav"))
        if not candidates:
            raise FileNotFoundError(f"demucs did not produce drums.wav under {work}")
        stem = candidates[0]

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(stem, output_wav)
    shutil.rmtree(work, ignore_errors=True)
    print(f"[separate] wrote {output_wav}")
    return output_wav


def _resolve_device(requested: str) -> str:
    if requested != "cuda":
        return requested
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        print("[separate] CUDA not available — using CPU (slower)")
        return "cpu"
    except ImportError:
        print("[separate] torch not installed — demucs will fail; install PyTorch first")
        return "cpu"
