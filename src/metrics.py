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
# Clarity + MIDI (F0) — Tartini-style windowed autocorrelation
#
# Matches SC:  Tartini.kr(Integrator.ar(in, 0.995), n:2048, k:0, overlap:1024)
#
# For each overlapping window of size n (2048) with hop (n - overlap = 1024):
#   1. Compute normalised autocorrelation (NSDF) via FFT
#   2. Find the dominant peak in the valid lag range → F0
#   3. Clarity = normalised ACF value at that peak (0..1)
# The per-window F0/Clarity are then assigned to EGG cycle boundaries.
# ---------------------------------------------------------------------------
class ClarityCalculator(MetricCalculator):

    def __init__(self, config: VoiceMapConfig):
        super().__init__(config)
        self._fft_n  = config.clarity_fft_size          # 2048
        self._hop    = config.clarity_fft_size - config.clarity_overlap  # 1024
        self._min_lag = max(1, int(config.sample_rate / 1000))  # ~1000 Hz ceiling
        self._max_lag = int(config.sample_rate / 50)            # 50 Hz floor

    def calculate(self, voice: np.ndarray,
                  cycle_triggers: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        logger.info("Calculating Clarity (Tartini autocorrelation)...")

        n     = self._fft_n
        hop   = self._hop
        sr    = self.sample_rate

        # Leaky-integrate the voice signal, matching SC Integrator.ar(in, 0.995)
        from scipy.signal import lfilter as _lfilter
        v_integr = _lfilter([1.0], [1.0, -0.995], voice.astype(np.float64))

        # Build all windows at once (zero-copy view, then copy to allow writability)
        n_win = max((len(v_integr) - n) // hop + 1, 0)
        if n_win == 0:
            return np.array([]), np.array([])

        wins = np.lib.stride_tricks.sliding_window_view(v_integr, n)[::hop].copy()

        # Subtract mean per window
        wins -= wins.mean(axis=1, keepdims=True)

        # Linear autocorrelation via zero-padded FFT
        # Using NSDF (Normalised Square Difference Function, McLeod/Tartini):
        #   NSDF(τ) = 2·m(τ) / [Σx[i]² for i∈[0,N-τ) + Σx[i]² for i∈[τ,N)]
        # For a perfectly periodic signal NSDF = 1.0, unlike simple r(τ)/r(0)
        # which gives (N-τ)/N < 1.0 and causes systematic under-reporting of clarity.
        fft_size = 2 * n
        W_fft  = rfft(wins, n=fft_size, axis=1)
        m_full = irfft(W_fft * np.conj(W_fft), n=fft_size, axis=1)[:, :n]  # (W, n) linear ACF

        # Cumulative sum of squares for NSDF denominator — O(W·N) numpy
        sq = wins * wins                                  # (W, n)
        cs = np.zeros((len(wins), n + 1), dtype=np.float64)
        np.cumsum(sq, axis=1, out=cs[:, 1:])             # cs[:, k] = Σ_{i<k} x[i]²

        lo, hi = self._min_lag, min(self._max_lag, n - 1)
        taus   = np.arange(lo, hi + 1, dtype=int)        # (n_lags,)

        # n'(τ) = Σ_{[0,N-τ)} x² + Σ_{[τ,N)} x²
        #       = cs[:, N-τ] + (cs[:, N] - cs[:, τ])
        n_prime = cs[:, n - taus] + (cs[:, n:n+1] - cs[:, taus])  # (W, n_lags)
        nsdf    = np.where(n_prime > 1e-12,
                           2.0 * m_full[:, taus] / n_prime,
                           0.0)                          # (W, n_lags)

        peak_local = np.argmax(nsdf, axis=1)              # (W,)
        peak_lag   = peak_local + lo
        clarity_w  = nsdf[np.arange(len(wins)), peak_local]  # (W,) in (-1,1]
        f0_w       = np.where(peak_lag > 0, sr / peak_lag, 0.0)

        # Sanitize (SC: Sanitize.kr(freq.cpsmidi, 20) → clamp MIDI to ≥20)
        midi_w    = np.where(f0_w > 0, _hz_to_midi(f0_w), 20.0)
        midi_w    = np.maximum(midi_w, 20.0)
        clarity_w = np.maximum(clarity_w, 0.0)

        # Assign window values to each EGG cycle trigger
        cycle_idx = np.where(cycle_triggers > 0.5)[0]
        if len(cycle_idx) < 2:
            return np.array([]), np.array([])

        # Each cycle trigger maps to the window that covers it
        cycle_midi    = _assign_to_cycles(cycle_idx[:-1], midi_w,    hop)
        cycle_clarity = _assign_to_cycles(cycle_idx[:-1], clarity_w, hop)

        logger.info("  Clarity: %d cycles  range %.3f – %.3f",
                    len(cycle_clarity), cycle_clarity.min(), cycle_clarity.max())
        logger.info("  MIDI:    range %.1f – %.1f", cycle_midi.min(), cycle_midi.max())
        return cycle_midi, cycle_clarity


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
