from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class ProtocolKind(Enum):
    PY_SERIAL = "pyserial"
    FIRMATA = "firmata"
    SYNTHETIC = "synthetic"


class SignalType(Enum):
    EEG = "EEG"
    ECG = "ECG"
    EMG = "EMG"
    PPG = "PPG"
    GSR = "GSR"


@dataclass(frozen=True)
class PortSettings:
    port: str
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = "N"  # 'N', 'E', 'O'
    stopbits: float = 1.0
    timeout_s: float = 0.2


@dataclass
class Sample:
    t: float  # seconds since session start
    amplitudes: Sequence[float]  # one or more channels


@dataclass
class SampleBatch:
    samples: list[Sample]
