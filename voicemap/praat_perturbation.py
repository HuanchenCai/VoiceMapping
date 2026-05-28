#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Direct numpy translation of Praat's jitter / shimmer math.

Sources (Praat ≥ 6.4, GPLv3):
    fon/VoiceAnalysis.cpp     — PointProcess_getJitter_* and Praat
                                 PointProcess_Sound_getShimmer_* wrappers
    fon/AmplitudeTier.cpp     — PointProcess_Sound_to_AmplitudeTier_period
                                 (per-pulse amplitude = Hann-windowed RMS)
                                 AmplitudeTier_getShimmer_*_u  formulas
    fon/PointProcess.cpp      — PointProcess_isPeriod, getMeanPeriod

All functions in this module take a 1-D `t_points` (float seconds, cycle
mark times — i.e. what Praat calls a PointProcess) plus optional voice +
sampling rate, and return a single scalar. The PerturbationCalculator
applies them on sliding windows of cycle marks to get a per-cycle array.

The whole file is a literal translation: variable names, loop bounds and
edge-case behaviour match Praat 1:1 so that unit tests can verify the
output matches parselmouth to floating-point precision.
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Period validity (PointProcess.cpp:isPeriod)
# ---------------------------------------------------------------------------
def is_period(t_points: np.ndarray,
              ileft: int,
              pmin: float,
              pmax: float,
              max_period_factor: float) -> bool:
    """Praat's PointProcess_isPeriod.

    A period (interval between consecutive marks) is valid iff:
      • length is in [pmin, pmax]  (skipped when pmin == pmax)
      • NOT (both neighbour-interval ratios exceed max_period_factor)

    Note Praat *requires both* neighbours to violate the factor — this is
    more permissive than a per-pair check. Used only by mean/stdev period
    computations; the jitter formulas have their own narrower checks.
    """
    n = len(t_points)
    iright = ileft + 1
    if iright >= n:
        return False
    interval = t_points[iright] - t_points[ileft]
    if pmin != pmax and (interval < pmin or interval > pmax):
        return False
    if not np.isfinite(max_period_factor) or max_period_factor < 1.0:
        return True

    prev_interval = (t_points[ileft] - t_points[ileft - 1]
                     if ileft >= 1 else None)
    next_interval = (t_points[iright + 1] - t_points[iright]
                     if iright + 1 < n else None)
    pf = (interval / prev_interval) if (prev_interval and prev_interval > 0) else None
    nf = (interval / next_interval) if (next_interval and next_interval > 0) else None

    if pf is None and nf is None:
        return True
    if pf is not None and 0 < pf < 1.0:
        pf = 1.0 / pf
    if nf is not None and 0 < nf < 1.0:
        nf = 1.0 / nf
    if (pf is not None and pf > max_period_factor and
            nf is not None and nf > max_period_factor):
        return False
    return True


# ---------------------------------------------------------------------------
# Mean period (PointProcess.cpp:getMeanPeriod)
# ---------------------------------------------------------------------------
def mean_period(t_points: np.ndarray,
                pmin: float, pmax: float,
                max_period_factor: float) -> float:
    """Mean period across pulses passing is_period(). Returns NaN if
    no period qualifies — matches Praat's `undefined`."""
    if len(t_points) < 2:
        return float('nan')
    n_periods = 0
    s = 0.0
    for i in range(len(t_points) - 1):
        if is_period(t_points, i, pmin, pmax, max_period_factor):
            n_periods += 1
            s += t_points[i + 1] - t_points[i]
    return (s / n_periods) if n_periods > 0 else float('nan')


# ---------------------------------------------------------------------------
# Jitter family (VoiceAnalysis.cpp)
# ---------------------------------------------------------------------------
def jitter_local(t_points: np.ndarray,
                  pmin: float = 1e-4, pmax: float = 0.02,
                  max_period_factor: float = 1.3) -> float:
    """Praat's PointProcess_getJitter_local. Returns NaN if undefined.

    Result is the **fraction** (not %). Multiply by 100 to get % as Praat's
    voice report displays it.
    """
    n_periods = len(t_points) - 1
    if n_periods < 2:
        return float('nan')
    s = 0.0
    for i in range(1, len(t_points) - 1):
        p1 = t_points[i]     - t_points[i - 1]
        p2 = t_points[i + 1] - t_points[i]
        if p1 <= 0 or p2 <= 0:
            n_periods -= 1
            continue
        factor = (p1 / p2) if p1 > p2 else (p2 / p1)
        if pmin == pmax or (pmin <= p1 <= pmax and pmin <= p2 <= pmax
                             and factor <= max_period_factor):
            s += abs(p1 - p2)
        else:
            n_periods -= 1
    if n_periods < 2:
        return float('nan')
    mp = mean_period(t_points, pmin, pmax, max_period_factor)
    if not np.isfinite(mp) or mp <= 0:
        return float('nan')
    return (s / (n_periods - 1)) / mp


