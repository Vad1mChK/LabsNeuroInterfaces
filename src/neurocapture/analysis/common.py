from abc import ABC, abstractmethod
from typing import Any


class NeurointerfaceSignal(ABC):
    @abstractmethod
    def analyze(self) -> dict[str, Any]:
        pass
