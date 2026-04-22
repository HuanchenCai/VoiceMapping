#!/usr/bin/env python3
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

from config import VoiceMapConfig

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
class FormantCalculator(MetricCalculator):
    """Per-cycle F1, F2, F3 (Hz) + Singer's Formant Energy (dB)."""

    def __init__(self, config: VoiceMapConfig,
                 lpc_order: Optional[int] = None,
                 win_ms: float = 25.0, hop_ms: float = 10.0,
                 f_min: float = 90.0, f_max: float = 5500.0,
                 f1_floor: float = 250.0,
                 singer_band: Tuple[float, float] = (2800.0, 3400.0),
                 pre_emphasis: float = 0.97):
        super().__init__(config)
        self.win_ms, self.hop_ms = float(win_ms), float(hop_ms)
        self.f_min,  self.f_max  = float(f_min),  float(f_max)
        self.f1_floor     = float(f1_floor)
        self.singer_band  = (float(singer_band[0]), float(singer_band[1]))
        self.pre_emphasis = float(pre_emphasis)
        # LPC order: Praat's classical autocorrelation/Burg formula
        #   order ≈ 2 + 2·Fs/1000   (→ 22 @ 44.1 kHz)
        # captures the right amount of spectral detail for our peak-picking
        # tracker. We DO need to gate sub-F1 peaks (pitch harmonics) with
        # `f1_floor` below, or the first low LPC peak gets mislabelled as F1
        # and drags F2/F3 with it.
        self.lpc_order    = int(lpc_order or (2 + 2 * config.sample_rate // 1000))

    def calculate(self, voice: np.ndarray,
                  cycle_triggers: np.ndarray) -> Dict[str, np.ndarray]:
        from scipy.signal import find_peaks
        logger.info("Calculating formants (LPC order=%d) + SFE...", self.lpc_order)

        idx = np.where(cycle_triggers > 0.5)[0]
        n_cycles = max(len(idx) - 1, 0)
        z = lambda: np.zeros(n_cycles)
        keys = ("f1", "f2", "f3", "sfe")
        if n_cycles == 0:
            return {k: z() for k in keys}

        sr  = self.sample_rate
        win = int(self.win_ms * 0.001 * sr)
        hop = int(self.hop_ms * 0.001 * sr)
        if len(voice) < win or hop < 1:
            return {k: z() for k in keys}

        # Pre-emphasis (HPF boost; matters a lot for LPC accuracy)
        voice_pe = np.empty_like(voice)
        voice_pe[0]  = voice[0]
        voice_pe[1:] = voice[1:] - self.pre_emphasis * voice[:-1]

        # Frame up
        n_frames = 1 + (len(voice_pe) - win) // hop
        starts   = np.arange(n_frames) * hop
        frames   = sliding_window_view(voice_pe, win)[starts]    # (n_frames, win)
        hamm     = np.hamming(win)
        frames_w = (frames - frames.mean(axis=1, keepdims=True)) * hamm

        # --- LPC via batched autocorrelation + Levinson-Durbin (np.linalg.solve) ---
        p = self.lpc_order
        nfft_ac = 1
        while nfft_ac < 2 * win:
            nfft_ac *= 2
        X_ac = np.fft.rfft(frames_w, nfft_ac, axis=1)
        acf  = np.fft.irfft(X_ac * np.conj(X_ac), nfft_ac, axis=1)[:, :p + 1]

        valid = acf[:, 0] > 1e-12
        lpc = np.zeros((n_frames, p + 1))
        lpc[:, 0] = 1.0
        if valid.any():
            # Toeplitz matrix per valid frame, then batched solve
            ij   = np.arange(p)[:, None] - np.arange(p)[None, :]
            R    = acf[valid][:, np.abs(ij)]                     # (m, p, p)
            rhs  = -acf[valid, 1:p + 1, None]
            try:
                a_sol = np.linalg.solve(R, rhs)[..., 0]          # (m, p)
                lpc[valid, 1:] = a_sol
            except np.linalg.LinAlgError:
                logger.warning("  LPC batch solve singular; falling back per-frame")
                for f in np.where(valid)[0]:
                    try:
                        R_f = acf[f, np.abs(ij)]
                        lpc[f, 1:] = np.linalg.solve(R_f, -acf[f, 1:p + 1])
                    except np.linalg.LinAlgError:
                        pass

        # --- LPC spectrum magnitude → per-frame peaks → F1/F2/F3 ---
        nfft_sp  = 1024
        A        = np.fft.rfft(lpc, nfft_sp, axis=1)
        H        = 1.0 / np.maximum(np.abs(A), 1e-12)
        freqs_sp = np.fft.rfftfreq(nfft_sp, 1.0 / sr)
        band     = (freqs_sp >= self.f_min) & (freqs_sp <= self.f_max)
        freqs_band = freqs_sp[band]
        min_peak_gap = max(1, int(150.0 / (sr / nfft_sp)))   # ≥ 150 Hz between peaks

        f1 = np.zeros(n_frames)
        f2 = np.zeros(n_frames)
        f3 = np.zeros(n_frames)
        for i in range(n_frames):
            if not valid[i]:
                continue
            spec = H[i, band]
            pk, _ = find_peaks(spec, distance=min_peak_gap)
            if len(pk) == 0:
                continue
            pf = freqs_band[pk]
            # Drop peaks below the F1 floor — these are subharmonic / low-
            # frequency LPC artifacts that would hijack the F1 slot and
            # pull the whole formant vector down (ours diverged from Praat
            # by ~25% before this gate was added).
            pf = pf[pf >= self.f1_floor]
            # Already ascending because freqs_band is monotonic
            if len(pf) >= 1: f1[i] = pf[0]
            if len(pf) >= 2: f2[i] = pf[1]
            if len(pf) >= 3: f3[i] = pf[2]

        # --- Singer's Formant Energy: signal-FFT power ratio (dB) ---
        nfft_sfe   = 2048
        X_sfe      = np.fft.rfft(frames_w, nfft_sfe, axis=1)
        power      = (np.abs(X_sfe)) ** 2
        freqs_sfe  = np.fft.rfftfreq(nfft_sfe, 1.0 / sr)
        sfe_mask   = (freqs_sfe >= self.singer_band[0]) & (freqs_sfe <= self.singer_band[1])
        total_pow  = power.sum(axis=1)
        band_pow   = power[:, sfe_mask].sum(axis=1)
        ratio      = band_pow / np.maximum(total_pow, 1e-15)
        sfe_db     = 10.0 * np.log10(np.maximum(ratio, 1e-6))

        # Assign each cycle to its enclosing frame
        cycle_starts = idx[:-1]
        frame_idx    = np.clip(cycle_starts // hop, 0, n_frames - 1)

        out = {
            "f1":  f1[frame_idx],
            "f2":  f2[frame_idx],
            "f3":  f3[frame_idx],
            "sfe": sfe_db[frame_idx],
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
        "shimmer_local", "shimmer_db",  "shimmer_apq11",
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
            "shimmer_apq11": shimmer_apq11,
        }


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
            self.centroids_ = km.cluster_centers_.copy()

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

        km = KMeans(n_clusters=self.n_clusters,
                    n_init=3, random_state=self.random_state)
        labels_g = km.fit_predict(z)

        out = np.zeros(n_min, dtype=np.int32)
        out[good] = labels_g.astype(np.int32) + 1

        counts = np.bincount(out[out > 0], minlength=self.n_clusters + 1)[1:]
        pct = 100.0 * counts / max(counts.sum(), 1)
        logger.info("  cPhon sizes (%%):   " +
                    "  ".join(f"#{i+1}={p:.1f}" for i, p in enumerate(pct)))
        return out
