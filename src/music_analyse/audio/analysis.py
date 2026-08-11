"""RawFrame + Live analyser (Filters | Stems, Live budget)."""

from __future__ import annotations

from dataclasses import dataclass

from music_analyse import config


@dataclass
class RawFrame:
    """Unconditioned features for one audio block."""

    rms: float = 0.0
    bass_energy: float = 0.0
    vocal_presence: float = 0.0
    onset_strength: float = 0.0
    bpm: float = config.BPM_DEFAULT
    kick_flux: float = 0.0
    snare_flux: float = 0.0
    hihat_flux: float = 0.0
    beat_pulse: bool = False
    kick_attack: float = 0.0
    kick_harmonicity: float = 0.0
    kick_shape: float = 0.0
    kick_beater: float = 0.0
    snare_attack: float = 0.0
    hihat_attack: float = 0.0
    kick_from_stem: bool = False

    @staticmethod
    def empty() -> RawFrame:
        return RawFrame()


from music_analyse.audio.measure import ExtractingAnalyser  # noqa: E402


class Analyser(ExtractingAnalyser):
    """Live: 22050 / hop 512. Extract mode is independent of Live|Pro."""

    def __init__(
        self,
        sample_rate: int = config.SAMPLE_RATE,
        block_size: int = config.BLOCK_SIZE,
        n_fft: int = config.LIVE_N_FFT,
        extract_mode: str = config.EXTRACT_DEFAULT,
    ) -> None:
        super().__init__(
            sample_rate=sample_rate,
            hop=block_size,
            n_fft=n_fft,
            extract_mode=extract_mode,
            hihat_band=config.FILTER_HIHAT,
            spec_frames=48,
        )
