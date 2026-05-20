#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VoiceMap Metrics Module — Optimized
All hot paths use vectorised NumPy; no Python-level loops over samples or windows.
"""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.signal import butter, sosfilt, lfilter
from scipy.fft import rfft, irfft, ifft as _ifft
from typing import Tuple, Dict, Optional
import logging

from voicemap.config import VoiceMapConfig

logger = logging.getLogger(__name__)

_rng = np.random.default_rng(seed=0)

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

        self.specbal_rms_window = config.specbal_rms_window


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

        # HPF at 30 Hz matching SC VRPSDIO: HPF.ar(inMic, 30) - 2nd order Butterworth
        sos_hpf = butter(2, 30.0, btype='high', fs=sr, output='sos')
        v_hpf   = sosfilt(sos_hpf, voice.astype(np.float64))

        # Integrator matching SC Integrator.ar(in, 0.995)
        v_integr = lfilter([1.0], [1.0, -0.995], v_hpf)

        n_win = max((len(v_integr) - n) // hop + 1, 0)
        if n_win == 0:
            return np.array([]), np.array([])

        # No DC removal: SC Tartini.kr processes raw buffer without mean subtraction
        wins = sliding_window_view(v_integr, n)[::hop].copy()

        # McLeod-Wyvill NSDF: 2*m(τ)/n'(τ) — confirmed from sc3-plugins Tartini.cpp
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

        # Iterative octave correction: repeatedly prefer half-lag while it scores
        # >= 90 % of current peak (handles 2×, 4×, 8× period errors in one pass).
        N_win  = len(peak_local)
        ix_arr = np.arange(N_win)
        nsdf_L = nsdf.shape[1]
        clarity_w = nsdf[ix_arr, peak_local]
        for _ in range(4):                                 # up to 3 halvings
            half_lag = peak_lag // 2
            in_range = half_lag >= lo
            half_ix  = np.clip(half_lag - lo, 0, nsdf_L - 1)
            nsdf_half = nsdf[ix_arr, half_ix]
            prefer   = in_range & (nsdf_half > 0.85 * clarity_w)
            if not prefer.any():
                break
            peak_lag  = np.where(prefer, half_lag, peak_lag)
            clarity_w = np.where(prefer, nsdf_half, clarity_w)

        # Targeted McLeod-Wyvill fallback: for windows where corrected lag still
        # implies MIDI < 39 (lag > SR/78 ≈ 565), find the first local peak in
        # NSDF before the first negative-going zero crossing.  This handles cases
        # where the argmax sits at a genuine sub-harmonic whose half-period has
        # negative NSDF (anti-correlated), so the ratio-based octave correction
        # cannot fire.
        mw_thresh = int(sr / 78.0)            # lag corresponding to MIDI 39
        low_mask  = peak_lag > mw_thresh
        if low_mask.any():
            for i in np.where(low_mask)[0]:
                ns = nsdf[i]                  # (L,) over [lo..hi]
                # Walk through successive positive regions, picking the best peak
                # from the FIRST region that ends before the current (wrong) peak.
                limit_idx = peak_lag[i] - lo   # don't look past current argmax
                found = False
                pos_start = None
                for j in range(len(ns)):
                    if j >= limit_idx:
                        break
                    if ns[j] > 0 and pos_start is None:
                        pos_start = j
                    elif ns[j] < 0 and pos_start is not None:
                        # end of a positive region
                        sub = ns[pos_start:j]
                        if len(sub) >= 3:
                            is_pk = np.concatenate([[False],
                                (sub[1:-1] >= sub[:-2]) & (sub[1:-1] >= sub[2:]),
                                [False]])
                            pix = np.where(is_pk)[0]
                            best = pix[np.argmax(sub[pix])] if len(pix) else int(np.argmax(sub))
                            if sub[best] > 0.5:
                                peak_lag[i]  = pos_start + best + lo
                                clarity_w[i] = sub[best]
                                found = True
                                break
                        pos_start = None
                if not found and pos_start is not None and pos_start < limit_idx:
                    # last positive region extends to limit_idx
                    sub = ns[pos_start:limit_idx]
                    if len(sub) >= 3:
                        is_pk = np.concatenate([[False],
                            (sub[1:-1] >= sub[:-2]) & (sub[1:-1] >= sub[2:]),
                            [False]])
                        pix = np.where(is_pk)[0]
                        best = pix[np.argmax(sub[pix])] if len(pix) else int(np.argmax(sub))
                        if sub[best] > 0.5:
                            peak_lag[i]  = pos_start + best + lo
                            clarity_w[i] = sub[best]

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
            return np.zeros(max(len(cycle_idx) - 1, 0))

        take = min(ws, fft_n)
        wins = sliding_window_view(voice, ws)[::hop, :take]
        wins = wins.astype(np.float64)

        wins = wins + _rng.standard_normal(wins.shape) * self.cpp_dither_amp
        wins = wins * np.hanning(take)

        if take < fft_n:
            pad  = np.zeros((len(wins), fft_n - take))
            wins = np.concatenate([wins, pad], axis=1)

        spec  = rfft(wins, n=fft_n, axis=1)          # (W, 1025)
        log_m = np.log(np.abs(spec) + 1e-10)          # (W, 1025) natural log

        # SC Cepstrum: 1024-pt IFFT of first 1024 log-mag bins
        ceps_complex = _ifft(log_m[:, :ceps_n], n=ceps_n, axis=1)  # (W, 1024)
        ceps_abs     = np.abs(ceps_complex)                          # (W, 1024)

        cpp_wins = self._peak_prominence_batch(ceps_abs, lo, hi)

        cycle_idx = np.where(cycle_triggers > 0.5)[0]
        if len(cycle_idx) < 2:
            return np.zeros(0)
        win_idx   = np.clip(cycle_idx[:-1] // hop, 0, len(cpp_wins) - 1)
        out       = cpp_wins[win_idx]
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
        # rq=1.4 empirically matches SC BLowPass4/BHiPass4 rq=2 reference output
        self._sos_lo = _blp4_sos(config.specbal_cutoff_low,  1.4, sr)
        self._sos_hi = _bhp4_sos(config.specbal_cutoff_high, 1.4, sr)

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
        if len(cycle_idx) < 2:
            return np.array([])
        out = _assign_to_cycles(cycle_idx[:-1], sb_hop, hop)
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
                crest_list.append(0.0)
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

    def calculate(self, egg: np.ndarray, cycle_triggers: np.ndarray,
                  dft: Tuple[np.ndarray, np.ndarray] = None) -> np.ndarray:
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
        if dft is not None:
            amps       = dft[0][:, :n_harm]
            phases_raw = dft[1][:, :n_harm]
        else:
            amps, phases_raw = _compute_cycle_dft(egg, idx, n_harm)

        # Amplitude in Bel: 2*log10(complexAbs)  (SC: ampdb*0.1)
        amps_bel   = 2.0 * np.log10(np.maximum(amps[:, :n_harm_amp], 1e-15))
        phases_abs = np.abs(phases_raw[:, :n_harm_ph])

        entropy = np.zeros(n_cycles)

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

    def calculate(self, egg: np.ndarray, cycle_triggers: np.ndarray,
                  dft: Tuple[np.ndarray, np.ndarray] = None) -> np.ndarray:
        logger.info("Calculating HRFegg (per-cycle EGG DFT)...")
        idx      = np.where(cycle_triggers > 0.5)[0]
        n_cycles = max(len(idx) - 1, 0)
        if n_cycles == 0:
            return np.zeros(0)

        n_harm = self.config.n_harmonics
        if dft is not None:
            amps = dft[0][:, :n_harm]
        else:
            amps, _ = _compute_cycle_dft(egg, idx, n_harm)

        fund    = np.maximum(amps[:, 0], 1e-15)
        harms_p = 2.0 * np.sqrt(np.sum(amps[:, 1:] ** 2, axis=1))

        hrf = 20.0 * np.log10(np.maximum(harms_p, 1e-15) / fund)
        logger.info("  HRFegg: %d cycles  mean %.2f  range %.2f – %.2f dB",
                    n_cycles, hrf.mean(), hrf.min(), hrf.max())
        return hrf


# ───────────────────────────────────────────────────────────────────────────
# Extended: spectral moments + raw scalars (待验证).
# Frame-based STFT on the voice channel; everything assigned per cycle.
# Centroid / Bandwidth / Rolloff / Flatness / Slope / Skewness / Kurtosis
# all share one rfft pass to keep cost low.
# ───────────────────────────────────────────────────────────────────────────
class SpectralMomentsCalculator(MetricCalculator):
    """7 spectral descriptors per cycle from one STFT pass."""

    KEYS = (
        "spec_centroid", "spec_bandwidth", "spec_rolloff85",
        "spec_flatness", "spec_slope",
        "spec_skewness", "spec_kurtosis",
        "alpha_ratio", "hammarberg",
        "rms",
    )

    def __init__(self, config: VoiceMapConfig,
                 win_ms: float = 25.0, hop_ms: float = 10.0,
                 rolloff_pct: float = 0.85,
                 alpha_lo: float = 50.0, alpha_mid: float = 1000.0, alpha_hi: float = 5000.0,
                 hamm_lo: float = 0.0, hamm_mid: float = 2000.0, hamm_hi: float = 5000.0):
        super().__init__(config)
        self.win_ms, self.hop_ms = float(win_ms), float(hop_ms)
        self.rolloff_pct = float(rolloff_pct)
        self.alpha_lo, self.alpha_mid, self.alpha_hi = alpha_lo, alpha_mid, alpha_hi
        self.hamm_lo,  self.hamm_mid,  self.hamm_hi  = hamm_lo,  hamm_mid,  hamm_hi

    def calculate(self, voice: np.ndarray,
                  cycle_triggers: np.ndarray) -> Dict[str, np.ndarray]:
        logger.info("Calculating spectral moments + Alpha/Hammarberg + RMS...")
        idx = np.where(cycle_triggers > 0.5)[0]
        n_cycles = max(len(idx) - 1, 0)
        z = lambda: np.zeros(n_cycles)
        if n_cycles == 0:
            return {k: z() for k in self.KEYS}

        sr  = self.sample_rate
        win = int(self.win_ms * 0.001 * sr)
        hop = int(self.hop_ms * 0.001 * sr)
        if len(voice) < win or hop < 1:
            return {k: z() for k in self.KEYS}

        n_frames = 1 + (len(voice) - win) // hop
        starts   = np.arange(n_frames) * hop
        frames   = sliding_window_view(voice, win)[starts]    # (n_frames, win)
        hann     = np.hanning(win)
        frames_w = (frames - frames.mean(axis=1, keepdims=True)) * hann

        # FFT (single pass shared across all moments)
        nfft = 1
        while nfft < 2 * win:
            nfft *= 2
        X    = np.fft.rfft(frames_w, nfft, axis=1)
        mag  = np.abs(X)
        psd  = mag ** 2                                    # power
        freqs = np.fft.rfftfreq(nfft, 1.0 / sr)

        total_pow = psd.sum(axis=1)
        safe_pow  = np.maximum(total_pow, 1e-15)

        # Centroid
        centroid = (psd * freqs[None, :]).sum(axis=1) / safe_pow

        # Bandwidth (std around centroid)
        diff   = freqs[None, :] - centroid[:, None]
        var    = (psd * (diff ** 2)).sum(axis=1) / safe_pow
        bandwidth = np.sqrt(np.maximum(var, 0.0))

        # Rolloff: smallest freq where cumulative power exceeds rolloff_pct
        cum = np.cumsum(psd, axis=1)
        thr = self.rolloff_pct * total_pow[:, None]
        idx_roll = (cum >= thr).argmax(axis=1)             # first True
        rolloff = freqs[idx_roll]

        # Spectral flatness = geomean / mean of magnitude
        log_mag  = np.log(np.maximum(mag, 1e-15))
        flatness = np.exp(log_mag.mean(axis=1)) / np.maximum(mag.mean(axis=1), 1e-15)

        # Spectral slope: linear fit of log10(mag) vs frequency in 0-5 kHz
        slope_band = (freqs >= 0) & (freqs <= 5000)
        f_band = freqs[slope_band]
        if len(f_band) >= 2:
            log_sub = np.log10(np.maximum(mag[:, slope_band], 1e-15))
            x = f_band - f_band.mean()
            denom = (x ** 2).sum()
            slope = (log_sub * x).sum(axis=1) / max(denom, 1e-12)
        else:
            slope = np.zeros(n_frames)

        # Skewness / kurtosis of the spectral distribution (using PSD as weights)
        norm_psd = psd / safe_pow[:, None]
        skewness = (norm_psd * (diff ** 3)).sum(axis=1) / np.maximum(bandwidth ** 3, 1e-15)
        kurtosis = (norm_psd * (diff ** 4)).sum(axis=1) / np.maximum(bandwidth ** 4, 1e-15) - 3.0

        # Alpha Ratio (E_low / E_high in dB)
        m_low  = (freqs >= self.alpha_lo)  & (freqs < self.alpha_mid)
        m_high = (freqs >= self.alpha_mid) & (freqs <= self.alpha_hi)
        e_low  = psd[:, m_low ].sum(axis=1)
        e_high = psd[:, m_high].sum(axis=1)
        alpha = 10.0 * np.log10(np.maximum(e_low, 1e-15) /
                                 np.maximum(e_high, 1e-15))

        # Hammarberg Index: max(0-2k, dB) − max(2-5k, dB)
        m_hl = (freqs >= self.hamm_lo)  & (freqs < self.hamm_mid)
        m_hh = (freqs >= self.hamm_mid) & (freqs <= self.hamm_hi)
        # Use mag dB so it's a level difference
        mag_db = 20.0 * np.log10(np.maximum(mag, 1e-15))
        hamm = mag_db[:, m_hl].max(axis=1) - mag_db[:, m_hh].max(axis=1)

        # RMS per frame from time-domain windowed energy
        rms_frame = np.sqrt(np.mean(frames ** 2, axis=1))

        # Assign each cycle to its enclosing frame
        cycle_starts = idx[:-1]
        frame_idx    = np.clip(cycle_starts // hop, 0, n_frames - 1)

        return {
            "spec_centroid":   centroid[frame_idx],
            "spec_bandwidth":  bandwidth[frame_idx],
            "spec_rolloff85":  rolloff[frame_idx],
            "spec_flatness":   flatness[frame_idx],
            "spec_slope":      slope[frame_idx],
            "spec_skewness":   skewness[frame_idx],
            "spec_kurtosis":   kurtosis[frame_idx],
            "alpha_ratio":     alpha[frame_idx],
            "hammarberg":      hamm[frame_idx],
            "rms":             rms_frame[frame_idx],
        }


# ───────────────────────────────────────────────────────────────────────────
# F0 in Hz (raw frequency, complement to MIDI).
# Reuses the same NSDF result that ClarityCalculator produced; we just
# convert MIDI back to Hz. This calculator is a no-op that takes the
# pre-computed midi array from the analyzer.
# ───────────────────────────────────────────────────────────────────────────
class F0HzCalculator(MetricCalculator):
    """Convert MIDI per-cycle to Hz."""

    @staticmethod
    def midi_to_hz(midi: np.ndarray) -> np.ndarray:
        return 440.0 * np.power(2.0, (midi - 69.0) / 12.0)

    def calculate(self, midi_per_cycle: np.ndarray) -> np.ndarray:
        if len(midi_per_cycle) == 0:
            return np.zeros(0)
        valid = midi_per_cycle > 0
        out = np.zeros_like(midi_per_cycle, dtype=np.float64)
        out[valid] = self.midi_to_hz(midi_per_cycle[valid])
        if valid.any():
            v = out[valid]
            logger.info("  F0_Hz: mean=%.1f Hz  range=[%.1f, %.1f]",
                        float(v.mean()), float(v.min()), float(v.max()))
        return out


# ───────────────────────────────────────────────────────────────────────────
# MFCC 1-13 (待验证).
# Standard 13-coefficient mel-frequency cepstrum, computed per frame
# (25 ms / 10 ms hop) on the voice channel. Each cycle is assigned the
# MFCC of its enclosing frame. Self-contained — no librosa dependency.
# ───────────────────────────────────────────────────────────────────────────
def _hz_to_mel(hz):
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel):
    return 700.0 * (np.power(10.0, mel / 2595.0) - 1.0)


def _build_mel_filterbank(sr: float, n_fft: int, n_mels: int = 26,
                           f_min: float = 0.0, f_max: float = None) -> np.ndarray:
    """Triangular mel filterbank, shape (n_mels, n_fft//2+1)."""
    if f_max is None:
        f_max = sr / 2.0
    mel_pts  = np.linspace(_hz_to_mel(f_min), _hz_to_mel(f_max), n_mels + 2)
    hz_pts   = _mel_to_hz(mel_pts)
    bin_pts  = np.floor((n_fft + 1) * hz_pts / sr).astype(int)
    bin_pts  = np.clip(bin_pts, 0, n_fft // 2)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float64)
    for m in range(n_mels):
        l, c, r = bin_pts[m], bin_pts[m + 1], bin_pts[m + 2]
        if c > l:
            fb[m, l:c] = (np.arange(l, c) - l) / max(c - l, 1)
        if r > c:
            fb[m, c:r] = (r - np.arange(c, r)) / max(r - c, 1)
    return fb


class MFCCCalculator(MetricCalculator):
    """13 MFCC coefficients per cycle (待验证)."""

    KEYS = tuple(f"mfcc{i}" for i in range(1, 14))

    def __init__(self, config: VoiceMapConfig,
                 win_ms: float = 25.0, hop_ms: float = 10.0,
                 n_mels: int = 26, n_mfcc: int = 13,
                 f_min: float = 0.0, f_max: Optional[float] = None):
        super().__init__(config)
        self.win_ms, self.hop_ms = float(win_ms), float(hop_ms)
        self.n_mels = int(n_mels)
        self.n_mfcc = int(n_mfcc)
        self.f_min  = float(f_min)
        self.f_max  = f_max if f_max is not None else config.sample_rate / 2.0

    def calculate(self, voice: np.ndarray,
                  cycle_triggers: np.ndarray) -> Dict[str, np.ndarray]:
        logger.info("Calculating MFCC 1-%d (n_mels=%d)...",
                    self.n_mfcc, self.n_mels)
        idx = np.where(cycle_triggers > 0.5)[0]
        n_cycles = max(len(idx) - 1, 0)
        z = lambda: np.zeros(n_cycles)
        if n_cycles == 0:
            return {k: z() for k in self.KEYS}

        sr  = self.sample_rate
        win = int(self.win_ms * 0.001 * sr)
        hop = int(self.hop_ms * 0.001 * sr)
        if len(voice) < win or hop < 1:
            return {k: z() for k in self.KEYS}

        # Pre-emphasis (standard for MFCC)
        v_pe = np.empty_like(voice)
        v_pe[0]  = voice[0]
        v_pe[1:] = voice[1:] - 0.97 * voice[:-1]

        n_frames = 1 + (len(v_pe) - win) // hop
        starts   = np.arange(n_frames) * hop
        frames   = sliding_window_view(v_pe, win)[starts]
        frames_w = (frames - frames.mean(axis=1, keepdims=True)) * np.hamming(win)

        nfft = 1
        while nfft < 2 * win:
            nfft *= 2
        X    = np.fft.rfft(frames_w, nfft, axis=1)
        psd  = (np.abs(X)) ** 2

        # Mel filterbank → log → DCT-II truncated to n_mfcc
        fb       = _build_mel_filterbank(sr, nfft, self.n_mels,
                                          self.f_min, self.f_max)
        mel_pow  = psd @ fb.T                                # (n_frames, n_mels)
        log_mel  = np.log(np.maximum(mel_pow, 1e-15))

        # DCT-II type, orthogonal-norm
        from scipy.fft import dct as _dct
        mfcc = _dct(log_mel, type=2, axis=1, norm="ortho")[:, :self.n_mfcc]

        # Assign per cycle
        cycle_starts = idx[:-1]
        frame_idx    = np.clip(cycle_starts // hop, 0, n_frames - 1)

        out = {f"mfcc{i+1}": mfcc[frame_idx, i] for i in range(self.n_mfcc)}
        logger.info("  MFCC1: mean=%.2f  MFCC13: mean=%.2f",
                    float(out["mfcc1"].mean()), float(out["mfcc13"].mean()))
        return out


# ---------------------------------------------------------------------------
# P3: Open Quotient / Speed Quotient / Contact Index Quotient.
#
# Three glottal-timing descriptors derived from within-cycle EGG events.
# FonaDyn's existing Qcontact uses an SC-specific integral formula; these
# use the classical Howard / Baken derivative-peak definitions which are
# what most EGG papers cite.
#
# Within each cycle [t0 = GCI_i, t1 = GCI_{i+1}]:
#   GOI (opening instant)       = argmin(dEGG)  within (t0, t1)
#   peak (max open, min EGG)    = argmin(EGG)   within (t0, t1)
#   T_closed  = GOI - t0         (fully contacted phase)
#   T_open    = t1  - GOI        (any contact loss)
#   T_opening = peak - GOI       (sub-phase 1 of the open phase)
#   T_closing = t1   - peak      (sub-phase 2 of the open phase)
#
# OQ  = T_open    / T
# SPQ = T_opening / T_closing        (Baken: "opening vs closing branch")
# CIQ = (T_closing - T_opening) / T_open    (Howard asymmetry index)
# Cycles whose sub-phase durations are degenerate (non-positive) fall to 0
# so bad segments don't wreck per-cell means.
# ---------------------------------------------------------------------------
class OpenQuotientCalculator(MetricCalculator):
    """Per-cycle OQ, SPQ, CIQ (all EGG-derivative based)."""

    KEYS = ("oq", "spq", "ciq")

    def calculate(self, egg: np.ndarray,
                  cycle_triggers: np.ndarray) -> Dict[str, np.ndarray]:
        logger.info("Calculating OQ / SPQ / CIQ (EGG timing)...")
        idx = np.where(cycle_triggers > 0.5)[0]
        n = max(len(idx) - 1, 0)
        if n == 0:
            return {k: np.zeros(0) for k in self.KEYS}

        T = np.diff(idx).astype(np.float64)              # cycle length
        t_goi   = np.zeros(n, dtype=np.float64)          # within-cycle offset
        t_peak  = np.zeros(n, dtype=np.float64)

        # Per-cycle argmin on dEGG and EGG. The Python loop is ~150 ms for
        # 12k cycles — less than the downstream K-means, not worth the
        # complexity of a jagged-array vectorisation.
        for i in range(n):
            s, e = idx[i], idx[i + 1]
            if e - s < 4:
                continue
            cyc  = egg[s:e]
            dcyc = np.diff(cyc)
            t_goi[i]  = float(np.argmin(dcyc))
            t_peak[i] = float(np.argmin(cyc))

        # Quotients
        oq  = np.zeros(n)
        spq = np.zeros(n)
        ciq = np.zeros(n)

        good_T = T > 0
        # OQ = T_open / T = (T - t_goi) / T ; clip to [0, 1]
        oq[good_T] = np.clip((T[good_T] - t_goi[good_T]) / T[good_T], 0.0, 1.0)

        t_opening = t_peak - t_goi        # GOI → peak (open_phase sub-1)
        t_closing = T      - t_peak       # peak → next GCI  (open_phase sub-2)

        # SPQ: both sub-phases must be positive; clip to a sane 0.1–10 range
        valid = good_T & (t_opening > 0) & (t_closing > 0)
        spq[valid] = np.clip(t_opening[valid] / t_closing[valid], 0.1, 10.0)

        # CIQ: T_open must be positive (same as OQ)
        t_open = T - t_goi
        valid_ciq = good_T & (t_open > 0)
        ciq[valid_ciq] = np.clip(
            (t_closing[valid_ciq] - t_opening[valid_ciq]) / t_open[valid_ciq],
            -1.0, 1.0)

        logger.info("  OQ:  mean=%.3f  range=[%.3f, %.3f]",
                    float(oq[oq > 0].mean() if (oq > 0).any() else 0.0),
                    float(oq.min()), float(oq.max()))
        logger.info("  SPQ: mean=%.3f  range=[%.3f, %.3f]",
                    float(spq[spq > 0].mean() if (spq > 0).any() else 0.0),
                    float(spq.min()), float(spq.max()))
        logger.info("  CIQ: mean=%.3f  range=[%.3f, %.3f]",
                    float(ciq.mean()),
                    float(ciq.min()), float(ciq.max()))

        return {"oq": oq, "spq": spq, "ciq": ciq}


# ---------------------------------------------------------------------------
# P2: Vibrato rate + extent per cycle.
#
# Peking-opera singing technique is characterised by a prominent 5-7 Hz
# pitch modulation; rate and extent are the standard quantitative handles.
#
# Algorithm:
#   • Take the per-cycle MIDI (semitone) series p[i].
#   • Sliding window of W cycles (default 40 ≈ 0.4 s @ 100 Hz pitch rate).
#   • Detrend (subtract window mean), Hann-window, FFT.
#   • For each window the cycle clock runs at avg_rate = W / Σ T[i..i+W];
#     FFT bin k maps to freq_k = k · avg_rate / W. Mask to the 4–8 Hz
#     vibrato band per window.
#   • Rate  = freq at max magnitude in the band (Hz).
#   • Extent = 800 · |X[k_peak]| / W  cents peak-to-peak (Hann coherent
#     gain factored in: amplitude_semitones = 4·mag/W → pk-pk cents = ×200).
#   • Peaks below 2× median magnitude in the band are gated to 0
#     (no clear vibrato → output 0, not spurious noise freq).
#   • Each cycle is assigned to the window it's centred in.
# ---------------------------------------------------------------------------
class VibratoCalculator(MetricCalculator):
    """Sliding-window FFT of the per-cycle MIDI series → rate (Hz) + extent (cents)."""

    def __init__(self, config: VoiceMapConfig,
                 window_cycles: int = 40,
                 vib_f_min: float = 4.0, vib_f_max: float = 8.0,
                 min_snr: float = 2.0):
        super().__init__(config)
        self.window_cycles = int(window_cycles)
        self.vib_f_min = float(vib_f_min)
        self.vib_f_max = float(vib_f_max)
        self.min_snr = float(min_snr)

    def calculate(self, midi_per_cycle: np.ndarray,
                  cycle_idx: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        logger.info("Calculating vibrato (rate + extent)...")
        n = len(midi_per_cycle)
        W = self.window_cycles
        zeros = np.zeros(n)

        if n < W + 2 or len(cycle_idx) < n + 1:
            return zeros.copy(), zeros.copy()

        sr = float(self.sample_rate)
        T = np.diff(cycle_idx[:n + 1]).astype(np.float64) / sr      # (n,)

        # Sliding windows over midi + T
        midi_wins = sliding_window_view(midi_per_cycle, W)           # (n-W+1, W)
        T_wins    = sliding_window_view(T, W)                        # (n-W+1, W)
        n_wins    = midi_wins.shape[0]

        # Detrend + Hann, FFT
        midi_d = midi_wins - midi_wins.mean(axis=1, keepdims=True)
        hann   = np.hanning(W)
        X      = np.fft.rfft(midi_d * hann, axis=1)
        mag    = np.abs(X)                                           # (n_wins, W//2+1)

        # Per-window cycle rate (cycles/s ≈ pitch frequency average)
        cycle_rate = W / T_wins.sum(axis=1)                          # (n_wins,)
        # FFT bin frequencies per window
        k = np.arange(mag.shape[1])
        freqs = k[None, :] * cycle_rate[:, None] / W                  # (n_wins, n_bins)

        # Mask to vibrato band (per-window since freqs vary)
        band = (freqs >= self.vib_f_min) & (freqs <= self.vib_f_max)
        has_band = band.any(axis=1)

        # Peak magnitude and freq in band
        mag_in_band = np.where(band, mag, -np.inf)
        peak_bin = mag_in_band.argmax(axis=1)
        peak_mag = mag[np.arange(n_wins), peak_bin]
        peak_freq = freqs[np.arange(n_wins), peak_bin]

        # SNR gate — peak must be > min_snr × median of full-spectrum mag.
        # Windows without vibrato (pure tone or random drift) get 0.
        noise_floor = np.median(mag, axis=1)
        valid = has_band & (peak_mag > self.min_snr * np.maximum(noise_floor, 1e-9))

        rate_win   = np.where(valid, peak_freq, 0.0)
        extent_win = np.where(valid, 800.0 * peak_mag / W, 0.0)   # cents pk-pk

        # Sanity clip: real vibrato is < ~400 cents pk-pk. Values above that
        # almost always come from pitch-tracking glitches (octave jumps,
        # subharmonic snaps) producing huge FFT peaks. Zero out both rate and
        # extent so those cycles don't skew the per-cell mean.
        bad = extent_win > 400.0
        rate_win[bad]   = 0.0
        extent_win[bad] = 0.0

        # Assign each cycle to its centred window; pad edges with nearest
        half = W // 2
        rate = np.zeros(n)
        extent = np.zeros(n)
        rate[half:half + n_wins]   = rate_win
        extent[half:half + n_wins] = extent_win
        if n_wins:
            rate[:half]             = rate_win[0]
            extent[:half]           = extent_win[0]
            rate[half + n_wins:]    = rate_win[-1]
            extent[half + n_wins:]  = extent_win[-1]

        good = rate > 0
        if good.any():
            logger.info("  Vibrato: rate mean=%.2f Hz  extent mean=%.1f cents  (%.0f%% of cycles)",
                        float(rate[good].mean()),
                        float(extent[good].mean()),
                        100.0 * good.mean())
        return rate, extent


# ---------------------------------------------------------------------------
# P2: Formants F1/F2/F3 + Singer's Formant Energy (SFE).
#
# LPC-based formant estimation on 25 ms frames (Hamming windowed, with
# α=0.97 pre-emphasis for flat-ish spectral envelope). LPC order defaults
# to 2 + 2·Fs/1000 (Praat recipe) — ~22 at 44.1 kHz, enough for 5–6
# formants in the voiced band. We take the batch autocorrelation →
# batched Levinson-Durbin via np.linalg.solve → LPC spectrum magnitude,
# then scipy find_peaks in the 90–3500 Hz band. First three peaks ascending
# become F1/F2/F3.
#
# Singer's Formant Energy (SFE): ratio of spectral power in 2.8–3.4 kHz to
# total power, in dB. Classical / trained singers show –7…–13 dB; untrained
# speakers usually < –13 dB.
# ---------------------------------------------------------------------------
# ───────────────────────────────────────────────────────────────────────────
# Praat-style formant extraction — reimplements "Sound: To Formant (burg)":
#   resample → pre-emphasis → Gaussian window → Burg LPC → polynomial roots.
# F1/F2/F3 and B1/B2/B3 then come from pole angles / radii, exactly as Praat
# does, instead of the old LPC-spectrum peak-picking (which ran 20-25 % off
# Praat). Both FormantCalculator and FormantExtrasCalculator share this.
# ───────────────────────────────────────────────────────────────────────────
def _burg_lpc_batch(frames: np.ndarray, order: int) -> np.ndarray:
    """Batched Burg-method LPC.

    frames : (M, N) real analysis frames (already windowed).
    Returns (M, order+1) coefficients with A(z) = 1 + a1·z⁻¹ + … + ap·z⁻ᵖ
    (column 0 is always 1.0). The Burg recursion below is the standard
    forward/backward least-squares form, vectorised across the M frames.
    """
    M, N = frames.shape
    f = frames.astype(np.float64, copy=True)      # forward prediction error
    b = frames.astype(np.float64, copy=True)      # backward prediction error
    a = np.zeros((M, order + 1), dtype=np.float64)
    a[:, 0] = 1.0
    s   = np.sum(frames * frames, axis=1)
    den = 2.0 * s - frames[:, 0] ** 2 - frames[:, -1] ** 2     # (M,)
    for k in range(order):
        fn = f[:, k + 1:N]                        # f[n],   n = k+1 … N-1
        bn = b[:, k:N - 1]                        # b[n-1], n = k+1 … N-1
        num  = 2.0 * np.sum(fn * bn, axis=1)
        safe = np.where(den > 1e-300, den, 1.0)
        kref = np.where(den > 1e-300, -num / safe, 0.0)
        kref = np.clip(kref, -0.999999, 0.999999)              # keep stable
        # Levinson update of the LPC vector (uses the pre-update a)
        a_old = a.copy()
        a[:, 1:k + 2] += kref[:, None] * a_old[:, k::-1]
        # Forward/backward error update (both from the pre-update f, b)
        kc = kref[:, None]
        fn_new = fn + kc * bn
        bn_new = bn + kc * fn
        f[:, k + 1:N] = fn_new
        b[:, k + 1:N] = bn_new
        if k < order - 1:
            den = (1.0 - kref ** 2) * den - f[:, k + 1] ** 2 - b[:, N - 1] ** 2
    return a


def _lpc_to_formants(a: np.ndarray, fs: float, n_formants: int,
                     f_lo: float = 50.0,
                     f_hi: Optional[float] = None
                     ) -> Tuple[np.ndarray, np.ndarray]:
    """Roots of each LPC polynomial → per-frame sorted formant Hz & bandwidth Hz.

    For a pole z:  freq = |∠z|·fs/2π,  bandwidth = -ln|z|·fs/π.
    Returns (F, B) each (M, n_formants), zero-padded where a frame yields
    fewer than n_formants in-band poles.
    """
    M, pp1 = a.shape
    p = pp1 - 1
    if f_hi is None:
        f_hi = fs / 2.0
    # Companion matrix of the monic polynomial [1, a1, …, ap] (a[:,0] == 1).
    C = np.zeros((M, p, p), dtype=np.float64)
    C[:, 0, :] = -a[:, 1:]
    if p > 1:
        di = np.arange(1, p)
        C[:, di, di - 1] = 1.0
    roots = np.linalg.eigvals(C)                  # (M, p) complex
    ang  = np.angle(roots)
    freq = np.abs(ang) * (fs / (2.0 * np.pi))
    bw   = -np.log(np.maximum(np.abs(roots), 1e-12)) * (fs / np.pi)
    # Keep one pole per conjugate pair (∠ > 0) that sits in the formant band.
    keep = (ang > 0.0) & (freq >= f_lo) & (freq <= f_hi)
    sortkey = np.where(keep, freq, np.inf)
    ix = np.argsort(sortkey, axis=1)
    freq_s = np.take_along_axis(sortkey, ix, axis=1)
    bw_s   = np.take_along_axis(bw,      ix, axis=1)
    F = np.zeros((M, n_formants))
    B = np.zeros((M, n_formants))
    take = min(n_formants, p)
    blk_f = freq_s[:, :take]
    valid = np.isfinite(blk_f)
    F[:, :take] = np.where(valid, blk_f, 0.0)
    B[:, :take] = np.where(valid, bw_s[:, :take], 0.0)
    return F, B


def _praat_burg_formant_frames(voice: np.ndarray, sr: int,
                               n_formants: int = 5,
                               max_formant: float = 5500.0,
                               win_ms: float = 25.0, hop_ms: float = 10.0,
                               pre_emph_hz: float = 50.0):
    """Praat-style "To Formant (burg)".

    Returns (F, B, n_frames, hop_orig):
      F, B      per-frame formant Hz & bandwidth Hz, each (n_frames, n_formants)
      hop_orig  the 10 ms frame hop expressed in ORIGINAL-sr samples, used to
                map per-cycle indices onto the frame grid.
    """
    from scipy.signal import resample_poly
    from math import gcd

    hop_orig = max(1, int(round(hop_ms * 0.001 * sr)))
    voice = np.asarray(voice, dtype=np.float64)

    # 1) Resample to 2·max_formant so a Burg order of 2·n_formants spans
    #    exactly the formant band — same trick Praat uses.
    target = int(round(2.0 * max_formant))
    g = gcd(target, int(sr))
    up, down = target // g, int(sr) // g
    v = voice if (up == down) else resample_poly(voice, up, down)
    fs_r = sr * up / down

    # 2) Pre-emphasis  y[n] = x[n] - exp(-2π·f/fs)·x[n-1]
    alpha = float(np.exp(-2.0 * np.pi * pre_emph_hz / fs_r))
    v_pe = v.astype(np.float64, copy=True)
    v_pe[1:] -= alpha * v[:-1]

    # 3) Framing — Praat's physical analysis window is 2× window_length.
    win = max(8, int(round(2.0 * win_ms * 0.001 * fs_r)))
    hop = max(1, int(round(hop_ms * 0.001 * fs_r)))
    if len(v_pe) < win:
        z = np.zeros((0, n_formants))
        return z, z, 0, hop_orig
    n_frames = 1 + (len(v_pe) - win) // hop

    # Praat's Gaussian analysis window (the −12 form used in its LPC stage).
    t = np.arange(win) / (win - 1) - 0.5
    gwin = (np.exp(-12.0 * t * t) - np.exp(-12.0)) / (1.0 - np.exp(-12.0))

    order = 2 * n_formants
    F = np.zeros((n_frames, n_formants))
    B = np.zeros((n_frames, n_formants))

    # Chunk the per-frame Burg so the (chunk, win) work arrays stay small
    # even on 25-min recordings (≈150 k frames).
    view  = sliding_window_view(v_pe, win)
    CHUNK = 8192
    for c0 in range(0, n_frames, CHUNK):
        starts = np.arange(c0, min(c0 + CHUNK, n_frames)) * hop
        frames = view[starts].astype(np.float64)
        frames = (frames - frames.mean(axis=1, keepdims=True)) * gwin
        lpc = _burg_lpc_batch(frames, order)
        Fc, Bc = _lpc_to_formants(lpc, fs_r, n_formants,
                                  f_lo=50.0, f_hi=max_formant)
        F[c0:c0 + len(starts)] = Fc
        B[c0:c0 + len(starts)] = Bc
    return F, B, n_frames, hop_orig


class FormantCalculator(MetricCalculator):
    """Per-cycle F1, F2, F3 (Hz) + Singer's Formant Energy (dB).

    F1/F2/F3 come from the Praat-style Burg + polynomial-root extractor
    (`_praat_burg_formant_frames`). SFE is an independent FFT power ratio
    on the singer's-formant band, unchanged.
    """

    def __init__(self, config: VoiceMapConfig,
                 n_formants: int = 5,
                 win_ms: float = 25.0, hop_ms: float = 10.0,
                 max_formant: float = 5500.0,
                 singer_band: Tuple[float, float] = (2800.0, 3400.0),
                 pre_emphasis_hz: float = 50.0,
                 lpc_order: Optional[int] = None):   # accepted, no longer used
        super().__init__(config)
        self.n_formants  = int(n_formants)
        self.win_ms, self.hop_ms = float(win_ms), float(hop_ms)
        self.max_formant = float(max_formant)
        self.singer_band = (float(singer_band[0]), float(singer_band[1]))
        self.pre_emphasis_hz = float(pre_emphasis_hz)

    def calculate(self, voice: np.ndarray,
                  cycle_triggers: np.ndarray) -> Dict[str, np.ndarray]:
        logger.info("Calculating formants (Praat-style Burg + roots) + SFE...")

        idx = np.where(cycle_triggers > 0.5)[0]
        n_cycles = max(len(idx) - 1, 0)
        z = lambda: np.zeros(n_cycles)
        keys = ("f1", "f2", "f3", "sfe")
        if n_cycles == 0:
            return {k: z() for k in keys}

        sr = self.sample_rate

        # --- F1/F2/F3 via Praat-style Burg LPC + polynomial roots ---
        F, B, n_frames, hop = _praat_burg_formant_frames(
            voice, sr, n_formants=self.n_formants,
            max_formant=self.max_formant,
            win_ms=self.win_ms, hop_ms=self.hop_ms,
            pre_emph_hz=self.pre_emphasis_hz)
        if n_frames == 0:
            return {k: z() for k in keys}
        f1, f2, f3 = F[:, 0], F[:, 1], F[:, 2]

        # --- Singer's Formant Energy: FFT power ratio (dB), original sr ---
        win = int(self.win_ms * 0.001 * sr)
        sfe_db = np.zeros(n_frames)
        if len(voice) >= win:
            v = np.asarray(voice, dtype=np.float64)
            v_pe = v.copy()
            v_pe[1:] -= 0.97 * v[:-1]
            nf       = 1 + (len(v_pe) - win) // hop
            starts   = np.arange(nf) * hop
            frames   = sliding_window_view(v_pe, win)[starts]
            frames_w = (frames - frames.mean(axis=1, keepdims=True)) * np.hamming(win)
            power     = np.abs(np.fft.rfft(frames_w, 2048, axis=1)) ** 2
            freqs_sfe = np.fft.rfftfreq(2048, 1.0 / sr)
            mask      = (freqs_sfe >= self.singer_band[0]) & \
                        (freqs_sfe <= self.singer_band[1])
            ratio  = power[:, mask].sum(axis=1) / np.maximum(power.sum(axis=1), 1e-15)
            sfe_db = 10.0 * np.log10(np.maximum(ratio, 1e-6))

        # Assign each cycle to its enclosing frame
        cycle_starts = idx[:-1]
        fi_fmt = np.clip(cycle_starts // hop, 0, n_frames - 1)
        fi_sfe = np.clip(cycle_starts // hop, 0, max(len(sfe_db) - 1, 0))

        out = {
            "f1":  f1[fi_fmt],
            "f2":  f2[fi_fmt],
            "f3":  f3[fi_fmt],
            "sfe": sfe_db[fi_sfe] if len(sfe_db) else z(),
        }

        def _report(name, arr, unit):
            nz = arr[arr > (0 if unit != "dB" else -50)]
            if len(nz):
                logger.info("  %s: mean=%.1f %s  range=[%.1f, %.1f]",
                            name, float(nz.mean()), unit, float(nz.min()), float(nz.max()))
        _report("F1", out["f1"], "Hz")
        _report("F2", out["f2"], "Hz")
        _report("F3", out["f3"], "Hz")
        _report("SFE", out["sfe"], "dB")
        return out


# ───────────────────────────────────────────────────────────────────────────
# Formant bandwidths B1/B2/B3 + Singing Power Ratio + GNE (待验证).
# Independent LPC root-finding pass — separate from FormantCalculator's
# spectrum-peak F1/F2/F3 so the two coexist (B1/B2/B3 here may not align
# perfectly with F1/F2/F3 from FormantCalculator since they come from
# different tracker designs).
# ───────────────────────────────────────────────────────────────────────────
class FormantExtrasCalculator(MetricCalculator):
    """B1/B2/B3 from LPC roots + Formant Dispersion + Singing Power Ratio + GNE-like."""

    KEYS = ("b1", "b2", "b3", "formant_dispersion", "spr", "gne")

    def __init__(self, config: VoiceMapConfig,
                 win_ms: float = 25.0, hop_ms: float = 10.0,
                 n_formants: int = 5, max_formant: float = 5500.0,
                 pre_emphasis_hz: float = 50.0,
                 spr_lo_band: Tuple[float, float] = (0.0, 2000.0),
                 spr_hi_band: Tuple[float, float] = (2000.0, 4000.0),
                 lpc_order: Optional[int] = None):   # accepted, no longer used
        super().__init__(config)
        self.win_ms, self.hop_ms = float(win_ms), float(hop_ms)
        self.n_formants  = int(n_formants)
        self.max_formant = float(max_formant)
        self.pre_emphasis_hz = float(pre_emphasis_hz)
        self.spr_lo = spr_lo_band
        self.spr_hi = spr_hi_band

    def calculate(self, voice: np.ndarray,
                  cycle_triggers: np.ndarray) -> Dict[str, np.ndarray]:
        logger.info("Calculating B1/B2/B3 (Burg poles) + Dispersion + SPR + GNE...")
        idx = np.where(cycle_triggers > 0.5)[0]
        n_cycles = max(len(idx) - 1, 0)
        z = lambda: np.zeros(n_cycles)
        if n_cycles == 0:
            return {k: z() for k in self.KEYS}

        sr = self.sample_rate

        # --- B1/B2/B3 + dispersion from Praat-style Burg poles ---
        F, B, n_frames, hop = _praat_burg_formant_frames(
            voice, sr, n_formants=self.n_formants, max_formant=self.max_formant,
            win_ms=self.win_ms, hop_ms=self.hop_ms,
            pre_emph_hz=self.pre_emphasis_hz)
        if n_frames == 0:
            return {k: z() for k in self.KEYS}

        b1, b2, b3 = B[:, 0].copy(), B[:, 1].copy(), B[:, 2].copy()
        # Physiological ceiling — FWHM > 800 Hz is implausible for speech
        # formants; drop to 0 (the NA-as-0 convention used elsewhere).
        for bb in (b1, b2, b3):
            bb[bb > 800.0] = 0.0
        f_disp = np.where((F[:, 0] > 0) & (F[:, 2] > 0),
                          (F[:, 2] - F[:, 0]) / 2.0, 0.0)

        # --- SPR + GNE: FFT power ratios on original-sr frames (unchanged) ---
        win = int(self.win_ms * 0.001 * sr)
        spr = np.zeros(n_frames)
        gne_proxy = np.zeros(n_frames)
        if len(voice) >= win:
            v = np.asarray(voice, dtype=np.float64)
            v_pe = v.copy()
            v_pe[1:] -= 0.97 * v[:-1]
            nf       = 1 + (len(v_pe) - win) // hop
            starts   = np.arange(nf) * hop
            frames   = sliding_window_view(v_pe, win)[starts]
            frames_w = (frames - frames.mean(axis=1, keepdims=True)) * np.hamming(win)
            psd   = np.abs(np.fft.rfft(frames_w, 2048, axis=1)) ** 2
            freqs = np.fft.rfftfreq(2048, 1.0 / sr)
            m_lo = (freqs >= self.spr_lo[0]) & (freqs < self.spr_lo[1])
            m_hi = (freqs >= self.spr_hi[0]) & (freqs <= self.spr_hi[1])
            spr  = 10.0 * np.log10(
                np.maximum(psd[:, m_hi].sum(axis=1), 1e-15) /
                np.maximum(psd[:, m_lo].sum(axis=1), 1e-15))
            # GNE-like: normalised cross-power of two adjacent bands (待验证).
            m_g1 = (freqs >= 500.0)  & (freqs < 1500.0)
            m_g2 = (freqs >= 1500.0) & (freqs <= 2500.0)
            e_g1 = psd[:, m_g1].sum(axis=1)
            e_g2 = psd[:, m_g2].sum(axis=1)
            gne_proxy = np.minimum(e_g1, e_g2) / np.maximum(
                np.maximum(e_g1, e_g2), 1e-15)

        cycle_starts = idx[:-1]
        fi    = np.clip(cycle_starts // hop, 0, n_frames - 1)
        fi_sp = np.clip(cycle_starts // hop, 0, max(len(spr) - 1, 0))

        return {
            "b1":                  b1[fi],
            "b2":                  b2[fi],
            "b3":                  b3[fi],
            "formant_dispersion":  f_disp[fi],
            "spr":                 spr[fi_sp] if len(spr) else z(),
            "gne":                 gne_proxy[fi_sp] if len(gne_proxy) else z(),
        }


# ───────────────────────────────────────────────────────────────────────────
# Whole-recording integrative metrics — MPT, Voicing Ratio, DUV.
# These produce one scalar per recording, which we then broadcast to every
# (MIDI, dB) cell so the metric still appears in the VRP grid (uniform
# colour). For per-VRP-cell analytics they're less useful; for whole-
# recording reporting (e.g. clinical summary) they're invaluable.
# ───────────────────────────────────────────────────────────────────────────
class IntegrativeMetricsCalculator(MetricCalculator):
    """MPT (s), Voicing Ratio (0-1), DUV (% unvoiced) — one value broadcast per cycle."""

    KEYS = ("mpt", "voicing_ratio", "duv")

    def calculate(self, voice: np.ndarray, midi_per_cycle: np.ndarray,
                  cycle_triggers: np.ndarray) -> Dict[str, np.ndarray]:
        idx = np.where(cycle_triggers > 0.5)[0]
        n_cycles = max(len(idx) - 1, 0)
        if n_cycles == 0:
            return {k: np.zeros(0) for k in self.KEYS}

        sr  = self.sample_rate
        # A cycle is "voiced" if its detected pitch (MIDI) is positive.
        voiced_cycle = midi_per_cycle > 0

        # Maximum Phonation Time = longest contiguous run of voiced cycles
        # converted from sample-count to seconds.
        T = np.diff(idx).astype(np.float64) / sr   # cycle durations in s
        max_run_sec = 0.0
        cur = 0.0
        for i in range(n_cycles):
            if voiced_cycle[i]:
                cur += T[i]
                if cur > max_run_sec:
                    max_run_sec = cur
            else:
                cur = 0.0

        # Voicing ratio: voiced cycles / total
        voicing = float(voiced_cycle.mean()) if n_cycles else 0.0
        # DUV: % of cycles that are unvoiced (within the analysed cycle set)
        duv = 100.0 * (1.0 - voicing)

        logger.info("  MPT: %.2f s   VoicingRatio: %.3f   DUV: %.2f%%",
                    max_run_sec, voicing, duv)

        # Broadcast: same value for every cycle so it lands in every cell
        return {
            "mpt":            np.full(n_cycles, max_run_sec, dtype=np.float64),
            "voicing_ratio":  np.full(n_cycles, voicing,    dtype=np.float64),
            "duv":            np.full(n_cycles, duv,        dtype=np.float64),
        }


# ───────────────────────────────────────────────────────────────────────────
# Vibrato Jitter — stability of the vibrato cycle period.
# Computed only on cycles where VibratoCalculator detected a non-zero rate;
# measures how regular the vibrato is. High value = irregular / wobbly.
# ───────────────────────────────────────────────────────────────────────────
class VibratoJitterCalculator(MetricCalculator):
    """Per-cycle relative variability of vibrato period (%, sliding-window)."""

    def __init__(self, config: VoiceMapConfig, window_cycles: int = 40):
        super().__init__(config)
        self.window_cycles = int(window_cycles)

    def calculate(self, vibrato_rate: np.ndarray) -> np.ndarray:
        n = len(vibrato_rate)
        if n == 0:
            return np.zeros(0)
        W = min(self.window_cycles, max(n // 4, 4))
        if n < W or W < 4:
            return np.zeros(n)

        # Sliding window CV of vibrato period (1/rate, ignoring zero rates)
        out = np.zeros(n)
        wins = sliding_window_view(vibrato_rate, W)
        for i, w in enumerate(wins):
            valid = w > 0
            if valid.sum() < 4:
                continue
            periods = 1.0 / w[valid]
            mu = periods.mean()
            sd = periods.std()
            out[i + W // 2] = 100.0 * sd / max(mu, 1e-9)
        # Edge padding
        if (out > 0).any():
            first_nz = np.argmax(out > 0)
            last_nz  = n - 1 - np.argmax((out > 0)[::-1])
            out[:first_nz] = out[first_nz]
            out[last_nz + 1:] = out[last_nz]

        good = out > 0
        if good.any():
            logger.info("  VibratoJitter: mean=%.2f%%  range=[%.2f, %.2f]",
                        float(out[good].mean()),
                        float(out[good].min()), float(out[good].max()))
        return out


# ---------------------------------------------------------------------------
# P2: H1-H2 and H1-H3 — spectral tilt from voice-channel per-cycle DFT.
#
# Physics: the relative amplitude of the fundamental versus the next
# harmonics encodes glottal source shape.
#   Breathy   → H1 strong, H2/H3 weak   → H1-H2 positive and large
#   Modal     → graded decay             → H1-H2 ≈ 2–6 dB
#   Pressed   → H2 close to or above H1  → H1-H2 near 0 or negative
# These complement the EGG-side Qcontact/Icontact picture.
#
# Per cycle: reuse _compute_cycle_dft on the *voice* channel (not EGG)
# for the first 3 harmonics. H1–H2 = 20·log10(|X[0]|/|X[1]|), similarly H3.
# Output clipped to ±40 dB so a spurious near-zero harmonic can't destroy
# the per-cell mean on aggregation.
# ---------------------------------------------------------------------------
class HarmonicDiffCalculator(MetricCalculator):
    """Per-cycle H1-H2 and H1-H3 (voice) in dB."""

    def __init__(self, config: VoiceMapConfig, clip_db: float = 40.0):
        super().__init__(config)
        self.clip_db = float(clip_db)

    def calculate(self, voice: np.ndarray,
                  cycle_triggers: np.ndarray) -> Dict[str, np.ndarray]:
        logger.info("Calculating H1-H2 / H1-H3 (voice DFT)...")
        idx = np.where(cycle_triggers > 0.5)[0]
        n_cycles = max(len(idx) - 1, 0)
        if n_cycles == 0:
            return {"h1h2": np.zeros(0), "h1h3": np.zeros(0)}

        # Voice per-cycle DFT at 3 harmonics (function is signal-agnostic —
        # reuses the exact same single-cycle FFT machinery we already use
        # for EGG in HRFCalculator, ClusterCalculator, etc.).
        amps, _ = _compute_cycle_dft(voice, idx, 3)   # (n, 3)

        eps = 1e-15
        h1 = np.maximum(amps[:, 0], eps)
        h2 = np.maximum(amps[:, 1], eps)
        h3 = np.maximum(amps[:, 2], eps)
        h1h2 = 20.0 * np.log10(h1 / h2)
        h1h3 = 20.0 * np.log10(h1 / h3)

        # Clip pathological extremes (near-zero harmonic amplitude on very
        # short or noisy cycles otherwise gives ±∞ that destroys cell means).
        np.clip(h1h2, -self.clip_db, self.clip_db, out=h1h2)
        np.clip(h1h3, -self.clip_db, self.clip_db, out=h1h3)

        logger.info("  H1-H2: mean=%.2f dB  range=[%.2f, %.2f]",
                    float(h1h2.mean()), float(h1h2.min()), float(h1h2.max()))
        logger.info("  H1-H3: mean=%.2f dB  range=[%.2f, %.2f]",
                    float(h1h3.mean()), float(h1h3.min()), float(h1h3.max()))

        return {"h1h2": h1h2, "h1h3": h1h3}


# ---------------------------------------------------------------------------
# P1: Jitter / Shimmer per cycle.
#   Jitter_local  = mean(|T[i] - T[i-1]|) / mean(T)      · %
#   Jitter_RAP    = mean(|T[i] - avg3(T[i-1..i+1])|) / mean(T)   · %   (3-pt)
#   Jitter_PPQ5   = mean(|T[i] - avg5(T[i-2..i+2])|) / mean(T)   · %   (5-pt)
#   Shimmer_local = mean(|A[i] - A[i-1]|) / mean(A)      · %
#   Shimmer_dB    = mean(|20·log10(A[i] / A[i-1])|)      · dB
#   Shimmer_APQ11 = mean(|A[i] - avg11(A[i-5..i+5])|) / mean(A)  · %   (11-pt)
# where T[i] = cycle period (samples), A[i] = peak-to-peak voice amplitude.
#
# These are the Praat/MDVP formulas used in clinical voice science. Output
# is a per-cycle value (NOT a whole-recording scalar) so it can be
# aggregated per VRP cell like every other metric.
# ---------------------------------------------------------------------------
class PerturbationCalculator(MetricCalculator):
    """Cycle-to-cycle jitter (period) and shimmer (amplitude) perturbations."""

    # Keys returned from calculate()
    KEYS = (
        "jitter_local", "jitter_rap",   "jitter_ppq5",
        "shimmer_local", "shimmer_db",
        "shimmer_apq3",  "shimmer_apq5", "shimmer_apq11",
    )

    # MDVP / Praat outlier rejection. A successive period (or amplitude)
    # ratio beyond these factors is treated as a detection glitch and the
    # affected cycle is masked out of the perturbation sum and denominator.
    # 1.3 / 1.6 are Praat's documented defaults.
    PERIOD_FACTOR_MAX    = 1.3
    AMPLITUDE_FACTOR_MAX = 1.6

    @staticmethod
    def _adjacent_ok(x: np.ndarray, max_factor: float) -> np.ndarray:
        """Boolean per-cycle mask: True if x[i] and x[i-1] are within a
        factor of max_factor of each other. Cycle 0 is always False (no
        previous neighbour to compare to)."""
        ok = np.zeros(len(x), dtype=bool)
        if len(x) < 2:
            return ok
        prev, cur = x[:-1], x[1:]
        safe_prev = np.maximum(prev, 1e-15)
        safe_cur  = np.maximum(cur,  1e-15)
        ratio = np.maximum(safe_cur / safe_prev, safe_prev / safe_cur)
        ok[1:] = ratio < max_factor
        return ok

    @classmethod
    def _local_perturb(cls, x: np.ndarray, ok: np.ndarray) -> np.ndarray:
        """Praat-style jitter/shimmer local with outlier mask.
        |x[i] - x[i-1]| / mean(x over ok cycles) · 100; cycles with
        ok[i]=False contribute 0 (masked out of both numerator and denominator).
        """
        out = np.zeros_like(x)
        if len(x) < 2 or not ok.any():
            return out
        mx = x[ok | np.roll(ok, -1)].mean() if ok.any() else 0.0
        if mx <= 0:
            return out
        diff = np.abs(np.diff(x))
        out[1:] = np.where(ok[1:], diff / mx * 100.0, 0.0)
        return out

    @classmethod
    def _npq_perturb(cls, x: np.ndarray, n_pts: int,
                     ok: np.ndarray) -> np.ndarray:
        """n-point PPQ/APQ with ok mask; pairs that touch an ok=False
        cycle are zeroed."""
        if n_pts % 2 != 1:
            raise ValueError("n_pts must be odd")
        k = n_pts // 2
        if len(x) < n_pts or not ok.any():
            return np.zeros_like(x)
        mx = x[ok].mean()
        if mx <= 0:
            return np.zeros_like(x)
        wins      = sliding_window_view(x,  n_pts)   # (len-n_pts+1, n_pts)
        wins_ok   = sliding_window_view(ok, n_pts)
        avg       = wins.mean(axis=1)
        center_ok = wins_ok[:, k] & wins_ok.all(axis=1)
        raw       = np.abs(x[k:k + len(avg)] - avg) / mx * 100.0
        out = np.zeros_like(x)
        out[k:k + len(avg)] = np.where(center_ok, raw, 0.0)
        return out

    def calculate(self, voice: np.ndarray,
                  cycle_triggers: np.ndarray) -> Dict[str, np.ndarray]:
        logger.info("Calculating jitter + shimmer (MDVP, period-factor %.1f)...",
                    self.PERIOD_FACTOR_MAX)
        idx = np.where(cycle_triggers > 0.5)[0]
        n = max(len(idx) - 1, 0)
        z = lambda: np.zeros(n)
        if n < 3:
            return {k: z() for k in self.KEYS}

        # Periods T[i] in samples (units cancel in relative formulas)
        T = np.diff(idx).astype(np.float64)

        # Peak-to-peak voice amplitude per cycle. A plain Python loop over
        # ~12k cycles is ~60 ms — not worth the complexity of a vectorised
        # reduceat here (would need boundary-index massage for equal-length
        # semantics).
        A = np.empty(n, dtype=np.float64)
        for i in range(n):
            s, e = idx[i], idx[i + 1]
            if e > s:
                seg = voice[s:e]
                A[i] = seg.max() - seg.min()
            else:
                A[i] = 0.0
        A_safe = np.maximum(A, 1e-15)

        # Outlier masks (Praat-style period/amplitude factor rejection)
        ok_T = self._adjacent_ok(T, self.PERIOD_FACTOR_MAX)
        ok_A = self._adjacent_ok(A, self.AMPLITUDE_FACTOR_MAX)

        jitter_local  = self._local_perturb(T, ok_T)
        jitter_rap    = self._npq_perturb  (T, 3,  ok_T)
        jitter_ppq5   = self._npq_perturb  (T, 5,  ok_T)

        shimmer_local = self._local_perturb(A, ok_A)
        # dB shimmer: per-cycle |20·log10(A[i]/A[i-1])|; masked at outlier cycles
        shimmer_db    = np.zeros(n)
        shimmer_db[1:] = np.where(
            ok_A[1:], np.abs(20.0 * np.log10(A_safe[1:] / A_safe[:-1])), 0.0)
        shimmer_apq3  = self._npq_perturb(A, 3,  ok_A)
        shimmer_apq5  = self._npq_perturb(A, 5,  ok_A)
        shimmer_apq11 = self._npq_perturb(A, 11, ok_A)

        logger.info("  Jitter local=%.3f%%  RAP=%.3f%%  PPQ5=%.3f%%",
                    float(jitter_local[jitter_local > 0].mean() or 0),
                    float(jitter_rap[jitter_rap > 0].mean() or 0),
                    float(jitter_ppq5[jitter_ppq5 > 0].mean() or 0))
        logger.info("  Shimmer local=%.3f%%  dB=%.3f  APQ11=%.3f%%",
                    float(shimmer_local[shimmer_local > 0].mean() or 0),
                    float(shimmer_db[shimmer_db > 0].mean() or 0),
                    float(shimmer_apq11[shimmer_apq11 > 0].mean() or 0))

        return {
            "jitter_local":  jitter_local,
            "jitter_rap":    jitter_rap,
            "jitter_ppq5":   jitter_ppq5,
            "shimmer_local": shimmer_local,
            "shimmer_db":    shimmer_db,
            "shimmer_apq3":  shimmer_apq3,
            "shimmer_apq5":  shimmer_apq5,
            "shimmer_apq11": shimmer_apq11,
        }


# ---------------------------------------------------------------------------
# ADD-ON: NHR — Noise-to-Harmonics Ratio, classical clinical measure.
# Arithmetic inverse of the linear HNR value. NHR > 0.19 is pathological
# by the Kay/MDVP reference; healthy voices sit around 0.1. Computing it
# just takes the per-cycle HNR we already make, so this class is a thin
# wrapper — keeping it separate makes the dedicated CSV column explicit.
# Status: 待验证 (not yet cross-checked against MDVP/Praat)
# ---------------------------------------------------------------------------
class NHRCalculator(MetricCalculator):
    """NHR = 1 / H, where H is the linear harmonics-to-noise ratio."""

    def calculate(self, voice: np.ndarray, cycle_triggers: np.ndarray,
                  hnr_values: Optional[np.ndarray] = None) -> np.ndarray:
        # If caller already computed HNR, reuse; otherwise compute inline.
        if hnr_values is None:
            hnr_values = HNRCalculator(self.config).calculate(voice, cycle_triggers)
        # Convert dB → linear ratio, then invert. Clip to avoid 0 / inf.
        h_linear = np.power(10.0, hnr_values / 10.0)
        nhr = 1.0 / np.maximum(h_linear, 1e-6)
        nhr = np.clip(nhr, 0.0, 10.0)   # sanity
        valid = nhr > 0
        if valid.any():
            logger.info("  NHR: mean=%.3f  range=[%.3f, %.3f]  (n=%d)",
                        float(nhr[valid].mean()), float(nhr[valid].min()),
                        float(nhr[valid].max()), int(valid.sum()))
        return nhr


# ---------------------------------------------------------------------------
# ADD-ON: CPPS — Cepstral Peak Prominence Smoothed (Hillenbrand 1996).
# Same cepstrum peak we compute for CPP, but smoothed over a short time
# window to reduce frame-to-frame jitter. Widely reported in clinical
# dysphonia literature as more stable than raw CPP.
# Status: 待验证 (not cross-checked)
# ---------------------------------------------------------------------------
class CPPSCalculator(MetricCalculator):
    """Temporal moving-average of CPP. `smooth_cycles` centred cycles wide."""

    def __init__(self, config: VoiceMapConfig, smooth_cycles: int = 5):
        super().__init__(config)
        self.smooth_cycles = max(1, int(smooth_cycles))

    def calculate(self, cpp_per_cycle: np.ndarray) -> np.ndarray:
        n = len(cpp_per_cycle)
        if n == 0:
            return np.zeros(0)
        w = min(self.smooth_cycles, n)
        if w % 2 == 0:
            w += 1   # odd → centred kernel
        kernel = np.ones(w) / w
        cpps = np.convolve(cpp_per_cycle, kernel, mode="same")
        logger.info("  CPPS (w=%d cycles): mean=%.2f  range=[%.2f, %.2f]",
                    w, float(cpps.mean()), float(cpps.min()), float(cpps.max()))
        return cpps


# ---------------------------------------------------------------------------
# ADD-ON: PPE — Pitch Period Entropy (Little et al 2009, Parkinson voice).
# Shannon entropy of the per-cycle log-period distribution inside a sliding
# window, normalised to [0, 1]. Low PPE = stable pitch, high PPE = noisy /
# irregular. Computed per-cycle via a ±W/2 window so it can be aggregated
# into the VRP grid.
# Status: 待验证
# ---------------------------------------------------------------------------
class PPECalculator(MetricCalculator):
    """Sliding-window Shannon entropy of log-period distribution."""

    def __init__(self, config: VoiceMapConfig,
                 window_cycles: int = 40, bins: int = 10):
        super().__init__(config)
        self.window_cycles = int(window_cycles)
        self.bins = int(bins)

    def calculate(self, cycle_triggers: np.ndarray) -> np.ndarray:
        idx = np.where(cycle_triggers > 0.5)[0]
        n = max(len(idx) - 1, 0)
        if n < self.window_cycles + 2:
            return np.zeros(n)

        # log-period per cycle (units cancel in ratio-based entropy)
        T    = np.diff(idx).astype(np.float64)
        logT = np.log(np.maximum(T, 1.0))

        W    = self.window_cycles
        wins = sliding_window_view(logT, W)             # (n-W+1, W)
        nw   = wins.shape[0]

        # Per-window: detrend, histogram, Shannon entropy normalised by log(bins).
        # Normalisation → PPE ∈ [0, 1] so it's comparable across recordings.
        log_bins = np.log(self.bins) if self.bins > 1 else 1.0
        ppe_win  = np.zeros(nw)
        for i in range(nw):
            w = wins[i] - wins[i].mean()
            # Dynamic range for the histogram: per-window σ, fall back if zero.
            s = w.std()
            if s < 1e-9:
                continue
            edges = np.linspace(w.min() - 1e-9, w.max() + 1e-9, self.bins + 1)
            counts, _ = np.histogram(w, bins=edges)
            p = counts.astype(np.float64) / max(counts.sum(), 1)
            p = p[p > 0]
            ppe_win[i] = float(-np.sum(p * np.log(p)) / log_bins)

        # Assign each cycle the PPE of its centred window; pad edges.
        half = W // 2
        out  = np.zeros(n)
        out[half:half + nw] = ppe_win
        if nw:
            out[:half]            = ppe_win[0]
            out[half + nw:]       = ppe_win[-1]
        good = out > 0
        if good.any():
            logger.info("  PPE (w=%d cycles, %d bins): mean=%.3f  range=[%.3f, %.3f]",
                        W, self.bins, float(out[good].mean()),
                        float(out[good].min()), float(out[good].max()))
        return out


# ---------------------------------------------------------------------------
# ADD-ON: ZCR — Zero-Crossing Rate per cycle (voice channel).
# Classical noise indicator — clean periodic voice has one main crossing
# per half-period; noisy / breathy voice has many extra crossings inside
# each cycle. Value is crossings / cycle_length so it's unit-less and
# comparable across pitches.
# Status: 待验证
# ---------------------------------------------------------------------------
class ZCRCalculator(MetricCalculator):
    """Per-cycle zero-crossing count / cycle length."""

    def calculate(self, voice: np.ndarray,
                  cycle_triggers: np.ndarray) -> np.ndarray:
        idx = np.where(cycle_triggers > 0.5)[0]
        n = max(len(idx) - 1, 0)
        if n == 0:
            return np.zeros(0)

        zcr = np.zeros(n, dtype=np.float64)
        # A Python loop over 12k cycles does ~50 ms; skipping reduceat
        # trickery (cycle lengths vary).
        for i in range(n):
            s, e = idx[i], idx[i + 1]
            if e - s < 2:
                continue
            seg = voice[s:e]
            crossings = int(np.sum(np.diff(np.sign(seg)) != 0))
            zcr[i] = crossings / float(e - s)

        logger.info("  ZCR: mean=%.4f  range=[%.4f, %.4f]",
                    float(zcr.mean()), float(zcr.min()), float(zcr.max()))
        return zcr


# ---------------------------------------------------------------------------
# P1: HNR — Harmonics-to-Noise Ratio on the voice channel.
# Praat-style autocorrelation method. For each analysis frame:
#   r(τ) = autocorrelation, normalised so r(0) = 1
#   p    = max r(τ) for τ ∈ [1/f_max, 1/f_min]       (expected pitch range)
#   HNR  = 10·log10( p / (1 - p) )     dB
# Computed on 40 ms frames with 10 ms hop; each cycle is assigned the HNR
# of its enclosing frame.
# ---------------------------------------------------------------------------
class HNRCalculator(MetricCalculator):
    """Per-cycle Harmonics-to-Noise Ratio (Praat autocorrelation method)."""

    def __init__(self, config: VoiceMapConfig,
                 win_ms: float = 40.0, hop_ms: float = 10.0,
                 f_min: float = 60.0,   f_max: float = 400.0):
        super().__init__(config)
        self.win_ms, self.hop_ms = float(win_ms), float(hop_ms)
        self.f_min,  self.f_max  = float(f_min),  float(f_max)

    def calculate(self, voice: np.ndarray,
                  cycle_triggers: np.ndarray) -> np.ndarray:
        logger.info("Calculating HNR (voice, autocorrelation)...")
        idx = np.where(cycle_triggers > 0.5)[0]
        n_cycles = max(len(idx) - 1, 0)
        if n_cycles == 0:
            return np.zeros(0)

        sr  = self.sample_rate
        win = int(self.win_ms * 0.001 * sr)
        hop = int(self.hop_ms * 0.001 * sr)
        if len(voice) < win or hop < 1:
            return np.zeros(n_cycles)

        min_lag = max(1, int(sr / self.f_max))
        max_lag = int(sr / self.f_min)
        if max_lag <= min_lag:
            return np.zeros(n_cycles)

        # FFT size: next power of 2 ≥ 2·win (for linear via circular autocorr)
        nfft = 1
        while nfft < 2 * win:
            nfft *= 2

        # Build all frames at once using sliding_window_view — avoids a
        # Python loop, drops HNR to well under 100 ms for typical lengths.
        n_frames = 1 + (len(voice) - win) // hop
        starts   = np.arange(n_frames) * hop
        frames   = sliding_window_view(voice, win)[starts]   # (n_frames, win)
        # Hann window + zero-mean per frame
        hann     = np.hanning(win)
        frames_w = (frames - frames.mean(axis=1, keepdims=True)) * hann

        # FFT-based autocorrelation, batched over frames
        X   = np.fft.rfft(frames_w, nfft, axis=1)
        acf = np.fft.irfft(X * np.conj(X), nfft, axis=1)[:, :win]   # (n_frames, win)

        # Praat's compensation: windowing reduces the autocorrelation peak
        # at non-zero lags because the signal gets tapered. Divide by the
        # autocorrelation of the window itself to recover the unbiased
        # signal autocorrelation. Without this the HNR is systematically
        # underestimated (10-15 dB too low on typical voice).
        W   = np.fft.rfft(hann, nfft)
        win_acf = np.fft.irfft(W * np.conj(W), nfft)[:win]
        win_acf_safe = np.where(np.abs(win_acf) < 1e-15, 1.0, win_acf)
        acf = acf / win_acf_safe[None, :]

        # Normalise by r(0); guard against silent frames
        r0  = acf[:, 0:1]
        bad = (r0[:, 0] <= 0)
        r0_safe = np.where(bad[:, None], 1.0, r0)
        acf_n = acf / r0_safe

        # Peak in pitch range → HNR
        peak = acf_n[:, min_lag:max_lag + 1].max(axis=1)
        peak = np.clip(peak, 1e-6, 0.9999)
        hnr_frames = 10.0 * np.log10(peak / (1.0 - peak))
        hnr_frames[bad] = 0.0

        # Assign each cycle to its nearest frame start
        cycle_starts = idx[:-1]
        frame_idx    = np.clip(cycle_starts // hop, 0, n_frames - 1)
        hnr_per_cycle = hnr_frames[frame_idx]

        valid = hnr_per_cycle != 0
        if valid.any():
            logger.info("  HNR: %d cycles  mean=%.2f dB  range %.2f – %.2f",
                        n_cycles, hnr_per_cycle[valid].mean(),
                        hnr_per_cycle[valid].min(), hnr_per_cycle[valid].max())
        return hnr_per_cycle


# ---------------------------------------------------------------------------
# EGG cycle clustering (Cluster 1..5) — harmonic-shape K-means.
#
# Mirrors FonaDyn's VRPSDCluster.sc feature recipe:
#   per-cycle DFT at n harmonics →
#   feature vector = [ Δamp_dB[1..n], cos(Δφ[1..n]), sin(Δφ[1..n]) ]   (3n dims)
#   where Δamp_dB[k] = 20·log10(|X[k]| / |X[0]|)
#         Δφ[k]     = phase[k] - phase[0]
# K-means k=5, trained from scratch on the input recording (from-scratch matches
# the default `learn=true` behaviour when no pre-saved centroid CSV is loaded).
# Returns a 1..k label per cycle (0 reserved for "no cluster / not computed").
# ---------------------------------------------------------------------------
class ClusterCalculator:
    """
    K-means clustering over per-cycle EGG harmonic shape features.

    Returns an int array of length n_cycles, values in {1..n_clusters}; 0
    means the cycle was dropped (e.g. degenerate amplitude at fundamental).

    After a fit, `centroids_` holds the trained centroids (shape (k, 3n)) so
    they can be persisted to CSV and reloaded for cross-recording consistency
    (a recording analysed with preloaded centroids will use the same cluster
    label semantics as whichever recording trained them). Set `centroids_`
    directly to a pre-loaded array to run in "classify-only" mode — the
    next calculate() will skip K-means training and just assign each cycle
    to the nearest loaded centroid.
    """

    def __init__(self, config: VoiceMapConfig,
                 n_clusters: int = 5,
                 n_harmonics: int = 10,
                 random_state: int = 0):
        self.config = config
        self.n_clusters = int(n_clusters)
        self.n_harmonics = int(n_harmonics)
        self.random_state = int(random_state)
        self.centroids_ = None   # None → train from scratch; ndarray → classify only

    def calculate(self, egg: np.ndarray,
                  cycle_triggers: np.ndarray,
                  dft: Tuple[np.ndarray, np.ndarray] = None) -> np.ndarray:
        from sklearn.cluster import KMeans

        logger.info("Calculating EGG cycle clusters (k=%d, n_harm=%d)...",
                    self.n_clusters, self.n_harmonics)
        idx = np.where(cycle_triggers > 0.5)[0]
        n_cycles = max(len(idx) - 1, 0)
        if n_cycles < self.n_clusters:
            logger.warning("  Too few cycles (%d < k=%d); skipping cluster",
                           n_cycles, self.n_clusters)
            return np.zeros(n_cycles, dtype=np.int32)

        if dft is not None:
            amps   = dft[0][:, :self.n_harmonics]
            phases = dft[1][:, :self.n_harmonics]
        else:
            amps, phases = _compute_cycle_dft(egg, idx, self.n_harmonics)

        # Δamp_dB relative to fundamental (in dB). Fundamental near zero ⇒ invalid.
        fund = amps[:, 0]
        valid = fund > 1e-12
        if valid.sum() < self.n_clusters:
            logger.warning("  Only %d valid cycles; skipping cluster",
                           int(valid.sum()))
            return np.zeros(n_cycles, dtype=np.int32)

        amps_v = amps[valid]
        phases_v = phases[valid]

        eps = 1e-15
        damp_db = 20.0 * np.log10(
            np.maximum(amps_v[:, 1:], eps) / np.maximum(amps_v[:, :1], eps)
        )  # (n_valid, n-1)

        dphi = phases_v[:, 1:] - phases_v[:, :1]   # (n_valid, n-1)
        feats = np.concatenate([damp_db, np.cos(dphi), np.sin(dphi)], axis=1)

        # Expose the feature matrix so helpers (e.g. multi-wav joint training)
        # can accumulate features across recordings without re-running the
        # DFT pipeline.
        self._last_features = feats
        self._last_valid    = valid

        # Classify-only mode: preloaded centroids → euclidean nearest-centroid
        # assignment, no fit. Much faster and gives consistent labels across
        # recordings. Feature dim must match the loaded centroid dim.
        if self.centroids_ is not None:
            if self.centroids_.shape[1] != feats.shape[1]:
                logger.warning(
                    "  Loaded centroids dim %d != feature dim %d; retraining",
                    self.centroids_.shape[1], feats.shape[1])
                self.centroids_ = None

        if self.centroids_ is not None:
            # Pairwise squared euclidean → argmin across centroids
            diffs = feats[:, None, :] - self.centroids_[None, :, :]
            labels_v = np.einsum("ijk,ijk->ij", diffs, diffs).argmin(axis=1)
            logger.info("  Classified against %d preloaded centroids",
                        self.centroids_.shape[0])
        else:
            # n_init=3 converges to the same solution as 10 on real EGG features
            km = KMeans(n_clusters=self.n_clusters,
                        n_init=3, random_state=self.random_state)
            labels_v = km.fit_predict(feats)   # 0..k-1
            centers_tmp = km.cluster_centers_.copy()

            # Same empty-cluster rescue as PhonClusterCalculator: steal
            # the worst-fit point from an overfull cluster so every k has
            # at least one member.
            counts = np.bincount(labels_v, minlength=self.n_clusters)
            empty = np.where(counts == 0)[0]
            if len(empty):
                logger.info("  Cluster: %d empty cluster(s) rescued", len(empty))
                for e in empty:
                    d = np.linalg.norm(feats - centers_tmp[labels_v], axis=1)
                    stealable = counts[labels_v] > 1
                    d = np.where(stealable, d, -1.0)
                    worst = int(np.argmax(d))
                    labels_v[worst] = e
                    centers_tmp[e] = feats[worst]
                    counts = np.bincount(labels_v, minlength=self.n_clusters)

            self.centroids_ = centers_tmp

        # Map labels to 1..k, leaving 0 for invalid cycles
        out = np.zeros(n_cycles, dtype=np.int32)
        out[valid] = labels_v.astype(np.int32) + 1

        counts = np.bincount(out[out > 0], minlength=self.n_clusters + 1)[1:]
        pct = 100.0 * counts / max(counts.sum(), 1)
        logger.info("  Cluster sizes (%%): " +
                    "  ".join(f"#{i+1}={p:.1f}" for i, p in enumerate(pct)))
        return out


# ---------------------------------------------------------------------------
# Phonation-type clustering (cPhon 1..5) — quality-metric K-means.
#
# Independent of EGG shape clustering. Takes the already-computed per-cycle
# quality metrics (clarity, CPP, specbal, crest, entropy, qcontact, deggmax,
# icontact, hrf) and clusters cycles by overall voice quality profile. Because
# these metrics have wildly different native ranges, z-score normalise first.
# Returns 1..k per cycle (0 for invalid).
# ---------------------------------------------------------------------------
class PhonClusterCalculator:
    """K-means over z-scored quality-metric vectors (one row per cycle)."""

    DEFAULT_KEYS = (
        "clarity", "cpp", "specbal", "crest", "entropy",
        "qcontact", "deggmax", "icontact", "hrf",
    )

    def __init__(self, config: VoiceMapConfig,
                 n_clusters: int = 5,
                 keys: tuple = None,
                 random_state: int = 0):
        self.config = config
        self.n_clusters = int(n_clusters)
        self.keys = tuple(keys) if keys else self.DEFAULT_KEYS
        self.random_state = int(random_state)

    def calculate(self, metrics: dict) -> np.ndarray:
        from sklearn.cluster import KMeans

        # Stack selected per-cycle metric arrays → (n_cycles, n_features)
        cols = []
        names = []
        for k in self.keys:
            v = metrics.get(k)
            if v is None or len(v) == 0:
                continue
            cols.append(np.asarray(v, dtype=np.float64))
            names.append(k)

        if not cols:
            return np.zeros(0, dtype=np.int32)

        n_min = min(len(c) for c in cols)
        feats = np.stack([c[:n_min] for c in cols], axis=1)

        logger.info("Calculating phonation clusters (k=%d, feats=%s)...",
                    self.n_clusters, ",".join(names))

        if n_min < self.n_clusters:
            logger.warning("  Too few cycles (%d < k=%d); skipping cPhon",
                           n_min, self.n_clusters)
            return np.zeros(n_min, dtype=np.int32)

        # Drop non-finite rows (any nan/inf) so KMeans doesn't choke.
        good = np.isfinite(feats).all(axis=1)
        if good.sum() < self.n_clusters:
            logger.warning("  Only %d finite rows; skipping cPhon", int(good.sum()))
            return np.zeros(n_min, dtype=np.int32)

        feats_g = feats[good]
        mu  = feats_g.mean(axis=0)
        sd  = feats_g.std(axis=0)
        sd[sd < 1e-12] = 1.0
        z   = (feats_g - mu) / sd

        # n_init=10 (sklearn default) on cPhon — raised from 3 because
        # the 9-dim z-scored feature space is small enough that K-means
        # sometimes converges with an empty cluster at n_init=3.
        # Extra cost: ~50 ms on 12k points, worth it for stable k-means.
        km = KMeans(n_clusters=self.n_clusters,
                    n_init=10, random_state=self.random_state)
        labels_g = km.fit_predict(z)

        # Empty-cluster rescue. sklearn's KMeans can legitimately leave a
        # cluster empty if its centroid never "wins" any point during
        # Lloyd's iterations. From a researcher's perspective that's a
        # missing column in the VRP. For each empty cluster we reassign
        # the single point with the LARGEST distance from its currently
        # assigned centroid — i.e. the worst-fit point moves to the empty
        # slot. Ensures every k has at least one member while minimally
        # disturbing the overall K-means solution.
        counts = np.bincount(labels_g, minlength=self.n_clusters)
        empty = np.where(counts == 0)[0]
        if len(empty):
            centers = km.cluster_centers_.copy()
            logger.info("  cPhon: %d empty cluster(s) rescued", len(empty))
            for e in empty:
                # Distance from each point to its own assigned centroid
                d = np.linalg.norm(z - centers[labels_g], axis=1)
                # Only steal from clusters that can spare a point (>1 member)
                stealable = counts[labels_g] > 1
                d = np.where(stealable, d, -1.0)
                worst = int(np.argmax(d))
                labels_g[worst] = e
                # Nudge the empty cluster's centroid to the moved point so
                # subsequent label accounting is self-consistent.
                centers[e] = z[worst]
                counts = np.bincount(labels_g, minlength=self.n_clusters)

        out = np.zeros(n_min, dtype=np.int32)
        out[good] = labels_g.astype(np.int32) + 1

        counts = np.bincount(out[out > 0], minlength=self.n_clusters + 1)[1:]
        pct = 100.0 * counts / max(counts.sum(), 1)
        logger.info("  cPhon sizes (%%):   " +
                    "  ".join(f"#{i+1}={p:.1f}" for i, p in enumerate(pct)))
        return out