def jitter_local_absolute(t_points: np.ndarray,
                           pmin: float = 1e-4, pmax: float = 0.02,
                           max_period_factor: float = 1.3) -> float:
    """Same as jitter_local but returns the absolute jitter (in seconds)
    — no division by mean period."""
    n_periods = len(t_points) - 1
    if n_periods < 2:
        return float('nan')
    s = 0.0
    for i in range(1, len(t_points) - 1):
        p1 = t_points[i]     - t_points[i - 1]
        p2 = t_points[i + 1] - t_points[i]
        if p1 <= 0 or p2 <= 0:
            n_periods -= 1
            continue
        factor = (p1 / p2) if p1 > p2 else (p2 / p1)
        if pmin == pmax or (pmin <= p1 <= pmax and pmin <= p2 <= pmax
                             and factor <= max_period_factor):
            s += abs(p1 - p2)
        else:
            n_periods -= 1
    if n_periods < 2:
        return float('nan')
    return s / (n_periods - 1)


def jitter_rap(t_points: np.ndarray,
                pmin: float = 1e-4, pmax: float = 0.02,
                max_period_factor: float = 1.3) -> float:
    """Praat's PointProcess_getJitter_rap (3-point relative average perturbation)."""
    n_periods = len(t_points) - 1
    if n_periods < 3:
        return float('nan')
    s = 0.0
    for i in range(2, len(t_points) - 1):
        p1 = t_points[i - 1] - t_points[i - 2]
        p2 = t_points[i]     - t_points[i - 1]
        p3 = t_points[i + 1] - t_points[i]
        if p1 <= 0 or p2 <= 0 or p3 <= 0:
            n_periods -= 1
            continue
        f1 = (p1 / p2) if p1 > p2 else (p2 / p1)
        f2 = (p2 / p3) if p2 > p3 else (p3 / p2)
        if pmin == pmax or (pmin <= p1 <= pmax and pmin <= p2 <= pmax
                             and pmin <= p3 <= pmax
                             and f1 <= max_period_factor
                             and f2 <= max_period_factor):
            s += abs(p2 - (p1 + p2 + p3) / 3.0)
        else:
            n_periods -= 1
    if n_periods < 3:
        return float('nan')
    mp = mean_period(t_points, pmin, pmax, max_period_factor)
    if not np.isfinite(mp) or mp <= 0:
        return float('nan')
    return (s / (n_periods - 2)) / mp


def jitter_ppq5(t_points: np.ndarray,
                 pmin: float = 1e-4, pmax: float = 0.02,
                 max_period_factor: float = 1.3) -> float:
    """Praat's PointProcess_getJitter_ppq5 (5-point period perturbation quotient)."""
    n_periods = len(t_points) - 1
    if n_periods < 5:
        return float('nan')
    s = 0.0
    # Praat's loop:  for (i = first + 5; i <= last; i++)  using 5 backwards periods
    last = len(t_points) - 1
    for i in range(5, last + 1):
        p1 = t_points[i - 4] - t_points[i - 5]
        p2 = t_points[i - 3] - t_points[i - 4]
        p3 = t_points[i - 2] - t_points[i - 3]
        p4 = t_points[i - 1] - t_points[i - 2]
        p5 = t_points[i]     - t_points[i - 1]
        if p1 <= 0 or p2 <= 0 or p3 <= 0 or p4 <= 0 or p5 <= 0:
            n_periods -= 1
            continue
        f1 = (p1 / p2) if p1 > p2 else (p2 / p1)
        f2 = (p2 / p3) if p2 > p3 else (p3 / p2)
        f3 = (p3 / p4) if p3 > p4 else (p4 / p3)
        f4 = (p4 / p5) if p4 > p5 else (p5 / p4)
        if pmin == pmax or (pmin <= p1 <= pmax and pmin <= p2 <= pmax
                             and pmin <= p3 <= pmax and pmin <= p4 <= pmax
                             and pmin <= p5 <= pmax
                             and f1 <= max_period_factor and f2 <= max_period_factor
                             and f3 <= max_period_factor and f4 <= max_period_factor):
            s += abs(p3 - (p1 + p2 + p3 + p4 + p5) / 5.0)
        else:
            n_periods -= 1
    if n_periods < 5:
        return float('nan')
    mp = mean_period(t_points, pmin, pmax, max_period_factor)
    if not np.isfinite(mp) or mp <= 0:
        return float('nan')
    return (s / (n_periods - 4)) / mp


