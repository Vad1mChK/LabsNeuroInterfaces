import queue
import threading
from typing import Optional
from src.neurocapture.core.types import Sample, SampleBatch
from src.neurocapture.io.base import AcquisitionDriver


class AcquisitionController:
    def __init__(self, driver: AcquisitionDriver, batch_size: int = 64) -> None:
        self.driver = driver
        self.batch_size = batch_size
        self.queue: queue.Queue[SampleBatch] = queue.Queue(maxsize=64)
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._running.set()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print("Started acquisition thread")

    def stop(self) -> None:
        self._running.clear()

    def join(self) -> None:
        if self._thread is not None:
            self._thread.join()

    def _run(self) -> None:
        self.driver.open()
        batch: list[Sample] = []
        try:
            for s in self.driver.iter_samples():
                if not self._running.is_set():
                    break
                batch.append(s)
                print(s.t)
                if len(batch) >= self.batch_size:
                    self.queue.put(SampleBatch(samples=batch.copy()))
                    batch.clear()
        except Exception as e:
            print(e)
        finally:
            self.driver.close()
