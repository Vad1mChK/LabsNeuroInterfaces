from __future__ import annotations

import math
import time
from typing import Iterable
import numpy as np
from neurocapture.core.types import Sample
from neurocapture.core.types import SignalType
from neurocapture.io.base import AcquisitionDriver


class SyntheticDriver(AcquisitionDriver):
    """
    Realtime synthetic signals for testing:
      - EEG: alpha 10 Hz + noise
      - ECG: simple PQRST-like pulse train (~1.2 Hz)
      - EMG: broadband noise bursts
      - PPG: 1.3 Hz pulsatile waveform
      - GSR: slow random walk
    """
    signal: SignalType

    def __init__(self, signal: SignalType, sample_rate_hz: float = 250.0, n_channels: int = 1) -> None:
        self.signal = signal
        self.fs = sample_rate_hz
        self.dt = 1.0 / self.fs
        self.n_channels = n_channels
        self._running = False

    def open(self) -> None:
        self._running = True

    def iter_samples(self) -> Iterable[Sample]:
        t0 = time.perf_counter()
        t = 0.0
        phase = 0.0
        gsr_level = 0.2
        rr = 0.8  # ECG period ~0.8s => ~75 bpm
        last_qrs = 0.0

        rng = np.random.default_rng(267)
        while self._running:
            now = time.perf_counter()
            t = now - t0

            match self.signal:
                case SignalType.EEG:
                    # 10 Hz alpha + pinkish noise
                    alpha = 0.8 * math.sin(2.0 * math.pi * 10.0 * t)
                    noise = 0.2 * float(rng.normal())
                    y = alpha + noise

                case SignalType.ECG:
                    # crude PQRST pattern every rr seconds
                    pos = (t - last_qrs) % rr
                    if pos < 0.02:
                        y = 1.5 * math.exp(-((pos - 0.01) ** 2) / (2 * 0.003 ** 2))  # QRS spike
                    elif pos < 0.12:
                        y = 0.2 * math.sin(math.pi * (pos - 0.02) / 0.10)  # T-wave-ish
                    else:
                        y = 0.0

                case SignalType.EMG:
                    # broadband noise with occasional bursts
                    base = 0.1 * float(rng.normal())
                    burst = 0.0
                    if int(t) % 3 == 0:
                        burst = 0.6 * float(rng.normal())
                    y = base + burst

                case SignalType.PPG:
                    # 1.3 Hz pulsatile waveform
                    y = 0.5 + 0.4 * max(0.0, math.sin(2.0 * math.pi * 1.3 * t))

                case _:
                    # GSR: slow drift with noise
                    gsr_level = max(0.0, min(1.0, gsr_level + 0.003 * float(rng.normal())))
                    y = gsr_level

            yield Sample(t=t, amplitudes=[y])

            # pace to sample rate
            time.sleep(self.dt)

    def close(self) -> None:
        self._running = False
