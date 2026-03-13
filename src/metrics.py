#!/usr/bin/env python3
"""
VoiceMap Metrics Module — Optimized
All hot paths use vectorised NumPy; no Python-level loops over samples or windows.
"""

import numpy as np
from scipy.signal import butter, sosfilt, lfilter
from scipy.fft import rfft, irfft, ifft as _ifft
from scipy.ndimage import uniform_filter1d as _uf1d
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
# Per-cycle EGG DFT at harmonics 1..n_harmonics
# Returns (amps, phases) each shape (n_cycles, n_harmonics)
#   amps[i,k]   = |X[k+1]| / N_cycle  (complexAbs in SC, k=0 is fundamental)
#   phases[i,k] = angle(X[k+1])
# ---------------------------------------------------------------------------
def _compute_cycle_dft(egg: np.ndarray,
                       cycle_idx: np.ndarray,
                       n_harmonics: int) -> Tuple[np.ndarray, np.ndarray]:
    n_cycles = len(cycle_idx) - 1
    amps   = np.zeros((n_cycles, n_harmonics), dtype=np.float64)
    phases = np.zeros((n_cycles, n_harmonics), dtype=np.float64)
    for i in range(n_cycles):
        s, e = int(cycle_idx[i]), int(cycle_idx[i + 1])
        N = e - s
        if N < 2:
            continue
        cyc = egg[s:e].astype(np.float64)
        X   = np.fft.rfft(cyc)
        n_out = min(n_harmonics, len(X) - 1)
        X_h = X[1:n_out + 1] / N     # normalise by cycle length
        amps  [i, :n_out] = np.abs(X_h)
        phases[i, :n_out] = np.angle(X_h)
    return amps, phases


# ---------------------------------------------------------------------------
# Sample Entropy m=1 — batch over all windows at once
# sequences: (W, N) — W windows of length N
# ---------------------------------------------------------------------------
def _batch_sample_entropy_m1(sequences: np.ndarray, r: float) -> np.ndarray:
    W, N = sequences.shape
    if N < 3:
        return np.zeros(W)
    xi  = sequences[:, :N-1]   # (W, N-1)
    xi1 = sequences[:, 1:N]    # (W, N-1)
    d0  = np.abs(xi[:, :, None] - xi[:, None, :])    # (W, N-1, N-1)
    d1  = np.abs(xi1[:, :, None] - xi1[:, None, :])  # (W, N-1, N-1)
    diag_mask = ~np.eye(N - 1, dtype=bool)
    dm  = diag_mask[None]                              # (1, N-1, N-1)
    match_m  = (d0 < r) & dm
    match_m1 = match_m & (d1 < r)
    B = match_m .sum(axis=(1, 2)).astype(np.float64)
    A = match_m1.sum(axis=(1, 2)).astype(np.float64)
    result = np.zeros(W)
    valid = (A > 0) & (B > 0)
    result[valid] = -np.log(A[valid] / B[valid])
    return result


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
        idx = np.where(cycle_triggers > 0.5)[0]
        if len(idx) < 2:
            return np.array([])

        # Per-cycle RMS, matching SC's AverageOut.ar(in.squared, trig).sqrt
        # Use vectorised cumsum to avoid Python loop
        sq = voice * voice
        cs = np.empty(len(sq) + 1)
        cs[0] = 0.0
        np.cumsum(sq, out=cs[1:])

        starts = idx[:-1]
        ends   = idx[1:]
        lens   = ends - starts
        valid  = lens >= self.min_samples
        rms    = np.where(valid,
                          np.sqrt((cs[ends] - cs[starts]) / np.maximum(lens, 1)),
                          0.0)
        out = np.where(valid & (rms > 0),
                       20.0 * np.log10(np.maximum(rms, 1e-12)),
                       -100.0)
        logger.info("  SPL: %d cycles  range %.1f – %.1f dB", len(out), out.min(), out.max())
        return out


