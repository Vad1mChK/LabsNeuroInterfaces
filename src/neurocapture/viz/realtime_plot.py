# src/neurocapture/viz/realtime_plot.py
from __future__ import annotations

from typing import Sequence
import math
import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


class RealTimePlot(ttk.Frame):
    """
    Dark realtime plot widget.

    Behavior:
      - X axis shows [0, seconds] from the start. It begins to scroll only after t > seconds.
      - Y axis limits are computed from the all-time global min/max of incoming data.
      - Internally we still drop old samples for memory, but we keep global min/max separately.
    """

    def __init__(self, master: tk.Misc, seconds: float, n_channels: int) -> None:
        super().__init__(master)
        self.seconds = seconds
        self.n_channels = n_channels

        self.fig = Figure(figsize=(6, 3), dpi=100)
        self.ax = self.fig.add_subplot(111)

        self._apply_dark_style()

        # One line per channel
        self.lines = [self.ax.plot([], [])[0] for _ in range(n_channels)]

        # Initial axes: fixed [0, seconds]; y will be set on first data
        self.ax.set_xlim(0.0, self.seconds)
        self.ax.set_ylim(-1.0, 1.0)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # Windowed storage for display
        self._t: list[float] = []
        self._y: list[list[float]] = [[] for _ in range(n_channels)]

        # Global extrema across whole session (for y-limits)
        self._global_ymin: float | None = None
        self._global_ymax: float | None = None

    def _apply_dark_style(self) -> None:
        bg = "#121212"
        fg = "#e0e0e0"
        grid = "#2a2a2a"

        self.fig.patch.set_facecolor(bg)
        self.ax.set_facecolor(bg)

        for spine in self.ax.spines.values():
            spine.set_color(fg)

        self.ax.tick_params(colors=fg)
        self.ax.xaxis.label.set_color(fg)
        self.ax.yaxis.label.set_color(fg)
        self.ax.grid(True, color=grid, linewidth=0.6, alpha=0.9)

        self.ax.set_xlabel("t, s")
        self.ax.set_ylabel("Amplitude")

    def push(self, t: Sequence[float], amps: Sequence[Sequence[float]]) -> None:
        """
        Append a batch of points.
        - t: list of timestamps (seconds since start), len = N
        - amps: list of amplitudes per sample, shape N x n_channels
        """
        if not t:
            return

        # Extend windowed buffers
        self._t.extend(t)
        for i in range(self.n_channels):
            self._y[i].extend([a[i] for a in amps])

        # Update global y-extrema from this batch (across all channels)
        # Compute batch min/max safely even if amps is ragged or empty rows
        batch_min = None
        batch_max = None
        for row in amps:
            if not row:
                continue
            vmin = min(row)
            vmax = max(row)
            batch_min = vmin if batch_min is None else min(batch_min, vmin)
            batch_max = vmax if batch_max is None else max(batch_max, vmax)

        if batch_min is not None and batch_max is not None:
            if self._global_ymin is None or batch_min < self._global_ymin:
                self._global_ymin = batch_min
            if self._global_ymax is None or batch_max > self._global_ymax:
                self._global_ymax = batch_max

        # Determine current time span and manage scrolling window
        tmax = self._t[-1]
        if tmax <= self.seconds:
            # Before window fills: show [0, seconds] and DO NOT scroll data out
            x0, x1 = 0.0, self.seconds
        else:
            # After window fills: drop old points and scroll x-limits
            tmin = tmax - self.seconds
            while self._t and self._t[0] < tmin:
                self._t.pop(0)
                for i in range(self.n_channels):
                    if self._y[i]:
                        self._y[i].pop(0)
            x0, x1 = tmin, tmax

        # Update line data
        for i in range(self.n_channels):
            self.lines[i].set_data(self._t, self._y[i])

        # X limits per rules above
        self.ax.set_xlim(x0, x1)

        # Y limits: global since start, with a small padding
        if self._global_ymin is not None and self._global_ymax is not None:
            ymin = self._global_ymin
            ymax = self._global_ymax
            if math.isclose(ymin, ymax, rel_tol=0.0, abs_tol=1e-12):
                pad = 1.0 if ymin == 0.0 else 0.1 * abs(ymin)
                self.ax.set_ylim(ymin - pad, ymax + pad)
            else:
                span = ymax - ymin
                pad = 0.05 * span
                self.ax.set_ylim(ymin - pad, ymax + pad)

        self.canvas.draw_idle()
