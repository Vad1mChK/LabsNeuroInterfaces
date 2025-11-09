from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable
from neurocapture.core.types import Sample


class AcquisitionDriver(ABC):
    @abstractmethod
    def open(self) -> None:
        ...

    @abstractmethod
    def iter_samples(self) -> Iterable[Sample]:
        ...

    @abstractmethod
    def close(self) -> None:
        ...