def jitter_ddp(t_points: np.ndarray,
                pmin: float = 1e-4, pmax: float = 0.02,
                max_period_factor: float = 1.3) -> float:
    """Praat's PointProcess_getJitter_ddp = 3 * jitter_rap."""
    rap = jitter_rap(t_points, pmin, pmax, max_period_factor)
    return 3.0 * rap if np.isfinite(rap) else float('nan')


# ---------------------------------------------------------------------------
# Per-pulse amplitude (AmplitudeTier.cpp:Sound_getHannWindowedRms)
# ---------------------------------------------------------------------------
def sound_find_maximum_correlation(voice: np.ndarray, fs: float,
                                     t1: float,
                                     window_length: float,
                                     tmin2: float, tmax2: float
                                     ) -> tuple[float, float, float]:
    """Direct translation of Praat's `Sound_findMaximumCorrelation`
    (fon/Pitch_to_PointProcess.cpp:163).

    For a window of duration `window_length` centred at `t1`, slide a
    same-sized window through the search range [tmin2, tmax2] and report
    the position `tout` whose window has the highest normalized
    cross-correlation with the template at `t1`.

    Returns
    -------
    max_correlation : float
        Peak normalized cross-correlation (parabolic-interpolated).
        −1.0 if no valid offset was found.
    tout : float
        Subsample time of the best-correlated window centre.
    peak : float
        Largest absolute voice amplitude inside the best-correlated window
        (used by Praat for the `peak > 0.01 * globalPeak` validity gate).
    """
    half_window = 0.5 * window_length
    dx = 1.0 / fs
    x1 = 0.5 * dx                                # sample-centre convention
    N = len(voice)

    # Praat helpers (0-indexed Python equivalents):
    def _nearest(t):
        return int(round((t - x1) / dx))
    def _low(t):
        return int(np.floor((t - x1) / dx))
    def _high(t):
        return int(np.ceil((t - x1) / dx))

    ileft1 = _nearest(t1 - half_window)
    iright1 = _nearest(t1 + half_window)
    ileft2min = _low(tmin2 - half_window)
    ileft2max = _high(tmax2 - half_window)
    if ileft2max < ileft2min or iright1 <= ileft1:
        return -1.0, t1, 0.0

    W = iright1 - ileft1 + 1   # window length in samples

    # Build correlation array via vectorized stride view, with bounds clipped.
    # Out-of-range samples in template / candidate are masked rather than
    # set to zero — matches Praat's `if (i < 1 || i > nx) continue;`
    r_arr = np.full(ileft2max - ileft2min + 1, -2.0, dtype=np.float64)
    peak_arr = np.zeros(ileft2max - ileft2min + 1, dtype=np.float64)

    for k, ileft2 in enumerate(range(ileft2min, ileft2max + 1)):
        i1_range = np.arange(ileft1, iright1 + 1)
        i2_range = np.arange(ileft2, ileft2 + W)
        valid = (i1_range >= 0) & (i1_range < N) & (i2_range >= 0) & (i2_range < N)
        if not valid.any():
            r_arr[k] = 0.0
            continue
        a1 = voice[i1_range[valid]]
        a2 = voice[i2_range[valid]]
        norm1 = float(np.sum(a1 * a1))
        norm2 = float(np.sum(a2 * a2))
        if norm1 == 0.0 or norm2 == 0.0:
            r_arr[k] = 0.0
        else:
            r_arr[k] = float(np.sum(a1 * a2) / np.sqrt(norm1 * norm2))
        peak_arr[k] = float(np.max(np.abs(a2)))

    # Praat picks a local maximum where r[i] >= r[i-1] and r[i] >= r[i+1],
    # tracking r1 (previous), r2 (current), r3 (next). It writes results
    # at the FIRST such qualified peak found (since the condition is
    # checked against `> maximumCorrelation`). Replicate:
    max_corr = -1.0
    best_k = -1
    r1_best = r3_best = 0.0
    for k in range(1, len(r_arr) - 1):
        r1, r2, r3 = r_arr[k - 1], r_arr[k], r_arr[k + 1]
        if r2 > max_corr and r2 >= r1 and r2 >= r3:
            max_corr = r2
            r1_best = r1
            r3_best = r3
            best_k = k

    if best_k < 0:
        return -1.0, t1, 0.0

    ir = float(ileft2min + best_k)   # integer best offset
    interpolated_peak = max_corr

    d2r = (max_corr - r1_best) + (max_corr - r3_best)
    if d2r != 0.0:
        dr = 0.5 * (r3_best - r1_best)
        interpolated_peak = max_corr + 0.5 * dr * dr / d2r
        ir += dr / d2r

    peak_time = t1 + (ir - ileft1) * dx
    peak_amp = float(peak_arr[best_k])
    if tmin2 <= peak_time <= tmax2:
        return interpolated_peak, peak_time, peak_amp

    # Out-of-range: Praat falls back to the geometric-mean midpoint
    mid_dist = np.sqrt(max((tmin2 - t1) * (tmax2 - t1), 0.0))
    mid_time = (t1 - mid_dist) if tmin2 < t1 else (t1 + mid_dist)
    return max_corr, mid_time, peak_amp


