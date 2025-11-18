import csv
from typing import Optional
from src.neurocapture.core.types import SampleBatch


class CsvRecorder:
    def __init__(self, path: str, n_channels: int) -> None:
        self._f = open(path, "w", newline="")
        headers = ["time"] + [f"amp{i+1}" for i in range(n_channels)]
        self._w = csv.DictWriter(self._f, fieldnames=headers)
        self._w.writeheader()
        self._closed = False

    def append(self, batch: SampleBatch) -> None:
        for s in batch.samples:
            row = {"time": f"{s.t:.6f}"}
            for i, v in enumerate(s.amplitudes):
                row[f"amp{i+1}"] = f"{v:.6f}"
            self._w.writerow(row)

    def close(self) -> None:
        if not self._closed:
            self._f.close()
            self._closed = True
