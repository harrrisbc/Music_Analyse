"""Pro analyser — same extractors as Live, Pro sample-rate / FFT budget."""

from __future__ import annotations

from music_analyse import config
from music_analyse.audio.measure import ExtractingAnalyser


class ProAnalyser(ExtractingAnalyser):
    """Pro: 44.1 kHz / hop 1024 / n_fft 4096. Look-ahead stays in the engine."""

    def __init__(
        self,
        sample_rate: int = config.PRO_SAMPLE_RATE,
        hop: int = config.PRO_HOP,
        n_fft: int = config.PRO_N_FFT,
        extract_mode: str = config.EXTRACT_DEFAULT,
    ) -> None:
        super().__init__(
            sample_rate=sample_rate,
            hop=hop,
            n_fft=n_fft,
            extract_mode=extract_mode,
            hihat_band=config.PRO_HIHAT_BAND,
            spec_frames=config.PRO_SPEC_FRAMES,
        )
