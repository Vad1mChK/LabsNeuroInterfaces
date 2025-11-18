import time
from threading import Lock
from collections import deque
from typing import Iterable

import pyfirmata2

from neurocapture.core.types import Sample
from neurocapture.io.base import AcquisitionDriver


class FirmataDriver(AcquisitionDriver):
    def __init__(
            self,
            port: str,
            sample_rate_hz: float = 250.0,
            analog_pins: list[int] = None,
    ) -> None:
        self.port = port
        self.fs = sample_rate_hz
        self.analog_pins = analog_pins or [0]
        self._running = False
        self.board = None

        # Data storage for callback
        self._data_queue = deque()
        self._lock = Lock()

    def open(self) -> None:
        try:
            # Use pyfirmata2.Arduino
            self.board = pyfirmata2.Arduino(self.port)
            time.sleep(2)  # Allow connection to establish

            # Set up analog pins and callbacks
            for pin_num in self.analog_pins:
                analog_pin = self.board.analog[pin_num]
                # Register callback for this pin
                analog_pin.register_callback(self._sample_callback)
                analog_pin.enable_reporting()

            # Start sampling at the desired rate
            sampling_interval_ms = int(1000 / self.fs)
            self.board.samplingOn(sampling_interval_ms)

            self._running = True
            print(f"Connected to Firmata device on {self.port}")

        except Exception as e:
            raise RuntimeError(f"Failed to connect to Firmata device {self.port}: {e}")

    def _sample_callback(self, data):
        """Callback that pyfirmata2 invokes when new data is available."""
        # Data is a value between 0 and 1. Scale it as needed.
        scaled_value = data * 5.0  # Convert to volts (0-5V range)
        timestamp = time.perf_counter()

        with self._lock:
            self._data_queue.append((timestamp, [scaled_value]))

    def iter_samples(self) -> Iterable[Sample]:
        """Generator that yields samples from the callback queue."""
        while self._running:
            # Yield all available samples in the queue
            with self._lock:
                while self._data_queue:
                    t, amplitudes = self._data_queue.popleft()
                    yield Sample(t=t, amplitudes=amplitudes)
            # Small sleep to prevent excessive CPU usage
            time.sleep(0.001)

    def close(self) -> None:
        self._running = False
        if self.board:
            self.board.samplingOff()
            self.board.exit()