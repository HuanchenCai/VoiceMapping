#!/usr/bin/env python3
"""
VoiceMap Metrics Module — Optimized
All hot paths use vectorised NumPy; no Python-level loops over samples or windows.
"""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.signal import butter, sosfilt, lfilter
from scipy.fft import rfft, irfft, ifft as _ifft
from typing import Tuple
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