def refine_cycle_marks_praat_cc(voice: np.ndarray, fs: float,
                                 seed_idx: np.ndarray,
                                 ) -> np.ndarray:
    """Refine integer cycle-mark seeds via Praat's cc cross-correlation
    pipeline. Each pulse is moved to the position of best xcorr alignment
    with its previous pulse, using Praat's exact `Sound_findMaximumCorrelation`
    parameters (window = 1/f0, search range = [t + 0.8/f0, t + 1.25/f0]).

    The first seed is anchored unchanged (acts as the recursion base).
    The local F0 used for each step's window is estimated from the
    current refined position and the next seed: `f0 ≈ fs / (seed[i+1] - refined[i-1]) * 2`.

    Returns
    -------
    refined_t : (N,) float64
        Refined cycle-mark times in seconds.
    """
    n = len(seed_idx)
    if n < 2:
        return seed_idx.astype(np.float64) / fs
    refined_t = np.empty(n, dtype=np.float64)
    refined_t[0] = float(seed_idx[0]) / fs

    for i in range(1, n):
        prev_t = refined_t[i - 1]
        # F0 estimate at this position — use 2× the gap between the
        # previous refined point and the next seed (a centred local F0).
        if i + 1 < n:
            local_period = (seed_idx[i + 1] - seed_idx[i - 1]) / (2.0 * fs)
        else:
            local_period = (seed_idx[i] - seed_idx[i - 1]) / fs
        if local_period <= 0:
            refined_t[i] = float(seed_idx[i]) / fs
            continue
        f0 = 1.0 / local_period

        # Praat: search for next pulse in [prev_t + 0.8/f0, prev_t + 1.25/f0]
        # with windowLength = 1/f0.
        corr, t_new, _peak = sound_find_maximum_correlation(
            voice, fs, prev_t, 1.0 / f0,
            prev_t + 0.8 / f0, prev_t + 1.25 / f0)
        if corr < -0.5 or not np.isfinite(t_new):
            refined_t[i] = float(seed_idx[i]) / fs
        else:
            refined_t[i] = t_new

    return refined_t


