#!/usr/bin/env python3
"""
VoiceMap Metrics Module — Optimized
All hot paths use vectorised NumPy; no Python-level loops over samples or windows.
"""

import numpy as np
from scipy.signal import butter, sosfilt, sosfiltfilt, lfilter
from scipy.fft import rfft, irfft
from typing import Tuple
import logging

from config import VoiceMapConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Inline midi conversion — removes librosa dependency
# ---------------------------------------------------------------------------
def _hz_to_midi(freq: np.ndarray) -> np.ndarray:
    """Vectorised Hz → MIDI (A4 = 69)."""
    return 12.0 * np.log2(np.maximum(freq, 1e-9) / 440.0) + 69.0


# ---------------------------------------------------------------------------
# Sliding-window RMS via cumsum — O(N), no Python loop
# ---------------------------------------------------------------------------
def _sliding_rms(signal: np.ndarray, window: int, hop: int) -> np.ndarray:
    """Return RMS for each hop-step window. Pure numpy, O(N)."""
    sq      = signal * signal
    cs      = np.empty(len(sq) + 1)
    cs[0]   = 0.0
    np.cumsum(sq, out=cs[1:])
    n_win   = (len(signal) - window) // hop + 1
    starts  = np.arange(n_win) * hop
    ends    = starts + window
    return np.sqrt((cs[ends] - cs[starts]) / window)


