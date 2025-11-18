import os
import tkinter as tk
from dataclasses import dataclass
from enum import Enum

import time

from tkinter import ttk, filedialog
from typing import Optional

import ttkbootstrap as tb
from ttkbootstrap.widgets.scrolled import ScrolledText
from ttkbootstrap.dialogs import Messagebox

from neurocapture.acquire.acquire import AcquisitionController
from neurocapture.acquire.recorder import CsvRecorder
from neurocapture.core.types import SampleBatch, ProtocolKind, SignalType
from neurocapture.io.base import AcquisitionDriver
from neurocapture.io.firmata_driver import FirmataDriver
from neurocapture.io.synthetic_driver import SyntheticDriver
from neurocapture.io.serial_driver import SerialDriver
from neurocapture.viz.realtime_plot import RealTimePlot


# --- App ----------------------------------------------------------------------

class App(tb.Frame):
    def __init__(self, master: tb.Window) -> None:
        super().__init__(master)
        master.title("NeuroCapture — ttkbootstrap example")
        master.geometry("1000x600")
        self.pack(fill="both", expand=True)

        # State vars
        self.protocol_var = tk.StringVar(value=ProtocolKind.PY_SERIAL.value)
        self._last_debug_output = 0.0  # For debug timing
        self.signal_var = tk.StringVar(value=SignalType.EEG.value)
        default_port = "COM3" if os.name == "nt" else "/dev/ttyUSB0"
        self.port_var = tk.StringVar(value=default_port)
        self.baud_var = tk.IntVar(value=115200)
        self.refresh_ms = tk.IntVar(value=20)
        self.seconds_window = tk.DoubleVar(value=10.0)

        # Notebook with two tabs
        self.nb = tb.Notebook(self, bootstyle="dark")
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_recording_tab()
        self._build_analysis_tab()

        # Status bar
        self.status_var = tk.StringVar(value="Ready.")
        status = ttk.Label(self, textvariable=self.status_var, anchor="w")
        status.pack(side="bottom", fill="x", padx=10, pady=(0, 8))

        self._controller: Optional[AcquisitionController] = None
        self._recorder: Optional[CsvRecorder] = None
        self._update_job: Optional[str] = None
        self._csv_path: Optional[str] = None
        self._fs_assumed = 250.0  # used for analysis if synthetic

    # --- UI builders ----------------------------------------------------------

    def _build_recording_tab(self) -> None:
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="Recording")

        tab.columnconfigure(0, weight=0)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

        # Controls (left)
        controls = tb.Labelframe(tab, text="Controls", bootstyle="secondary")
        controls.grid(row=0, column=0, sticky="ns", padx=(0, 10), pady=4, ipadx=8, ipady=8)

        # Protocol
        ttk.Label(controls, text="Protocol").grid(row=0, column=0, sticky="w", pady=(2, 0))
        proto_cb = tb.Combobox(
            controls,
            textvariable=self.protocol_var,
            values=[k.value for k in ProtocolKind],
            state="readonly",
            width=18,
        )
        proto_cb.grid(row=1, column=0, sticky="ew", pady=2)

        # Signal
        ttk.Label(controls, text="Signal").grid(row=2, column=0, sticky="w", pady=(8, 0))
        sig_cb = tb.Combobox(
            controls,
            textvariable=self.signal_var,
            values=[k.value for k in SignalType],
            state="readonly",
            width=18,
        )
        sig_cb.grid(row=3, column=0, sticky="ew", pady=2)

        # Port
        ttk.Label(controls, text="Port").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(controls, textvariable=self.port_var, width=20).grid(row=5, column=0, sticky="ew", pady=2)

        # Baudrate
        ttk.Label(controls, text="Baudrate").grid(row=6, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(controls, textvariable=self.baud_var, width=20).grid(row=7, column=0, sticky="ew", pady=2)

        # Refresh
        ttk.Label(controls, text="Refresh (ms)").grid(row=8, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(controls, textvariable=self.refresh_ms, width=20).grid(row=9, column=0, sticky="ew", pady=2)

        ttk.Label(controls, text="Plot window (s)").grid(row=10, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(controls, textvariable=self.seconds_window, width=20).grid(row=11, column=0, sticky="ew", pady=2)

        # Buttons
        btns = ttk.Frame(controls)
        btns.grid(row=12, column=0, sticky="ew", pady=(12, 0))
        start_btn = tb.Button(btns, text="Start", bootstyle="success", command=self.on_start)
        stop_btn = tb.Button(btns, text="Stop", bootstyle="danger", command=self.on_stop)
        save_btn = tb.Button(controls, text="Save CSV…", bootstyle="secondary", command=self.on_save_csv)
        start_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))
        stop_btn.pack(side="left", expand=True, fill="x", padx=(4, 0))
        save_btn.grid(row=13, column=0, sticky="ew", pady=(8, 0))

        # Plot placeholder (right)
        plot_box = tb.Labelframe(tab, text="Signal", bootstyle="secondary")
        plot_box.grid(row=0, column=1, sticky="nsew", pady=4)
        plot_box.rowconfigure(0, weight=1)
        plot_box.columnconfigure(0, weight=1)

        self.plot = RealTimePlot(plot_box, seconds=self.seconds_window.get(), n_channels=1)
        self.plot.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

    def _build_analysis_tab(self) -> None:
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="Analysis")

        tab.rowconfigure(1, weight=1)
        tab.columnconfigure(0, weight=1)

        # Tools row
        tools = ttk.Frame(tab)
        tools.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        load_btn = tb.Button(tools, text="Load CSV…", bootstyle="info", command=self.on_load_csv)
        run_btn = tb.Button(tools, text="Run EEG Analysis", bootstyle="primary", command=self.on_run_analysis)
        load_btn.pack(side="left", padx=(0, 6))
        run_btn.pack(side="left")

        # Results area
        results_box = tb.Labelframe(tab, text="Results", bootstyle="secondary")
        results_box.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        results_box.rowconfigure(0, weight=1)
        results_box.columnconfigure(0, weight=1)

        self.results_text = ScrolledText(results_box, autohide=True, height=10)
        self.results_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

    # --- Handlers -------------------------------------------------------------

    def _build_driver(self) -> AcquisitionDriver:
        sig = SignalType(self.signal_var.get())
        match self.protocol_var.get():
            case ProtocolKind.PY_SERIAL.value:
                driver = SerialDriver(port=self.port_var.get(), baudrate=self.baud_var.get())
            case ProtocolKind.FIRMATA.value:
                driver = FirmataDriver(port=self.port_var.get())
            case _:
                driver = SyntheticDriver(signal=sig, sample_rate_hz=250.0, n_channels=1)
        self._fs_assumed = 250.0
        return driver

    def on_start(self) -> None:
        if self._controller is not None:
            return
        driver = self._build_driver()
        self._controller = AcquisitionController(driver=driver, batch_size=64)
        try:
            self._controller.start()
        except Exception as exc:
            self._controller = None
            Messagebox.show_error(str(exc), "Start error")
            return

        self.status_var.set("Running (synthetic)")
        self._schedule_update()

    def _schedule_update(self) -> None:
        self._update()
        self._update_job = self.after(self.refresh_ms.get(), self._schedule_update)

    def _drain_queue(self) -> list[SampleBatch]:
        drained: list[SampleBatch] = []
        if self._controller is None:
            return drained
        try:
            while True:
                drained.append(self._controller.queue.get_nowait())
        except Exception:
            pass
        return drained

    def _update(self) -> None:
        batches = self._drain_queue()
        if not batches:
            return

        for batch in batches:
            if not batch.samples:
                continue

            t = [s.t for s in batch.samples]
            amps = [s.amplitudes for s in batch.samples]

            # Debug output to see what timestamps we're getting
            if hasattr(self, '_last_debug_output') is False or time.time() - self._last_debug_output > 2.0:
                print(f"First timestamp: {t[0]:.6f}, Last timestamp: {t[-1]:.6f}")
                print(f"Sample count: {len(t)}, Amplitudes shape: {len(amps)}x{len(amps[0]) if amps else 0}")
                self._last_debug_output = time.time()

            try:
                self.plot.push(t, amps)
                if self._recorder is not None:
                    self._recorder.append(batch)
            except Exception as e:
                print(f"Plot update error: {e}")
                # Continue with next batch rather than crashing

    def on_stop(self) -> None:
        if self._controller is None:
            return
        if self._update_job is not None:
            self.after_cancel(self._update_job)
            self._update_job = None
        self._controller.stop()
        self._controller.join()
        self._controller = None
        if self._recorder is not None:
            self._recorder.close()
            self._recorder = None
        self.status_var.set("Stopped.")

    def on_save_csv(self) -> None:
        if self._recorder is not None:
            Messagebox.show_info("Already recording.", "CSV")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        self._csv_path = path
        self._recorder = CsvRecorder(path, n_channels=1)
        Messagebox.show_info(f"Recording to {path}", "CSV")

    def on_load_csv(self) -> None:
        self.status_var.set("Loading CSV… (demo)")
        Messagebox.ok("Would open file dialog and parse CSV here.", "Load CSV")

    def on_run_analysis(self) -> None:
        self.status_var.set("Running analysis… (demo)")
        self.results_text.delete("1.0", "end")
        self.results_text.insert(
            "end",
            "Demo analysis output:\n"
            "- Dominant EEG band: ???\n"
            "- Band powers: ???\n"
            "- Notes: Replace with real post-hoc computation.\n",
        )
        Messagebox.show_info("Analysis complete (demo).", "Analysis")


# --- Entrypoint ---------------------------------------------------------------

def main() -> None:
    root = tb.Window(themename="darkly")  # try "cyborg", "superhero", etc.
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
