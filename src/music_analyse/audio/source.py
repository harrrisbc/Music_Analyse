"""Audio sources — File or Live, one active at a time."""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from pathlib import Path
from typing import Callable

import numpy as np
import sounddevice as sd
import soundfile as sf

from music_analyse import config

BlockCallback = Callable[[np.ndarray], None]


def list_input_devices() -> list[tuple[int, str]]:
    devices: list[tuple[int, str]] = []
    try:
        for i, dev in enumerate(sd.query_devices()):
            if int(dev.get("max_input_channels", 0)) > 0:
                devices.append((i, f"{i}: {dev['name']}"))
    except Exception:
        pass
    return devices


class AudioSource(ABC):
    @abstractmethod
    def start(self, on_block: BlockCallback) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @property
    @abstractmethod
    def is_running(self) -> bool: ...


class FileSource(AudioSource):
    """Stream an audio file in blocks (optional playback through default output)."""

    def __init__(
        self,
        path: str | Path,
        sample_rate: int = config.SAMPLE_RATE,
        block_size: int = config.BLOCK_SIZE,
        play_audio: bool = True,
    ) -> None:
        self.path = Path(path)
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.play_audio = play_audio
        self._output_gain = 1.0  # 0 = muted monitor; analysis still runs
        self._gain_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False
        self._on_block: BlockCallback | None = None
        self._error: BaseException | None = None

    def set_output_gain(self, gain: float) -> None:
        with self._gain_lock:
            self._output_gain = float(max(0.0, min(1.0, gain)))

    def get_output_gain(self) -> float:
        with self._gain_lock:
            return self._output_gain

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_error(self) -> BaseException | None:
        return self._error

    def start(self, on_block: BlockCallback) -> None:
        if self._running:
            return
        if not self.path.is_file():
            raise FileNotFoundError(f"Audio file not found: {self.path}")
        self._on_block = on_block
        self._error = None
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._running = False
        self._on_block = None

    def _run(self) -> None:
        out_stream = None
        try:
            with sf.SoundFile(str(self.path), "r") as f:
                native_sr = int(f.samplerate)
                channels = int(f.channels)
                block_native = max(
                    1, int(round(self.block_size * native_sr / self.sample_rate))
                )
                if self.play_audio:
                    out_stream = sd.OutputStream(
                        samplerate=self.sample_rate,
                        channels=1,
                        dtype="float32",
                        blocksize=self.block_size,
                    )
                    out_stream.start()

                residual = np.zeros(0, dtype=np.float32)
                while not self._stop.is_set():
                    data = f.read(block_native, dtype="float32", always_2d=True)
                    if len(data) == 0:
                        break
                    if channels > 1:
                        mono = data.mean(axis=1)
                    else:
                        mono = data[:, 0]

                    if native_sr != self.sample_rate:
                        duration = len(mono) / native_sr
                        n_out = max(1, int(round(duration * self.sample_rate)))
                        x_old = np.linspace(0.0, 1.0, num=len(mono), endpoint=False)
                        x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
                        mono = np.interp(x_new, x_old, mono).astype(np.float32)

                    residual = np.concatenate([residual, mono])
                    while len(residual) >= self.block_size and not self._stop.is_set():
                        block = residual[: self.block_size].copy()
                        residual = residual[self.block_size :]
                        if self._on_block is not None:
                            self._on_block(block)
                        if out_stream is not None:
                            with self._gain_lock:
                                gain = self._output_gain
                            if gain <= 0.0:
                                out = np.zeros((self.block_size, 1), dtype=np.float32)
                            elif gain < 1.0:
                                out = (block * gain).reshape(-1, 1)
                            else:
                                out = block.reshape(-1, 1)
                            out_stream.write(out)
                        else:
                            time.sleep(self.block_size / self.sample_rate)
        except BaseException as exc:
            self._error = exc
        finally:
            if out_stream is not None:
                try:
                    out_stream.stop()
                    out_stream.close()
                except Exception:
                    pass
            self._running = False


class LiveSource(AudioSource):
    """Capture from an input device in blocks."""

    def __init__(
        self,
        device: int | str | None = None,
        sample_rate: int = config.SAMPLE_RATE,
        block_size: int = config.BLOCK_SIZE,
    ) -> None:
        self.device = device
        self.sample_rate = sample_rate
        self.block_size = block_size
        self._stream: sd.InputStream | None = None
        self._on_block: BlockCallback | None = None
        self._queue: deque[np.ndarray] = deque(maxlen=64)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False
        self._error: str | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_error(self) -> str | None:
        return self._error

    def start(self, on_block: BlockCallback) -> None:
        if self._running:
            return
        self._on_block = on_block
        self._error = None
        self._stop.clear()
        self._queue.clear()

        def _callback(indata, frames, time_info, status) -> None:  # noqa: ARG001
            if status:
                self._error = str(status)
            mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
            self._queue.append(mono.astype(np.float32, copy=False))

        self._stream = sd.InputStream(
            device=self.device,
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.block_size,
            callback=_callback,
        )
        self._stream.start()
        self._running = True
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        while not self._stop.is_set():
            if self._queue:
                block = self._queue.popleft()
                if self._on_block is not None:
                    self._on_block(block)
            else:
                time.sleep(0.001)
        self._running = False

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._on_block = None
        self._running = False
        self._queue.clear()