# ---------------------------------------------------------------------------
# Cycle-index → window-index lookup — O(C) numpy, no Python loop
# ---------------------------------------------------------------------------
def _assign_to_cycles(cycle_indices: np.ndarray,
                      metric_values: np.ndarray,
                      hop: int) -> np.ndarray:
    idx = np.minimum(cycle_indices // hop, len(metric_values) - 1)
    return metric_values[idx]


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------
class MetricCalculator:
    def __init__(self, config: VoiceMapConfig):
        self.config      = config
        self.sample_rate = config.sample_rate
        self.min_samples = config.min_samples
        self.max_period_samples = config.max_period_samples

        self.spl_window_size = config.spl_window_size
        self.spl_hop_size    = config.spl_hop_size

        self.cpp_fft_size   = config.cpp_fft_size
        self.cpp_ceps_size  = config.cpp_ceps_size
        self.cpp_low_bin    = config.cpp_low_bin
        self.cpp_high_bin   = config.cpp_high_bin
        self.cpp_dither_amp = config.cpp_dither_amp

        self.specbal_cutoff_low  = config.specbal_cutoff_low
        self.specbal_cutoff_high = config.specbal_cutoff_high
        self.specbal_rms_window  = config.specbal_rms_window


# ---------------------------------------------------------------------------
# SPL
# ---------------------------------------------------------------------------
class SPLCalculator(MetricCalculator):
    def calculate(self, voice: np.ndarray, cycle_triggers: np.ndarray) -> np.ndarray:
        logger.info("Calculating SPL...")
        delay       = int(0.02 * self.sample_rate)
        v_delayed   = np.concatenate([np.zeros(delay), voice[:-delay]])

        rms_windows = _sliding_rms(v_delayed, self.spl_window_size, self.spl_hop_size)
        spl_windows = np.where(rms_windows > 0,
                               20.0 * np.log10(np.maximum(rms_windows, 1e-12)),
                               -100.0)

        cycle_idx = np.where(cycle_triggers > 0.5)[0]
        out = _assign_to_cycles(cycle_idx, spl_windows, self.spl_hop_size)
        logger.info("  SPL: %d cycles  range %.1f – %.1f dB", len(out), out.min(), out.max())
        return out


# ---------------------------------------------------------------------------
# Clarity + MIDI (F0)
# ---------------------------------------------------------------------------
class ClarityCalculator(MetricCalculator):
    def calculate(self, voice: np.ndarray,
                  cycle_triggers: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        logger.info("Calculating Clarity...")
        cycle_idx = np.where(cycle_triggers > 0.5)[0]
        if len(cycle_idx) < 2:
            return np.array([]), np.array([])

        clarity_list = []
        midi_list    = []

        for i in range(len(cycle_idx) - 1):
            s, e = cycle_idx[i], cycle_idx[i + 1]
            L = e - s
            if L < self.min_samples:
                continue

            a = voice[s:e].astype(np.float64)
            b = voice[cycle_idx[i + 1]:cycle_idx[i + 1] + L
                      if i + 2 < len(cycle_idx)
                      else len(voice)]

            # Use next cycle at same length
            n_next = cycle_idx[i + 2] - cycle_idx[i + 1] if i + 2 < len(cycle_idx) else 0
            if n_next < self.min_samples:
                b = voice[e:e + L] if e + L <= len(voice) else None
            else:
                b = voice[e:e + min(L, n_next)].astype(np.float64)

            if b is None or len(b) == 0:
                continue
            n = min(len(a), len(b))
            a, b = a[:n], b[:n]

            # Normalize
            std_a, std_b = a.std(), b.std()
            if std_a < 1e-12 or std_b < 1e-12:
                continue
            a = (a - a.mean()) / std_a
            b = (b - b.mean()) / std_b

            # Cross-correlation at zero lag (faster than corrcoef)
            corr = float(np.dot(a, b)) / (n - 1) if n > 1 else 0.0
            clarity_list.append(max(0.0, corr))
            midi_list.append(float(_hz_to_midi(np.array([self.sample_rate / L]))[0]))

        clarity = np.array(clarity_list)
        midi    = np.array(midi_list)
        if len(clarity):
            logger.info("  Clarity: %d cycles  range %.3f – %.3f",
                        len(clarity), clarity.min(), clarity.max())
        return midi, clarity


# ---------------------------------------------------------------------------
# CPP — fully vectorised: batch rfft + vectorised peak prominence
# ---------------------------------------------------------------------------
class CPPCalculator(MetricCalculator):

    def calculate(self, voice: np.ndarray, cycle_triggers: np.ndarray) -> np.ndarray:
        logger.info("Calculating CPP (batch FFT)...")
        ws   = self.spl_window_size
        hop  = self.spl_hop_size
        fft_n = self.cpp_fft_size
        ceps_n = self.cpp_ceps_size
        lo, hi = self.cpp_low_bin, self.cpp_high_bin

        # --- Build all windows at once with stride tricks (zero-copy view) ---
        n_win = max((len(voice) - ws) // hop + 1, 0)
        if n_win == 0:
            cycle_idx = np.where(cycle_triggers > 0.5)[0]
            return np.zeros(len(cycle_idx))

        # Use explicit slicing to avoid large contiguous allocation for long files
        # Each window is ws samples; we take the first fft_n (or zero-pad)
        take = min(ws, fft_n)
        wins = np.lib.stride_tricks.sliding_window_view(voice, ws)[::hop, :take]
        wins = wins.astype(np.float64)

        # Add dither + Hanning window
        wins += np.random.default_rng().standard_normal(wins.shape) * self.cpp_dither_amp
        wins *= np.hanning(take)

        # Zero-pad to fft_n if needed
        if take < fft_n:
            pad = np.zeros((len(wins), fft_n - take))
            wins = np.concatenate([wins, pad], axis=1)

        # Batch real FFT → log magnitude → real cepstrum
        spec   = rfft(wins, n=fft_n, axis=1)                         # (W, fft_n//2+1)
        log_m  = np.log(np.abs(spec) + 1e-10)
        ceps   = irfft(log_m, n=fft_n, axis=1)[:, :ceps_n]          # (W, ceps_n)

        # Vectorised peak prominence for all windows
        cpp_wins = self._peak_prominence_batch(ceps, lo, hi)

        cycle_idx = np.where(cycle_triggers > 0.5)[0]
        out = _assign_to_cycles(cycle_idx, cpp_wins, hop)
        logger.info("  CPP: %d windows → %d cycles  range %.3f – %.3f",
                    n_win, len(out), out.min(), out.max())
        return out

    @staticmethod
    def _peak_prominence_batch(cepstrum: np.ndarray,
                                low_bin: int, high_bin: int) -> np.ndarray:
        """Vectorised peak prominence across all windows simultaneously."""
        region    = cepstrum[:, low_bin:high_bin + 1]                # (W, B)
        region_db = 20.0 * np.log10(np.abs(region) + 1e-10)

        B     = region_db.shape[1]
        x     = np.arange(B, dtype=np.float64)                      # (B,)
        sum_x  = x.sum()
        sum_x2 = (x * x).sum()
        sum_y  = region_db.sum(axis=1)                              # (W,)
        sum_xy = region_db.dot(x)                                   # (W,)

        denom     = B * sum_x2 - sum_x * sum_x
        slope     = (B * sum_xy - sum_x * sum_y) / denom            # (W,)
        intercept = (sum_y - slope * sum_x) / B                     # (W,)

        regression = slope[:, None] * x + intercept[:, None]        # (W, B)
        residuals  = region_db - regression
        return np.maximum(0.0, residuals.max(axis=1))               # (W,)


# ---------------------------------------------------------------------------
# SpecBal — filter applied ONCE to full signal, O(N), no Python loop
# ---------------------------------------------------------------------------
class SpecBalCalculator(MetricCalculator):

    def __init__(self, config: VoiceMapConfig):
        super().__init__(config)
        nyq = config.sample_rate / 2
        # Pre-compute SOS coefficients once
        self._sos_lo = butter(4, config.specbal_cutoff_low  / nyq, btype='low',  output='sos')
        self._sos_hi = butter(4, config.specbal_cutoff_high / nyq, btype='high', output='sos')

    def calculate(self, voice: np.ndarray, cycle_triggers: np.ndarray) -> np.ndarray:
        logger.info("Calculating SpecBal (single-pass filter)...")
        hop = self.spl_hop_size
        rms_w = self.specbal_rms_window   # 50-sample RMS window (matches SC RMS.ar(..., 50))

        # Filter entire signal at C speed — O(N)
        lo = sosfilt(self._sos_lo, voice)
        hi = sosfilt(self._sos_hi, voice)

        # Sliding RMS with cumsum — O(N)
        lo_rms = _sliding_rms(lo, rms_w, 1)                          # per-sample
        hi_rms = _sliding_rms(hi, rms_w, 1)

        lo_db = 20.0 * np.log10(np.maximum(lo_rms, 1e-12))
        hi_db = 20.0 * np.log10(np.maximum(hi_rms, 1e-12))
        sb    = np.maximum(hi_db - lo_db, -50.0)

        # Down-sample to hop grid then assign to cycles
        sb_hop    = sb[rms_w - 1::hop]                               # take one value per hop
        cycle_idx = np.where(cycle_triggers > 0.5)[0]
        out = _assign_to_cycles(cycle_idx, sb_hop, hop)

        # Clamp to reasonable range
        out = np.clip(out, -50.0, 50.0)
        logger.info("  SpecBal: %d cycles  range %.1f – %.1f dB",
                    len(out), out.min(), out.max())
        return out


# ---------------------------------------------------------------------------
# Crest — per-cycle, but inner ops are numpy (no Python arithmetic per sample)
# ---------------------------------------------------------------------------
class CrestCalculator(MetricCalculator):

    def calculate(self, voice: np.ndarray, cycle_triggers: np.ndarray) -> np.ndarray:
        logger.info("Calculating Crest...")
        delay    = int(0.02 * self.sample_rate)
        v        = np.concatenate([np.zeros(delay), voice[:-delay]])
        idx      = np.where(cycle_triggers > 0.5)[0]

        crest_list = []
        for i in range(len(idx) - 1):
            s, e = idx[i], idx[i + 1]
            if e - s < self.min_samples:
                continue
            cyc  = v[s:e]
            rms  = np.sqrt(np.mean(cyc * cyc))
            peak = np.max(np.abs(cyc))
            crest_list.append(peak / rms if rms > 1e-12 else 0.0)

        out = np.array(crest_list)
        if len(out):
            logger.info("  Crest: %d cycles  range %.3f – %.3f",
                        len(out), out.min(), out.max())
        return out


# ---------------------------------------------------------------------------
# Qcontact / dEGGmax / Icontact — per-cycle, inner ops numpy
# ---------------------------------------------------------------------------
class QcontactCalculator(MetricCalculator):

    def calculate(self, egg: np.ndarray,
                  cycle_triggers: np.ndarray
                  ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        logger.info("Calculating Qcontact / dEGGmax / Icontact...")
        idx = np.where(cycle_triggers > 0.5)[0]

        qc_list, dq_list, ic_list = [], [], []

        for i in range(len(idx) - 1):
            s, e = idx[i], idx[i + 1]
            if e - s < self.min_samples:
                continue
            cyc  = egg[s:e]
            cmax = cyc.max()
            cmin = cyc.min()
            p2p  = cmin - cmax          # negative (min < max for EGG)
            if abs(p2p) < 1e-12:
                qc_list.append(0.0); dq_list.append(0.0); ic_list.append(0.0)
                continue

            ticks    = len(cyc)
            integral = cmin / p2p                                      # Qci
            sin_term = np.sin(2.0 * np.pi / ticks) if ticks > 0 else 0.0
            denom    = p2p * (-0.5) * sin_term
            amp_sc   = 1.0 / denom if abs(denom) > 1e-12 else 0.0

            delta   = np.diff(cyc).max() if len(cyc) > 1 else 0.0
            deggmax = delta * amp_sc
            ic      = np.log10(max(deggmax, 1.0)) * integral

            qc_list.append(integral)
            dq_list.append(deggmax)
            ic_list.append(ic)

        qc = np.array(qc_list)
        dq = np.array(dq_list)
        ic = np.array(ic_list)
        if len(qc):
            logger.info("  Qcontact: %.3f – %.3f  dEGGmax: %.3f – %.3f  Icontact: %.3f – %.3f",
                        qc.min(), qc.max(), dq.min(), dq.max(), ic.min(), ic.max())
        return qc, dq, ic


# ---------------------------------------------------------------------------
# Entropy / HRF — placeholders (zeros)
# ---------------------------------------------------------------------------
class EntropyCalculator(MetricCalculator):
    def calculate(self, voice: np.ndarray, cycle_triggers: np.ndarray) -> np.ndarray:
        n = max(np.sum(cycle_triggers > 0.5) - 1, 0)
        return np.zeros(n)


class HRFCalculator(MetricCalculator):
    def calculate(self, voice: np.ndarray, cycle_triggers: np.ndarray) -> np.ndarray:
        n = max(np.sum(cycle_triggers > 0.5) - 1, 0)
        return np.zeros(n)
