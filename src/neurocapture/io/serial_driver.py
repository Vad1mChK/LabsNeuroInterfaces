import time
import serial
from serial.tools import list_ports
from typing import Iterable
from neurocapture.core.types import Sample
from neurocapture.io.base import AcquisitionDriver


class SerialDriver(AcquisitionDriver):
    """
    PySerial driver for neurointerface devices (EEG/ECG/EMG/PPG/GSR)
    Supports both Arduino-based systems and commercial EEG kits
    """

    def __init__(
            self,
            port: str,
            baudrate: int = 115200,
            timeout: float = 1.0,
            sample_rate_hz: float = 250.0
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.fs = sample_rate_hz
        self.dt = 1.0 / self.fs if sample_rate_hz > 0 else 0
        self._running = False
        self.ser = None

    def open(self) -> None:
        """Initialize and open serial connection"""
        try:
            print([(port.device, port.description) for port in list_ports.comports()])

            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )

            # Allow time for connection to establish
            time.sleep(2)

            # Reset device buffer - some neuro interfaces need this
            if self.ser.is_open:
                self.ser.reset_input_buffer()
                # No initialization command needed for simple CSV format

            self._running = True
            print(f"Connected to {self.port} at {self.baudrate} baud")

        except serial.SerialException as e:
            raise RuntimeError(f"Failed to open serial port {self.port}: {e}")

    def iter_samples(self) -> Iterable[Sample]:
        """
        Continuously read and parse samples from serial stream
        Handles both CSV-style and binary packet formats common in neurointerfaces
        """
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Serial port not open. Call open() first.")

        buffer = b""

        while self._running:
            try:
                # Read available data
                data = self.ser.read(self.ser.in_waiting or 1)
                if data:
                    buffer += data

                    # Try to parse complete lines (CSV format)
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        sample = self._parse_line(line.strip())
                        if sample:
                            yield sample

                # Pace reading to approximate sample rate
                if self.dt > 0:
                    time.sleep(self.dt)

            except serial.SerialException as e:
                print(f"Serial read error: {e.with_traceback(None)}")
                break
            except Exception as e:
                print(f"Unexpected error: {e.with_traceback(None)}")
                break

    def _parse_line(self, line: bytes) -> Sample | None:
        """Parse a line of serial data into Sample object"""
        if not line:
            return None

        try:
            # Decode and clean the line
            decoded = line.decode('utf-8', errors='ignore').strip()

            # Skip empty lines or non-data lines
            if not decoded:
                return None

            # Split CSV format: "seconds,value"
            parts = decoded.split(',')
            if len(parts) != 2:
                return None

            timestamp_str, value_str = parts

            # Parse timestamp and value
            try:
                timestamp = float(timestamp_str)
                value = float(value_str)
            except ValueError:
                return None

            # Use the Arduino's timestamp instead of local perf_counter
            # Convert ADC value (0-1023) to more meaningful range if needed
            # value = (value / 1023.0) * 5.0  # Convert to voltage if needed

            return Sample(t=timestamp, amplitudes=[value])

        except Exception as e:
            print(f"Parse error for line '{line}': {e}")

        return None

    def close(self) -> None:
        """Close serial connection and cleanup"""
        self._running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        print("Serial connection closed")
