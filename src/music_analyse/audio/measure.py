"""Extract (Filters | Stems) → measure → RawFrame. Shared by Live and Pro."""

from __future__ import annotations

import numpy as np

from music_analyse import config
from music_analyse.audio.analysis import RawFrame
from music_analyse.audio.filters import IirBand, block_unit
from music_analyse.audio.spectrum import AttackTracker, FluxTracker, OnsetPeakPicker, rms_power_unit
from music_analyse.audio.stems import HpssLiteSeparator
from music_analyse.banks import BankParams, default_banks
from music_analyse.output.addresses import BANK_IDS


class ExtractingAnalyser:
    """
    Causal IIR measure on the mix (Filters) or on Stem-lite stems.
    FFT is only used inside HPSS when Extract=Stems — not for bank/float Hz.
    """

    def __init__(
        self,
        sample_rate: int,
        hop: int,
        n_fft: int,
        extract_mode: str = config.EXTRACT_DEFAULT,
        hihat_band: tuple[float, float] = config.FILTER_HIHAT,
        spec_frames: int = 48,
    ) -> None:
        self.sample_rate = sample_rate
        self.block_size = hop
        self.hop = hop
        self.n_fft = n_fft
        self.extract_mode = "stems" if str(extract_mode).lower() == "stems" else "filters"
        self._dt = hop / sample_rate
        self._hihat_band = hihat_band
        self._stems = HpssLiteSeparator(sample_rate, hop, n_fft, spec_frames=spec_frames)
        self._mix: dict[str, IirBand] = {}
        self._drum: dict[str, IirBand] = {}
        self._bank_filters: dict[str, IirBand] = {}
        self._build_factory()
        self.set_banks(default_banks())
        self._flux = {
            "kick": FluxTracker(),
            "snare": FluxTracker(),
            "hihat": FluxTracker(),
            "beater": FluxTracker(),
        }
        self._attack = {
            "kick": AttackTracker(self._dt),
            "snare": AttackTracker(self._dt),
            "hihat": AttackTracker(self._dt),
        }
        self._onset_pick = OnsetPeakPicker()
        self._prev_onset = 0.0
        self._bank_env: dict[str, float] = {k: 0.0 for k in BANK_IDS}
        self._kick_flux_hold = 0.0
        self._ioi: list[float] = []
        self._last_onset_time = -1.0
        self._time = 0.0
        self._bpm = config.BPM_DEFAULT
        self._beat_phase = 0.0
        self._last_beat_time = -1.0

    def extra_ms(self) -> float:
        if self.extract_mode == "stems":
            return self._stems.extra_ms()
        return 0.0

    def _build_factory(self) -> None:
        sr = self.sample_rate
        hat = self._hihat_band
        specs = {
            "bass": (*config.FILTER_BASS, "band"),
            "vocal": (*config.FILTER_VOCAL, "band"),
            "onset": (*config.FILTER_ONSET, "band"),
            "kick": (*config.FILTER_KICK, "band"),
            "snare_body": (*config.FILTER_SNARE_BODY, "band"),
            "snare_click": (*config.FILTER_SNARE_CLICK, "band"),
            "hihat": (*hat, "band"),
            "mid": (*config.FILTER_MID, "band"),
        }
        for name, (lo, hi, kind) in specs.items():
            self._mix[name] = IirBand(sr, lo, hi, kind)
            self._drum[name] = IirBand(sr, lo, hi, kind)

    def set_extract_mode(self, mode: str) -> None:
        mode = "stems" if str(mode).lower() == "stems" else "filters"
        if mode == self.extract_mode:
            return
        self.extract_mode = mode
        self.reset()

    def set_banks(self, banks: list[BankParams]) -> None:
        sr = self.sample_rate
        for b in banks:
            key = b.key
            if key not in self._bank_filters:
                self._bank_filters[key] = IirBand(sr, b.lo_hz, b.hi_hz)
            else:
                self._bank_filters[key].retune(b.lo_hz, b.hi_hz)

    def reset(self) -> None:
        for bank in (*self._mix.values(), *self._drum.values(), *self._bank_filters.values()):
            bank.reset()
        self._stems.reset()
        for tr in self._flux.values():
            tr.reset()
        for tr in self._attack.values():
            tr.reset()
        self._onset_pick.reset()
        self._prev_onset = 0.0
        self._bank_env = {k: 0.0 for k in BANK_IDS}
        self._kick_flux_hold = 0.0
        self._ioi.clear()
        self._last_onset_time = -1.0
        self._time = 0.0
        self._bpm = config.BPM_DEFAULT
        self._beat_phase = 0.0
        self._last_beat_time = -1.0

    def process(self, block: np.ndarray) -> RawFrame:
        x = np.asarray(block, dtype=np.float32).reshape(-1)
        if len(x) < self.hop:
            x = np.concatenate([x, np.zeros(self.hop - len(x), dtype=np.float32)])
        else:
            x = x[: self.hop]
        self._time += self._dt

        stems_on = self.extract_mode == "stems"
        if stems_on:
            parts = self._stems.process(x)
            src_drums = parts["drums"]
            vocal_e = rms_power_unit(parts["vocals"])
            bass_e = rms_power_unit(parts["bass"])
            trig_src = self._drum
            wave = src_drums
        else:
            vocal_e = block_unit(self._mix["vocal"].process(x))
            bass_e = block_unit(self._mix["bass"].process(x))
            trig_src = self._mix
            wave = x

        rms = rms_power_unit(x)
        onset_y = trig_src["onset"].process(wave)
        onset_e = block_unit(onset_y)
        onset_flux = max(0.0, onset_e - self._prev_onset)
        if onset_flux < 0.012:
            onset_flux = 0.0
        self._prev_onset = onset_e

        kick_e = block_unit(trig_src["kick"].process(wave))
        body = block_unit(trig_src["snare_body"].process(wave))
        click = block_unit(trig_src["snare_click"].process(wave))
        snare_e = max(body, click)
        hihat_e = block_unit(trig_src["hihat"].process(wave))
        mid_e = block_unit(trig_src["mid"].process(wave))
        beater_e = click

        kick_flux = self._flux["kick"].update(kick_e)
        # 1-hop hold: IIR mid/thud ratio settles one hop after the flux peak
        kick_flux_out = max(kick_flux, self._kick_flux_hold)
        self._kick_flux_hold = kick_flux
        snare_flux = self._flux["snare"].update(snare_e)
        hihat_flux = self._flux["hihat"].update(hihat_e)
        beater_flux = self._flux["beater"].update(beater_e)
        kick_attack = self._attack["kick"].update(kick_e)
        snare_attack = self._attack["snare"].update(snare_e)
        hihat_attack = self._attack["hihat"].update(hihat_e)

        if stems_on:
            tone = float(parts.get("tone_like", 0.0))
            # Stem-side extra (not mix-FFT kick identity): harmonic stack → not a thud
            if tone >= 0.35:
                kick_flux_out *= float(max(0.0, 1.0 - tone))
            kick_harm = 0.0
            kick_shape = 1.0
        else:
            # No mix-FFT: mid vs thud is a weak piano hint (Stems is the identity fix).
            kick_harm = float(mid_e / (kick_e + mid_e + 1e-9))
            kick_shape = float(kick_e / (kick_e + mid_e + 1e-9))

        for key, filt in self._bank_filters.items():
            self._bank_env[key] = block_unit(filt.process(x))

        if self._onset_pick.push(onset_flux):
            peak_t = self._time - self._dt
            if self._last_onset_time >= 0:
                ioi = peak_t - self._last_onset_time
                if 60.0 / config.BPM_MAX <= ioi <= 60.0 / config.BPM_MIN:
                    self._ioi.append(ioi)
                    if len(self._ioi) > 24:
                        self._ioi.pop(0)
                    self._bpm = float(
                        np.clip(60.0 / float(np.median(self._ioi)), config.BPM_MIN, config.BPM_MAX)
                    )
            self._last_onset_time = peak_t

        beat_pulse = self._advance_beat(onset_flux)

        return RawFrame(
            rms=rms,
            bass_energy=bass_e,
            vocal_presence=vocal_e,
            onset_strength=onset_flux,
            bpm=float(self._bpm),
            kick_flux=float(kick_flux_out),
            snare_flux=float(snare_flux),
            hihat_flux=float(hihat_flux),
            beat_pulse=beat_pulse,
            kick_attack=float(kick_attack),
            kick_harmonicity=float(kick_harm),
            kick_shape=float(kick_shape),
            kick_beater=float(min(1.0, beater_flux)),
            snare_attack=float(snare_attack),
            hihat_attack=float(hihat_attack),
            kick_from_stem=stems_on,
        )

    def bank_energies(self) -> dict[str, float]:
        return dict(self._bank_env)

    def _advance_beat(self, flux: float) -> bool:
        beat_period = 60.0 / max(self._bpm, 1.0)
        self._beat_phase += self._dt / beat_period
        beat_pulse = False
        if self._beat_phase >= 1.0:
            self._beat_phase -= 1.0
            if self._time - self._last_beat_time > beat_period * 0.5:
                beat_pulse = True
                self._last_beat_time = self._time
        if flux > 0.02:
            phase_err = min(self._beat_phase, 1.0 - self._beat_phase)
            if phase_err < config.BEAT_PHASE_TOLERANCE and not beat_pulse:
                if self._time - self._last_beat_time > beat_period * 0.45:
                    beat_pulse = True
                    self._beat_phase = 0.0
                    self._last_beat_time = self._time
        return beat_pulse