def hann_windowed_rms(voice: np.ndarray, fs: float,
                       t_mid: float,
                       width_left: float,
                       width_right: float) -> float:
    """Praat's Sound_getHannWindowedRms. Returns NaN if window too small.

    Sample times follow Praat's Sampled convention: sample i (0-indexed)
    is centred at t = x1 + i·dx where x1 = 0.5·dx (each sample sits at the
    centre of its dx interval, so a Sound with start_time = 0 has its
    first sample at t = 0.5/fs, not 0). Using i/fs instead introduces a
    ~0.14 % systematic amplitude bias that breaks shimmer parity.
    """
    dx = 1.0 / fs
    x1 = 0.5 * dx
    t_start = t_mid - width_left
    t_end = t_mid + width_right
    # Sampled_getWindowSamples: imin = ceil((tmin - x1)/dx), imax = floor((tmax - x1)/dx)
    i_min = int(np.ceil((t_start - x1) / dx))
    i_max = int(np.floor((t_end - x1) / dx))
    i_min = max(0, i_min)
    i_max = min(len(voice) - 1, i_max)
    if i_max - i_min + 1 < 3:
        return float('nan')

    idx = np.arange(i_min, i_max + 1, dtype=np.int64)
    t = x1 + idx.astype(np.float64) * dx
    width = np.where(t < t_mid, width_left, width_right)
    width = np.maximum(width, 1e-12)
    phase = (t - t_mid) / width            # ∈ [-1, 1]
    win = 0.5 + 0.5 * np.cos(np.pi * phase)
    v_w = voice[idx] * win
    win_ss = float(np.sum(win * win))
    if win_ss <= 0:
        return float('nan')
    return float(np.sqrt(np.sum(v_w * v_w) / win_ss))


def point_process_to_amplitude_tier(t_points: np.ndarray,
                                     voice: np.ndarray, fs: float,
                                     pmin: float = 1e-4, pmax: float = 0.02,
                                     max_period_factor: float = 1.3
                                     ) -> tuple[np.ndarray, np.ndarray]:
    """Praat's PointProcess_Sound_to_AmplitudeTier_period.

    For each interior pulse (not first or last), compute Hann-windowed RMS
    on the voice with asymmetric window [0.2·p1, 0.2·p2] where p1, p2 are
    the preceding and following periods. Only pulses where both p1 and p2
    pass the period bounds + factor checks are kept.

    Returns
    -------
    times : (M,) float64
        Pulse times (subset of t_points).
    values : (M,) float64
        Hann-windowed RMS amplitude at each kept pulse.
    """
    n = len(t_points)
    if n < 3:
        return np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)
    times = []
    values = []
    for i in range(1, n - 1):
        p1 = t_points[i]     - t_points[i - 1]
        p2 = t_points[i + 1] - t_points[i]
        if p1 <= 0 or p2 <= 0:
            continue
        factor = (p1 / p2) if p1 > p2 else (p2 / p1)
        if pmin == pmax or (pmin <= p1 <= pmax and pmin <= p2 <= pmax
                             and factor <= max_period_factor):
            peak = hann_windowed_rms(voice, fs, t_points[i],
                                     0.2 * p1, 0.2 * p2)
            if np.isfinite(peak) and peak > 0.0:
                times.append(t_points[i])
                values.append(peak)
    return (np.asarray(times, dtype=np.float64),
            np.asarray(values, dtype=np.float64))


# ---------------------------------------------------------------------------
# Shimmer family (AmplitudeTier.cpp)
# Each takes the (times, values) tuple from point_process_to_amplitude_tier.
# ---------------------------------------------------------------------------
def shimmer_local(amp_times: np.ndarray, amp_values: np.ndarray,
                   pmin: float = 1e-4, pmax: float = 0.02,
                   max_amplitude_factor: float = 1.6) -> float:
    """Praat AmplitudeTier_getShimmer_local_u. Returns fraction (×100 for %)."""
    n = len(amp_values)
    if n < 2:
        return float('nan')
    # Numerator: mean of |a1 - a2| over accepted adjacent pulse pairs
    numer_sum = 0.0
    n_accepted = 0
    for i in range(1, n):
        p = amp_times[i] - amp_times[i - 1]
        if pmin != pmax and not (pmin <= p <= pmax):
            continue
        a1, a2 = amp_values[i - 1], amp_values[i]
        if a1 <= 0 or a2 <= 0:
            continue
        af = (a1 / a2) if a1 > a2 else (a2 / a1)
        if af <= max_amplitude_factor:
            numer_sum += abs(a1 - a2)
            n_accepted += 1
    if n_accepted < 1:
        return float('nan')
    numerator = numer_sum / n_accepted
    # Denominator: mean of ALL amplitudes — Praat's `for i = 1; i < size; i++`
    # iterates indices 1..size-1, i.e. excludes the last point.
    denom = float(np.mean(amp_values[:-1])) if n >= 2 else 0.0
    if denom == 0.0:
        return float('nan')
    return numerator / denom


