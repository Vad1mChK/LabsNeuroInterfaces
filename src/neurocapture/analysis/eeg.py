from __future__ import annotations

from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from scipy import signal
from scipy.integrate import trapezoid

from neurocapture.analysis.common import NeurointerfaceSignal


class EEGBandType(Enum):
    ALPHA = "alpha"
    BETA = "beta"
    DELTA = "delta"
    THETA = "theta"
    KAPPA = "kappa"
    LAMBDA = "lambd"  # name avoids the Python keyword; value is the common text label
    MU = "mu"


class EEG(NeurointerfaceSignal):
    """
    Minimal, canonical EEG analyzer for a single channel.
    Pipeline:
      df -> sort -> deduplicate (median by time) -> drop non-monotonic time ->
      interpolate to regular dt -> FFT denoise -> bandpass (0.5–40 Hz) ->
      Welch PSD -> total power and band power (by EEGBandType)
    """

    # Default band dictionary; extend/override as needed (e.g., EEG.eeg_band_ranges[EEGBandType.KAPPA] = (x, y))
    eeg_band_ranges: dict[EEGBandType, tuple[float, float]] = {
        EEGBandType.DELTA: (0.5, 4.0),
        EEGBandType.THETA: (4.0, 8.0),
        EEGBandType.ALPHA: (8.0, 13.0),
        EEGBandType.BETA: (13.0, 30.0),
        EEGBandType.MU: (8.0, 13.0),  # often overlaps alpha (sensorimotor rhythm)
        # EEGBandType.KAPPA: ( ... ),   # define explicitly if you use it
        # EEGBandType.LAMBDA: ( ... ),
    }

    # Pre-filter to confine the analysis band (Hz)
    filter_range: tuple[float, float] = (0.5, 40.0)

    # FFT denoise strength: coefficients below (median*factor) are zeroed
    fft_soft_threshold_factor: float = 3.0

    def __init__(
        self,
        df: pd.DataFrame,
        time_col: str | None,
        amplitude_col: str | None,
        band_type: EEGBandType
    ) -> None:
        self.original = df.copy()
        self.band_type = band_type

        self.time_col, self.amp_col = self._deduce_columns(df, time_col, amplitude_col)
        self.df = df[[self.time_col, self.amp_col]].rename(columns={self.time_col: "time", self.amp_col: "amp"}).copy()

        # Normalize time to float seconds if possible
        if np.issubdtype(self.df["time"].dtype, np.datetime64):
            t0 = pd.to_datetime(self.df["time"].iloc[0])
            self.df["time"] = (pd.to_datetime(self.df["time"]) - t0).dt.total_seconds()
        else:
            self.df["time"] = pd.to_numeric(self.df["time"], errors="coerce")

        self.df["amp"] = pd.to_numeric(self.df["amp"], errors="coerce")
        self.df.dropna(subset=["time", "amp"], inplace=True)

    # ----------------------------- Public API ---------------------------------

    def analyze(self) -> dict[str, Any]:
        if self.band_type not in self.eeg_band_ranges:
            raise ValueError(
                f"No range defined for band {self.band_type.value!r}. "
                f"Add one via EEG.eeg_band_ranges[EEGBandType.{self.band_type.name}] = (low_hz, high_hz)."
            )

        band_lo, band_hi = self.eeg_band_ranges[self.band_type]

        stage = {}
        df = self.df.sort_values("time", kind="mergesort").reset_index(drop=True)

        # 1) Deduplicate timestamps (median amplitude per time)
        before = len(df)
        df = (
            df.groupby("time", as_index=False, sort=True)
            .agg(amp=("amp", "median"))
            .sort_values("time", kind="mergesort")
            .reset_index(drop=True)
        )
        stage["duplicates_removed"] = before - len(df)

        # 2) Drop non-monotonic time steps (negative or zero diffs)
        before = len(df)
        if len(df) >= 2:
            diffs = df["time"].diff()
            mask = (diffs > 0) | diffs.isna()
            df = df.loc[mask].reset_index(drop=True)
        stage["nonmonotonic_removed"] = before - len(df)

        if len(df) < 8:
            return {
                "ok": False,
                "reason": "not_enough_samples_after_cleaning",
                "n": int(len(df))
            }

        # 3) Interpolate to a regular grid (linear)
        t = df["time"].to_numpy(dtype=float, copy=False)
        x = df["amp"].to_numpy(dtype=float, copy=False)
        dt = float(np.median(np.diff(t)))
        if not np.isfinite(dt) or dt <= 0:
            dt = float((t[-1] - t[0]) / max(1, len(t) - 1))

        t_reg = np.arange(t[0], t[-1] + 0.5 * dt, dt, dtype=float)
        x_reg = np.interp(t_reg, t, x)
        fs = 1.0 / dt
        stage["interpolation_dt"] = dt
        stage["fs_estimated"] = fs
        stage["n_regular"] = int(t_reg.size)

        # 4) FFT denoise (soft threshold)
        x_denoised = self._fft_denoise(x_reg, factor=self.fft_soft_threshold_factor)

        # 5) Bandpass (zero-phase)
        x_bp = self._bandpass_zero_phase(x_denoised, fs=fs, band=self.filter_range)

        if x_bp.size < 16:
            return {
                "ok": False,
                "reason": "not_enough_samples_after_filters",
                "n": int(x_bp.size)
            }

        # 6) Welch PSD
        nperseg = int(min(2048, max(256, 2 * fs)))
        f, pxx = signal.welch(x_bp, fs=fs, nperseg=nperseg)

        # 7) Total and band power
        total_power = float(trapezoid(pxx, f))
        band_mask = (f >= band_lo) & (f < band_hi)
        band_power = float(trapezoid(pxx[band_mask], f[band_mask])) if band_mask.sum() >= 2 else 0.0
        relative = float(band_power / total_power) if total_power > 0 else 0.0

        return {
            "ok": True,
            "band": self.band_type.value,
            "band_range_hz": (band_lo, band_hi),
            "fs_hz": fs,
            "duration_s": float(t_reg[-1] - t_reg[0]),
            "n_samples": int(x_bp.size),
            "total_power": total_power,
            "band_power": band_power,
            "relative_band_power": relative,
            "psd_f": f,
            "psd_pxx": pxx,
            "stages": stage,
        }

    # --------------------------- Helper methods --------------------------------

    @staticmethod
    def _deduce_columns(
        df: pd.DataFrame,
        time_col: str | None,
        amplitude_col: str | None
    ) -> tuple[str, str]:
        """
        Pick sensible defaults if columns are not provided.
        - time: one of ["time", "t", "timestamp", "sec", "seconds", "ms", "millis"]
        - amplitude: first numeric column that is not the chosen time column
        """
        if time_col is None:
            candidates = [c for c in df.columns]
            priority = ["time", "t", "timestamp", "sec", "seconds", "ms", "millis", "Время", "Время (с)"]
            lowered = {c.lower(): c for c in candidates}
            chosen_time = None
            for p in priority:
                if p in lowered:
                    chosen_time = lowered[p]
                    break
            if chosen_time is None:
                # fallback: first column that looks numeric or datetime-like
                for c in candidates:
                    if np.issubdtype(df[c].dtype, np.number) or np.issubdtype(df[c].dtype, np.datetime64):
                        chosen_time = c
                        break
            if chosen_time is None:
                raise ValueError("Could not deduce time column")
            time_col = chosen_time

        if amplitude_col is None:
            numeric_cols = [c for c in df.columns if np.issubdtype(df[c].dtype, np.number) and c != time_col]
            heuristic_order = ["amp", "amplitude", "value", "signal", "eeg", "ch1", "channel1", "A0", "A0 (В)"]
            lowered = {c.lower(): c for c in numeric_cols}
            chosen_amp = None
            for p in heuristic_order:
                if p in lowered:
                    chosen_amp = lowered[p]
                    break
            if chosen_amp is None and numeric_cols:
                chosen_amp = numeric_cols[0]
            if chosen_amp is None:
                raise ValueError("Could not deduce amplitude column")
            amplitude_col = chosen_amp

        return time_col, amplitude_col

    @staticmethod
    def _fft_denoise(x: np.ndarray, factor: float) -> np.ndarray:
        """
        Simple FFT soft-threshold denoise:
          - compute rFFT
          - zero coefficients with magnitude < median * factor
        """
        X = np.fft.rfft(x)
        thresh = np.median(np.abs(X)) * factor
        mask = np.abs(X) >= thresh
        X_d = X * mask
        y = np.fft.irfft(X_d, n=x.size)
        return y.astype(float, copy=False)

    @staticmethod
    def _bandpass_zero_phase(x: np.ndarray, fs: float, band: tuple[float, float]) -> np.ndarray:
        lo, hi = band
        nyq = 0.5 * fs
        lo_n = max(1e-6, lo / nyq)
        hi_n = min(0.999, hi / nyq)
        if hi_n <= lo_n:
            return x.copy()
        b, a, _ = signal.butter(N=4, Wn=[lo_n, hi_n], btype="bandpass")
        return signal.filtfilt(b, a, x).astype(float, copy=False)