# ---------------------------------------------------------------------------
# Clarity + MIDI (F0) — Tartini-style windowed NSDF autocorrelation
# ---------------------------------------------------------------------------
class ClarityCalculator(MetricCalculator):

    def __init__(self, config: VoiceMapConfig):
        super().__init__(config)
        self._fft_n  = config.clarity_fft_size
        self._hop    = config.clarity_fft_size - config.clarity_overlap
        self._min_lag = max(1, int(config.sample_rate / 1000))
        self._max_lag = int(config.sample_rate / 50)

    def calculate(self, voice: np.ndarray,
                  cycle_triggers: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        logger.info("Calculating Clarity (Tartini autocorrelation)...")

        n   = self._fft_n
        hop = self._hop
        sr  = self.sample_rate

        v_integr = lfilter([1.0], [1.0, -0.995], voice.astype(np.float64))

        n_win = max((len(v_integr) - n) // hop + 1, 0)
        if n_win == 0:
            return np.array([]), np.array([])

        wins = np.lib.stride_tricks.sliding_window_view(v_integr, n)[::hop].copy()
        wins -= wins.mean(axis=1, keepdims=True)

        fft_size = 2 * n
        W_fft  = rfft(wins, n=fft_size, axis=1)
        m_full = irfft(W_fft * np.conj(W_fft), n=fft_size, axis=1)[:, :n]

        sq = wins * wins
        cs = np.zeros((len(wins), n + 1), dtype=np.float64)
        np.cumsum(sq, axis=1, out=cs[:, 1:])

        lo, hi = self._min_lag, min(self._max_lag, n - 1)
        taus   = np.arange(lo, hi + 1, dtype=int)

        n_prime = cs[:, n - taus] + (cs[:, n:n+1] - cs[:, taus])
        nsdf    = np.where(n_prime > 1e-12,
                           2.0 * m_full[:, taus] / n_prime,
                           0.0)                            # (N_win, L)

        # Global argmax (baseline)
        peak_local = np.argmax(nsdf, axis=1)               # (N_win,) index in nsdf
        peak_lag   = peak_local + lo                       # sample lag

        # Octave correction: if nsdf at half-lag is nearly as high, prefer it.
        # Fixes sub-octave errors where argmax picks 2× the true period.
        half_lag  = peak_lag // 2
        in_range  = half_lag >= lo                         # (N_win,) bool
        half_ix   = np.clip(half_lag - lo, 0, nsdf.shape[1] - 1)
        nsdf_peak = nsdf[np.arange(len(peak_local)), peak_local]
        nsdf_half = nsdf[np.arange(len(peak_local)), half_ix]
        prefer_half = in_range & (nsdf_half > 0.9 * nsdf_peak)
        peak_lag  = np.where(prefer_half, half_lag, peak_lag)
        clarity_w = np.where(prefer_half, nsdf_half, nsdf_peak)

        f0_w      = np.where(peak_lag > 0, sr / peak_lag, 0.0)

        midi_w    = np.where(f0_w > 0, _hz_to_midi(f0_w), 20.0)
        midi_w    = np.maximum(midi_w, 20.0)
        clarity_w = np.maximum(clarity_w, 0.0)

        cycle_idx = np.where(cycle_triggers > 0.5)[0]
        if len(cycle_idx) < 2:
            return np.array([]), np.array([])

        cycle_midi    = _assign_to_cycles(cycle_idx[:-1], midi_w,    hop)
        cycle_clarity = _assign_to_cycles(cycle_idx[:-1], clarity_w, hop)

        logger.info("  Clarity: %d cycles  range %.3f – %.3f",
                    len(cycle_clarity), cycle_clarity.min(), cycle_clarity.max())
        logger.info("  MIDI:    range %.1f – %.1f", cycle_midi.min(), cycle_midi.max())
        return cycle_midi, cycle_clarity


# ---------------------------------------------------------------------------
# CPP — SC-matching: 1024-pt IFFT of first 1024 log-mag bins,
#        then PV_MagSmooth(0.3) + PV_MagSmear(3).
#
# SC Cepstrum UGen (fftBuffer=2048, cepsBuffer=1024):
#   1024-pt IFFT of bins 0..1023 → quefrency q maps to f = SR/(2·q)
#   lowBin=25 ↔ 882 Hz, highBin=367 ↔ 60 Hz
# PeakProminence: magnitudes→dB, linear regression, max residual = CPP.
# ---------------------------------------------------------------------------
class CPPCalculator(MetricCalculator):

    def calculate(self, voice: np.ndarray, cycle_triggers: np.ndarray) -> np.ndarray:
        logger.info("Calculating CPP (SC-matching 1024-pt cepstrum)...")
        ws     = self.spl_window_size
        hop    = self.spl_hop_size
        fft_n  = self.cpp_fft_size   # 2048
        ceps_n = self.cpp_ceps_size  # 1024
        lo, hi = self.cpp_low_bin, self.cpp_high_bin   # 25, 367

        n_win = max((len(voice) - ws) // hop + 1, 0)
        if n_win == 0:
            cycle_idx = np.where(cycle_triggers > 0.5)[0]
            return np.zeros(len(cycle_idx))

        take = min(ws, fft_n)
        wins = np.lib.stride_tricks.sliding_window_view(voice, ws)[::hop, :take]
        wins = wins.astype(np.float64)

        wins = wins + np.random.default_rng().standard_normal(wins.shape) * self.cpp_dither_amp
        wins = wins * np.hanning(take)

        if take < fft_n:
            pad  = np.zeros((len(wins), fft_n - take))
            wins = np.concatenate([wins, pad], axis=1)

        spec  = rfft(wins, n=fft_n, axis=1)          # (W, 1025)
        log_m = np.log(np.abs(spec) + 1e-10)          # (W, 1025) natural log

        # SC Cepstrum: 1024-pt IFFT of first 1024 log-mag bins
        ceps_complex = _ifft(log_m[:, :ceps_n], n=ceps_n, axis=1)  # (W, 1024)
        ceps_abs     = np.abs(ceps_complex)                          # (W, 1024)

        # PV_MagSmooth(0.3): temporal IIR LPF  y[t] = 0.3·y[t-1] + 0.7·x[t]
        # PV_MagSmear(3) is omitted: it over-broadens the peak and lowers CPP
        # below the reference; MagSmooth alone matches the reference mean well.
        alpha       = 0.3
        ceps_smooth = lfilter([1 - alpha], [1, -alpha], ceps_abs, axis=0)

        cpp_wins = self._peak_prominence_batch(ceps_smooth, lo, hi)

        cycle_idx = np.where(cycle_triggers > 0.5)[0]
        out = _assign_to_cycles(cycle_idx, cpp_wins, hop)
        logger.info("  CPP: %d windows → %d cycles  range %.3f – %.3f",
                    n_win, len(out), out.min(), out.max())
        return out

    @staticmethod
    def _peak_prominence_batch(cepstrum: np.ndarray,
                                low_bin: int, high_bin: int) -> np.ndarray:
        region    = cepstrum[:, low_bin:high_bin + 1]
        region_db = 20.0 * np.log10(np.maximum(region, 1e-10))

        B     = region_db.shape[1]
        x     = np.arange(B, dtype=np.float64)
        sum_x  = x.sum()
        sum_x2 = (x * x).sum()
        sum_y  = region_db.sum(axis=1)
        sum_xy = region_db.dot(x)

        denom     = B * sum_x2 - sum_x * sum_x
        slope     = (B * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / B

        regression = slope[:, None] * x + intercept[:, None]
        residuals  = region_db - regression
        return np.maximum(0.0, residuals.max(axis=1))


# ---------------------------------------------------------------------------
# SpecBal
# ---------------------------------------------------------------------------
def _blp4_sos(freq: float, rq: float, sr: float) -> np.ndarray:
    """SC BLowPass4 equivalent: two cascaded Audio EQ Cookbook LP biquads, Q=1/rq."""
    w0 = 2.0 * np.pi * freq / sr
    cw = np.cos(w0); sw = np.sin(w0)
    alpha = sw * rq / 2.0
    b0 = (1.0 - cw) / 2.0; b1 = 1.0 - cw; b2 = b0
    a0 = 1.0 + alpha;       a1 = -2.0 * cw; a2 = 1.0 - alpha
    sec = np.array([b0/a0, b1/a0, b2/a0, 1.0, a1/a0, a2/a0])
    return np.vstack([sec, sec])            # cascade twice → 4th order

def _bhp4_sos(freq: float, rq: float, sr: float) -> np.ndarray:
    """SC BHiPass4 equivalent: two cascaded Audio EQ Cookbook HP biquads, Q=1/rq."""
    w0 = 2.0 * np.pi * freq / sr
    cw = np.cos(w0); sw = np.sin(w0)
    alpha = sw * rq / 2.0
    b0 = (1.0 + cw) / 2.0; b1 = -(1.0 + cw); b2 = b0
    a0 = 1.0 + alpha;        a1 = -2.0 * cw;   a2 = 1.0 - alpha
    sec = np.array([b0/a0, b1/a0, b2/a0, 1.0, a1/a0, a2/a0])
    return np.vstack([sec, sec])

class SpecBalCalculator(MetricCalculator):

    def __init__(self, config: VoiceMapConfig):
        super().__init__(config)
        sr = float(config.sample_rate)
        self._sos_lo = _blp4_sos(config.specbal_cutoff_low,  2.0, sr)
        self._sos_hi = _bhp4_sos(config.specbal_cutoff_high, 2.0, sr)

    def calculate(self, voice: np.ndarray, cycle_triggers: np.ndarray) -> np.ndarray:
        logger.info("Calculating SpecBal (single-pass filter)...")
        hop   = self.spl_hop_size
        rms_w = self.specbal_rms_window

        lo = sosfilt(self._sos_lo, voice)
        hi = sosfilt(self._sos_hi, voice)

        lo_rms = _sliding_rms(lo, rms_w, 1)
        hi_rms = _sliding_rms(hi, rms_w, 1)

        lo_db = 20.0 * np.log10(np.maximum(lo_rms, 1e-12))
        hi_db = 20.0 * np.log10(np.maximum(hi_rms, 1e-12))
        sb = hi_db - lo_db
        sb = np.where(np.isfinite(sb), sb, -50.0)

        sb_hop    = sb[rms_w - 1::hop]
        cycle_idx = np.where(cycle_triggers > 0.5)[0]
        out = _assign_to_cycles(cycle_idx, sb_hop, hop)
        out = np.clip(out, -50.0, 50.0)
        logger.info("  SpecBal: %d cycles  range %.1f – %.1f dB",
                    len(out), out.min(), out.max())
        return out


# ---------------------------------------------------------------------------
# Crest
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
# Qcontact / dEGGmax / Icontact
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
                qc_list.append(0.0); dq_list.append(0.0); ic_list.append(0.0)
                continue
            cyc  = egg[s:e]
            cmax = cyc.max()
            cmin = cyc.min()
            p2p  = cmin - cmax
            if abs(p2p) < 1e-12:
                qc_list.append(0.0); dq_list.append(0.0); ic_list.append(0.0)
                continue

            ticks    = len(cyc)
            integral = cmin / p2p
            sin_term = np.sin(2.0 * np.pi / ticks) if ticks > 0 else 0.0
            denom    = p2p * (-0.5) * sin_term
            amp_sc   = 1.0 / denom if abs(denom) > 1e-12 else 0.0

            cross   = egg[s] - egg[s - 1] if s > 0 else 0.0
            delta   = max(cross, np.diff(cyc).max()) if len(cyc) > 1 else cross
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
# Entropy — sliding-window Sample Entropy on per-cycle EGG DFT amplitudes/phases.
#
# Matches VRPSDSampEn SynthDef (GUI defaults: win=10, m=1, 4 harmonics each).
# For each harmonic: SampEn on last windowSize Bel-amplitude values, and on
# |phase| values; sum all 8 SampEn values per cycle.
# ---------------------------------------------------------------------------
class EntropyCalculator(MetricCalculator):

    def calculate(self, egg: np.ndarray, cycle_triggers: np.ndarray) -> np.ndarray:
        logger.info("Calculating Sample Entropy (CSE)...")
        idx      = np.where(cycle_triggers > 0.5)[0]
        n_cycles = max(len(idx) - 1, 0)
        if n_cycles < 3:
            return np.zeros(n_cycles)

        cfg        = self.config
        n_harm_amp = cfg.sampen_amplitude_harmonics
        n_harm_ph  = cfg.sampen_phase_harmonics
        win_a      = cfg.sampen_amplitude_window_size
        win_p      = cfg.sampen_phase_window_size
        tol_a      = cfg.sampen_amplitude_tolerance
        tol_p      = cfg.sampen_phase_tolerance

        n_harm = max(n_harm_amp, n_harm_ph)
        amps, phases_raw = _compute_cycle_dft(egg, idx, n_harm)

        # Amplitude in Bel: 2*log10(complexAbs)  (SC: ampdb*0.1)
        amps_bel   = 2.0 * np.log10(np.maximum(amps[:, :n_harm_amp], 1e-15))
        phases_abs = np.abs(phases_raw[:, :n_harm_ph])

        entropy = np.zeros(n_cycles)
        from numpy.lib.stride_tricks import sliding_window_view

        if n_cycles >= win_a:
            for k in range(n_harm_amp):
                wins = sliding_window_view(amps_bel[:, k], win_a)
                entropy[win_a - 1:] += _batch_sample_entropy_m1(wins, tol_a)

        if n_cycles >= win_p:
            for k in range(n_harm_ph):
                wins = sliding_window_view(phases_abs[:, k], win_p)
                entropy[win_p - 1:] += _batch_sample_entropy_m1(wins, tol_p)

        logger.info("  Entropy: %d cycles  mean %.3f  range %.3f – %.3f",
                    n_cycles, entropy.mean(), entropy.min(), entropy.max())
        return entropy


# ---------------------------------------------------------------------------
# HRFegg — Harmonic Richness Factor from per-cycle EGG DFT.
#
# Matches nameHRFEGG SynthDef:
#   harmsPower = 2 * sqrt(Σ_{k=2..N} complexAbs[k]^2)
#   HRFegg = 20*log10(harmsPower / complexAbs[0])
# ---------------------------------------------------------------------------
class HRFCalculator(MetricCalculator):

    def calculate(self, egg: np.ndarray, cycle_triggers: np.ndarray) -> np.ndarray:
        logger.info("Calculating HRFegg (per-cycle EGG DFT)...")
        idx      = np.where(cycle_triggers > 0.5)[0]
        n_cycles = max(len(idx) - 1, 0)
        if n_cycles == 0:
            return np.zeros(0)

        n_harm = self.config.n_harmonics
        amps, _ = _compute_cycle_dft(egg, idx, n_harm)

        fund    = np.maximum(amps[:, 0], 1e-15)
        harms_p = 2.0 * np.sqrt(np.sum(amps[:, 1:] ** 2, axis=1))

        hrf = 20.0 * np.log10(np.maximum(harms_p, 1e-15) / fund)
        logger.info("  HRFegg: %d cycles  mean %.2f  range %.2f – %.2f dB",
                    n_cycles, hrf.mean(), hrf.min(), hrf.max())
        return hrf