def shimmer_local_dB(amp_times: np.ndarray, amp_values: np.ndarray,
                      pmin: float = 1e-4, pmax: float = 0.02,
                      max_amplitude_factor: float = 1.6) -> float:
    """Praat AmplitudeTier_getShimmer_local_dB_u. Returns dB directly."""
    n = len(amp_values)
    if n < 2:
        return float('nan')
    s = 0.0
    n_accepted = 0
    for i in range(1, n):
        p = amp_times[i] - amp_times[i - 1]
        if pmin != pmax and not (pmin <= p <= pmax):
            continue
        a1, a2 = amp_values[i - 1], amp_values[i]
        if a1 <= 0 or a2 <= 0:
            continue
        af = (a1 / a2) if a1 > a2 else (a2 / a1)
        if af <= max_amplitude_factor:
            s += abs(np.log10(a1 / a2))
            n_accepted += 1
    if n_accepted < 1:
        return float('nan')
    return float(20.0 * s / n_accepted)


def _shimmer_apq_n(amp_times: np.ndarray, amp_values: np.ndarray,
                    n_pts: int,
                    pmin: float, pmax: float,
                    max_amplitude_factor: float) -> float:
    """Generic n-point Amplitude Perturbation Quotient (Praat APQ3/5/11).

    For APQ_n, n is the window size centred at the target pulse. Praat
    iterates such that the window of n consecutive amplitudes around
    pulse `i` is checked, and contributes |a_center - mean(a_window)|
    to the numerator. All n-1 interior period intervals AND all n-1
    amplitude ratios in the window must pass the period / amplitude
    factor checks.
    """
    if n_pts % 2 != 1:
        raise ValueError("APQ window size must be odd")
    half = n_pts // 2
    n = len(amp_values)
    if n < n_pts:
        return float('nan')
    # Praat loops i from `half + 1` to `n_amplitudes - half` (1-based);
    # in 0-based Python, i in [half .. n - 1 - half].
    numer_sum = 0.0
    n_accepted = 0
    for i in range(half, n - half):
        win_amps = amp_values[i - half: i + half + 1]
        win_times = amp_times[i - half: i + half + 1]
        # Period intervals between consecutive window pulses
        periods = np.diff(win_times)
        if np.any(periods <= 0):
            continue
        if pmin != pmax:
            if np.any(periods < pmin) or np.any(periods > pmax):
                continue
        # Amplitude factor checks between adjacent pulses in window
        a1 = win_amps[:-1]
        a2 = win_amps[1:]
        with np.errstate(divide='ignore', invalid='ignore'):
            factors = np.where(a1 > a2, a1 / np.maximum(a2, 1e-15),
                                          a2 / np.maximum(a1, 1e-15))
        if np.any(factors > max_amplitude_factor) or np.any(a1 <= 0) or np.any(a2 <= 0):
            continue
        n_avg = float(np.mean(win_amps))
        numer_sum += abs(amp_values[i] - n_avg)
        n_accepted += 1
    if n_accepted < 1:
        return float('nan')
    numerator = numer_sum / n_accepted
    denom = float(np.mean(amp_values[:-1])) if n >= 2 else 0.0
    if denom == 0.0:
        return float('nan')
    return numerator / denom


def shimmer_apq3(amp_times, amp_values, pmin=1e-4, pmax=0.02,
                 max_amplitude_factor=1.6) -> float:
    return _shimmer_apq_n(amp_times, amp_values, 3, pmin, pmax,
                          max_amplitude_factor)


def shimmer_apq5(amp_times, amp_values, pmin=1e-4, pmax=0.02,
                 max_amplitude_factor=1.6) -> float:
    return _shimmer_apq_n(amp_times, amp_values, 5, pmin, pmax,
                          max_amplitude_factor)


def shimmer_apq11(amp_times, amp_values, pmin=1e-4, pmax=0.02,
                  max_amplitude_factor=1.6) -> float:
    return _shimmer_apq_n(amp_times, amp_values, 11, pmin, pmax,
                          max_amplitude_factor)


def shimmer_dda(amp_times, amp_values, pmin=1e-4, pmax=0.02,
                max_amplitude_factor=1.6) -> float:
    """Praat: shimmer_dda = 3 * shimmer_apq3."""
    apq3 = shimmer_apq3(amp_times, amp_values, pmin, pmax, max_amplitude_factor)
    return 3.0 * apq3 if np.isfinite(apq3) else float('nan')
