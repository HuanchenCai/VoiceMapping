#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Direct numpy translation of Praat's Sound_to_Pitch.cpp (AC_HANNING method).

This is a phased port — each commit narrows numerical parity with parselmouth:

  Commit 1 (this file's initial state):
    - FFT-based per-frame autocorrelation
    - Hanning window + windowR bias correction
    - Parabolic peak interpolation → F0 candidate frequencies
    - Returns list of (F0, strength) per frame
    NOT YET: sinc(x)/x precision refinement (commit 2), Viterbi path
    finder (commit 3).

  Commit 2 (planned):
    - NUM_interpolate_sinc (30-point sinc) for strength precision
    - NUMimproveMaximum-equivalent peak refinement

  Commit 3 (planned):
    - Pitch_pathFinder (Viterbi DP over candidates with octave / voicing
      / unvoiced-step costs)
    - Pitch object equivalent with getVoicedIntervalAfter, getValueAtTime

  Commit 4 (planned):
    - Wire into PerturbationCalculator: voice-derived cycle marks (Praat
      cc PointProcess) replace EGG triggers, giving full Praat numerical
      parity for jitter/shimmer.

DEFERRED (recorded in TASK #11):
  - AC_GAUSS method (Gaussian window, ~2× length, sinc-700 interpolation)
  - FCC_NORMAL / FCC_ACCURATE methods (forward cross-correlation)
  - veryAccurate=True option

Source: praat/fon/Sound_to_Pitch.cpp (Boersma 1993 method).
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Pre-computed analysis parameters
# ---------------------------------------------------------------------------
class PitchAnalysisSetup:
    """Frame-invariant constants computed once per (signal length, fs,
    pitch_floor, pitch_ceiling) configuration. Caching them across frames
    saves ~30 % runtime since the FFT size, window, and windowR don't
    change per frame."""

    def __init__(self, fs: float,
                  pitch_floor: float,
                  pitch_ceiling: float,
                  periods_per_window: float = 3.0,
                  interpolation_depth: float = 0.5,
                  ):
        # Praat clips ceiling at Nyquist
        pitch_ceiling = min(pitch_ceiling, 0.5 * fs)

        self.fs = float(fs)
        self.dx = 1.0 / self.fs
        self.pitch_floor = float(pitch_floor)
        self.pitch_ceiling = float(pitch_ceiling)
        self.periods_per_window = float(periods_per_window)

        # Window: 3 longest-period durations (for AC_HANNING)
        dt_window = periods_per_window / pitch_floor
        nsamp_window = int(np.floor(dt_window * fs))
        # Praat: halfnsamp = nsamp//2 - 1; nsamp = halfnsamp * 2 (force even
        # and symmetric around the centre)
        halfnsamp_window = nsamp_window // 2 - 1
        if halfnsamp_window < 2:
            raise ValueError("Analysis window too short — pitch_floor too high "
                             "or signal sample rate too low.")
        nsamp_window = halfnsamp_window * 2
        self.nsamp_window = nsamp_window
        self.halfnsamp_window = halfnsamp_window
        self.dt_window = dt_window

        # Longest period samples (for local mean / peak / DC-zone context)
        self.nsamp_period = int(np.floor(fs / pitch_floor))
        self.halfnsamp_period = self.nsamp_period // 2 + 1

        # Lag bounds in autocorrelation
        self.minimumLag = max(2, int(np.floor(fs / pitch_ceiling)))
        self.maximumLag = min(int(np.floor(nsamp_window / periods_per_window)) + 2,
                              nsamp_window)

        # FFT size: next power of 2 ≥ nsamp_window * (1 + interpolation_depth)
        target = nsamp_window * (1 + interpolation_depth)
        nsampFFT = 1
        while nsampFFT < target:
            nsampFFT *= 2
        self.nsampFFT = nsampFFT
        self.interpolation_depth = interpolation_depth
        self.brent_ixmax = int(np.floor(nsamp_window * interpolation_depth))

        # Hanning window (Praat: 0.5 - 0.5*cos(2π·i/(nsamp+1)) for i=1..nsamp)
        i_vals = np.arange(1, nsamp_window + 1, dtype=np.float64)
        self.window = (0.5 - 0.5 * np.cos(2.0 * np.pi * i_vals
                                            / (nsamp_window + 1)))

        # WindowR = normalized autocorrelation of the Hanning window itself.
        # Used to remove the window's intrinsic correlation falloff so r[i]
        # reflects only the signal's pitch periodicity. Praat 0-indexed:
        # windowR[0] = 1 by construction; windowR[i] = ifft(|fft(window)|²)[i] / windowR[0]
        win_padded = np.zeros(nsampFFT, dtype=np.float64)
        win_padded[:nsamp_window] = self.window
        Win = np.fft.rfft(win_padded)
        WinPower = (Win.conj() * Win).real
        winR = np.fft.irfft(WinPower, n=nsampFFT)
        # Normalize so winR[0] = 1
        if winR[0] > 0:
            winR = winR / winR[0]
        self.windowR = winR  # length nsampFFT

    # Convenience: time-grid like Sampled_shortTermAnalysis
    def frame_times(self, signal_length_samples: int,
                    time_step: float | None = None) -> np.ndarray:
        """Where to centre analysis frames.

        time_step default = window/4 (75 % overlap), matching Praat's
        `dt = periodsPerWindow / pitchFloor / 4` when `dt <= 0`.

        Frames are positioned symmetrically inside the signal: the first
        frame is offset so that integer (numberOfFrames) frames fit fully.
        """
        if time_step is None or time_step <= 0:
            time_step = self.dt_window / 4.0
        duration = signal_length_samples / self.fs
        # Need at least one full window per frame; first frame centre must
        # be ≥ window/2, last must be ≤ duration - window/2.
        usable = duration - self.dt_window
        if usable <= 0:
            return np.zeros(0)
        n_frames = int(np.floor(usable / time_step)) + 1
        # Symmetric centring like Sampled_shortTermAnalysis
        t1 = 0.5 * (duration - (n_frames - 1) * time_step)
        return t1 + np.arange(n_frames) * time_step


# ---------------------------------------------------------------------------
# Single-frame analysis
# ---------------------------------------------------------------------------
def autocorrelation_frame(voice: np.ndarray, t_centre: float,
                           setup: PitchAnalysisSetup,
                           ) -> tuple[np.ndarray, float, float]:
    """Compute Praat-style windowR-corrected autocorrelation `r[0..brent_ixmax]`
    for a single frame centred at `t_centre`.

    Returns
    -------
    r : (brent_ixmax + 1,) float64
        Normalised autocorrelation per lag (in samples). r[0] = 1.
    local_peak : float
        |voice| peak inside the central ±half-period window — used by Praat
        to compute frame intensity and gate voiceless detection.
    local_mean : float
        Mean of voice over ±1 longest period around the frame centre,
        subtracted before windowing.
    """
    fs = setup.fs
    n_voice = len(voice)
    nsamp_window = setup.nsamp_window
    halfnsamp_window = setup.halfnsamp_window
    nsamp_period = setup.nsamp_period
    halfnsamp_period = setup.halfnsamp_period
    nsampFFT = setup.nsampFFT
    brent_ixmax = setup.brent_ixmax

    # Praat 1-indexed leftSample = floor((t-x1)/dx) + 1 (x1 = 0.5*dx) ;
    # 0-indexed: i_left = floor(t*fs - 0.5)
    i_left = int(np.floor(t_centre * fs - 0.5))
    # Window samples [i_left + 1 - half, i_left + half]  (inclusive)
    s_start = i_left + 1 - halfnsamp_window
    s_end_excl = s_start + nsamp_window
    # Local-mean window [i_left + 1 - period, i_left + period]
    m_start = i_left + 1 - nsamp_period
    m_end_excl = m_start + 2 * nsamp_period
    if s_start < 0 or s_end_excl > n_voice or m_start < 0 or m_end_excl > n_voice:
        # Frame too close to signal edge → return all-zero r (voiceless)
        r = np.zeros(brent_ixmax + 1)
        r[0] = 1.0
        return r, 0.0, 0.0

    local_mean = float(np.mean(voice[m_start: m_end_excl]))
    seg = voice[s_start: s_end_excl] - local_mean

    # Local peak: ±half period around the WINDOW centre, in window-local
    # coordinates (sample 0..nsamp_window-1).
    lp_start = max(0, halfnsamp_window - halfnsamp_period)
    lp_end_excl = min(nsamp_window, halfnsamp_window + halfnsamp_period)
    local_peak = float(np.max(np.abs(seg[lp_start: lp_end_excl])))

    # Window + zero-pad
    frame = np.zeros(nsampFFT, dtype=np.float64)
    frame[:nsamp_window] = seg * setup.window

    # FFT-based autocorrelation via power spectrum
    X = np.fft.rfft(frame)
    power = (X.conj() * X).real
    ac = np.fft.irfft(power, n=nsampFFT)

    # Normalise by ac[0] (energy) AND by windowR[i] (window's own autocorrelation)
    r = np.zeros(brent_ixmax + 1, dtype=np.float64)
    r[0] = 1.0
    if ac[0] > 0.0:
        denom = ac[0] * setup.windowR[1: brent_ixmax + 1]
        with np.errstate(divide='ignore', invalid='ignore'):
            r[1:] = ac[1: brent_ixmax + 1] / denom
        r[1:] = np.where(np.isfinite(r[1:]), r[1:], 0.0)
    return r, local_peak, local_mean


# ---------------------------------------------------------------------------
# Candidate extraction (parabolic interpolation — sinc(x)/x refinement
# is added in commit 2).
# ---------------------------------------------------------------------------
def find_candidates_parabolic(r: np.ndarray,
                               setup: PitchAnalysisSetup,
                               voicing_threshold: float = 0.45,
                               octave_cost: float = 0.01,
                               max_n_candidates: int = 15,
                               ) -> list[tuple[float, float]]:
    """Pick up to `max_n_candidates` local maxima of `r` in the lag range
    [minimumLag, maximumLag], with parabolic-interpolated F0 and strength.

    The first candidate is always voiceless (F0=0, strength=0), as in Praat.
    When more peaks are found than slots, the weakest one is replaced
    using `localStrength = strength - octaveCost·log2(pitch_floor/F)` so
    Praat's high-frequency bias is preserved.
    """
    candidates: list[tuple[float, float]] = [(0.0, 0.0)]   # voiceless first
    minLag = setup.minimumLag
    maxLag = min(setup.maximumLag, setup.brent_ixmax)
    fs = setup.fs
    threshold = 0.5 * voicing_threshold

    if maxLag <= minLag:
        return candidates

    for i in range(max(1, minLag), maxLag):
        ri = r[i]
        if ri <= threshold:
            continue
        if not (ri > r[i - 1] and ri >= r[i + 1]):
            continue
        # Parabolic interpolation
        dr = 0.5 * (r[i + 1] - r[i - 1])
        d2r = (ri - r[i - 1]) + (ri - r[i + 1])
        if d2r <= 0.0:
            continue
        lag_subsample = i + dr / d2r
        if lag_subsample <= 0:
            continue
        F0_cand = fs / lag_subsample
        if F0_cand < setup.pitch_floor or F0_cand > setup.pitch_ceiling:
            continue
        strength = ri + 0.5 * dr * dr / d2r
        if strength > 1.0:
            strength = 1.0 / strength

        if len(candidates) < max_n_candidates:
            candidates.append((F0_cand, strength))
        else:
            # Find weakest using octave-cost-adjusted score
            weakest_idx = -1
            weakest_score = 2.0
            for j in range(1, len(candidates)):
                F_j, S_j = candidates[j]
                if F_j <= 0:
                    continue
                local_strength = S_j - octave_cost * np.log2(
                    setup.pitch_floor / F_j)
                if local_strength < weakest_score:
                    weakest_score = local_strength
                    weakest_idx = j
            # Replace only if new candidate beats weakest score
            new_local_strength = strength - octave_cost * np.log2(
                setup.pitch_floor / F0_cand)
            if weakest_idx > 0 and new_local_strength > weakest_score:
                candidates[weakest_idx] = (F0_cand, strength)

    return candidates


# ---------------------------------------------------------------------------
# Sinc interpolation (commit 2 — Praat's NUM_interpolate_sinc with RAISED_COSINE
# window) + Brent search for maximum refinement (NUMimproveMaximum).
# Source: praat/melder/NUMinterpol.cpp.
# ---------------------------------------------------------------------------
def sinc_interpolate_raised_cosine(y: np.ndarray, x: float,
                                     max_depth: int) -> float:
    """Praat-style sinc interpolation with raised-cosine window.

    Computes y(x) where x is a fractional 0-indexed position into y, using:
        y(x) = Σ y[i] · sinc(x - i) · 0.5 · (1 + cos(π(x - i)/(maxDepth + 0.5)))
    summed over i ∈ [midright - maxDepth, midleft + maxDepth].

    Matches Praat's RAISED_COSINE branch (NUMinterpol.cpp line 143-228).
    """
    n = len(y)
    if n < 1:
        return float('nan')
    if x < 0.0:
        return float(y[0])
    if x > n - 1:
        return float(y[-1])
    midleft = int(np.floor(x))
    if x == float(midleft):
        return float(y[midleft])
    midright = midleft + 1

    # Clip depth to fit in array
    max_depth = min(max_depth, midright)         # so left ≥ 0
    max_depth = min(max_depth, n - 1 - midleft)  # so right ≤ n - 1
    if max_depth <= 0:
        # Fall back to linear interp
        return float(y[midleft] + (x - midleft) * (y[midright] - y[midleft]))

    left = midright - max_depth
    right = midleft + max_depth
    i_arr = np.arange(left, right + 1, dtype=np.float64)
    delta = x - i_arr                  # may be ≠ 0 because x is not integer
    pi_delta = np.pi * delta
    sinc = np.sin(pi_delta) / pi_delta
    win_depth = max_depth + 0.5
    win = 0.5 * (1.0 + np.cos(np.pi * delta / win_depth))
    return float(np.sum(y[left: right + 1] * sinc * win))


def improve_maximum_sinc(y: np.ndarray, ix_mid: int,
                          depth: int = 70) -> tuple[float, float]:
    """Praat's NUMimproveMaximum: Brent search for the maximum of the
    sinc-interpolated y curve near integer index ix_mid.

    Returns
    -------
    y_max : float
        Refined peak height (sinc-interpolated).
    x_max : float
        Subsample position where the peak occurs (in y's 0-based indexing).
    """
    n = len(y)
    if ix_mid <= 0:
        return float(y[0]), 0.0
    if ix_mid >= n - 1:
        return float(y[-1]), float(n - 1)
    if depth <= 0:
        return float(y[ix_mid]), float(ix_mid)
    if depth == 1:
        # Praat's NUM_PEAK_INTERPOLATE_LINEAR — also degenerate
        return float(y[ix_mid]), float(ix_mid)
    if depth == 2:
        # Parabolic
        dy = 0.5 * (y[ix_mid + 1] - y[ix_mid - 1])
        d2y = 2.0 * y[ix_mid] - y[ix_mid - 1] - y[ix_mid + 1]
        if d2y == 0.0:
            return float(y[ix_mid]), float(ix_mid)
        x_max = ix_mid + dy / d2y
        y_max = y[ix_mid] + 0.5 * dy * dy / d2y
        return float(y_max), float(x_max)

    # Sinc (depth 70 / 700): Brent on negated sinc-interpolation
    from scipy.optimize import minimize_scalar

    def neg_y(x):
        return -sinc_interpolate_raised_cosine(y, x, depth)

    res = minimize_scalar(neg_y,
                           bracket=(ix_mid - 1, ix_mid, ix_mid + 1),
                           method='brent',
                           options={'xtol': 1e-10})
    return float(-res.fun), float(res.x)


# ---------------------------------------------------------------------------
# Sinc-refined candidate finding (commit 2)
# ---------------------------------------------------------------------------
def find_candidates_sinc(r: np.ndarray,
                          setup: PitchAnalysisSetup,
                          voicing_threshold: float = 0.45,
                          octave_cost: float = 0.01,
                          max_n_candidates: int = 15,
                          depth: int = 70,
                          ) -> list[tuple[float, float]]:
    """Same logic as find_candidates_parabolic, but with two refinements
    that match Praat's first/second-pass exactly:

      1. First pass uses parabolic for F0 (fast) but sinc-30 for strength
         (so the candidate ranking matches Praat's even before refinement).
      2. Second pass refines each non-voiceless candidate's F0 + strength
         via NUMimproveMaximum (Brent search on sinc-70 interpolated r).

    Source: Sound_to_Pitch.cpp lines 184-261.
    """
    candidates: list[tuple[float, float]] = [(0.0, 0.0)]
    minLag = setup.minimumLag
    maxLag = min(setup.maximumLag, setup.brent_ixmax)
    fs = setup.fs
    threshold = 0.5 * voicing_threshold

    if maxLag <= minLag:
        return candidates

    # First pass: parabolic F0, sinc-30 strength
    for i in range(max(1, minLag), maxLag):
        ri = r[i]
        if ri <= threshold:
            continue
        if not (ri > r[i - 1] and ri >= r[i + 1]):
            continue
        dr = 0.5 * (r[i + 1] - r[i - 1])
        d2r = (ri - r[i - 1]) + (ri - r[i + 1])
        if d2r <= 0.0:
            continue
        lag_subsample = i + dr / d2r
        if lag_subsample <= 0:
            continue
        F0_cand = fs / lag_subsample
        if F0_cand < setup.pitch_floor or F0_cand > setup.pitch_ceiling:
            continue
        # Praat first pass: sinc-30 strength using the parabolic-refined lag
        strength = sinc_interpolate_raised_cosine(r, lag_subsample, 30)
        if not np.isfinite(strength):
            strength = ri + 0.5 * dr * dr / d2r
        if strength > 1.0:
            strength = 1.0 / strength

        if len(candidates) < max_n_candidates:
            candidates.append((F0_cand, strength))
        else:
            weakest_idx = -1
            weakest_score = 2.0
            for j in range(1, len(candidates)):
                F_j, S_j = candidates[j]
                if F_j <= 0:
                    continue
                local_strength = S_j - octave_cost * np.log2(
                    setup.pitch_floor / F_j)
                if local_strength < weakest_score:
                    weakest_score = local_strength
                    weakest_idx = j
            new_local_strength = strength - octave_cost * np.log2(
                setup.pitch_floor / F0_cand)
            if weakest_idx > 0 and new_local_strength > weakest_score:
                candidates[weakest_idx] = (F0_cand, strength)

    # Second pass: refine each candidate via sinc-70 Brent search
    refined: list[tuple[float, float]] = [(0.0, 0.0)]
    for F_cand, S_cand in candidates[1:]:
        if F_cand <= 0:
            continue
        lag = fs / F_cand
        ix_mid = int(round(lag))
        if ix_mid < 1 or ix_mid >= len(r) - 1:
            refined.append((F_cand, S_cand))
            continue
        # Praat uses SINC700 only for frequency > 0.3 * fs (≈ 13 kHz @ 44.1k),
        # which never triggers for pitch. SINC70 is the operative depth.
        y_new, x_new = improve_maximum_sinc(r, ix_mid, depth)
        if x_new > 0:
            F_new = fs / x_new
            if y_new > 1.0:
                y_new = 1.0 / y_new
            refined.append((F_new, y_new))
        else:
            refined.append((F_cand, S_cand))
    return refined


# ---------------------------------------------------------------------------
# Top-level convenience: per-frame strongest F0 across whole signal
# ---------------------------------------------------------------------------
def sound_to_pitch_frames(voice: np.ndarray, fs: float,
                            pitch_floor: float = 75.0,
                            pitch_ceiling: float = 600.0,
                            time_step: float | None = None,
                            voicing_threshold: float = 0.45,
                            octave_cost: float = 0.01,
                            max_n_candidates: int = 15,
                            method: str = 'sinc',
                            ) -> tuple[np.ndarray, np.ndarray, list]:
    """Run AC-Hanning analysis on every frame and return candidate lists.

    Parameters
    ----------
    method : str
        'parabolic' — first-pass only, fast (commit 1 default).
        'sinc'      — first pass + sinc-70 Brent refinement (commit 2),
                       matches Praat second-pass output.

    Returns
    -------
    frame_t : (N,) float64
        Frame centre times (seconds).
    intensity : (N,) float64
        Per-frame intensity (local_peak / global_peak, capped at 1).
    candidates : list[list[(float, float)]]
        Per-frame list of (F0, strength) tuples, with index 0 always the
        voiceless candidate (0.0, 0.0).
    """
    voice = np.asarray(voice, dtype=np.float64)
    setup = PitchAnalysisSetup(fs, pitch_floor, pitch_ceiling)
    frame_t = setup.frame_times(len(voice), time_step)
    n_frames = len(frame_t)
    intensity = np.zeros(n_frames, dtype=np.float64)
    candidates_per_frame: list = [None] * n_frames

    # Global absolute peak (Praat: mean-subtracted per channel)
    global_peak = float(np.max(np.abs(voice - np.mean(voice))))
    if global_peak <= 0:
        for k in range(n_frames):
            candidates_per_frame[k] = [(0.0, 0.0)]
        return frame_t, intensity, candidates_per_frame

    for k, t in enumerate(frame_t):
        r, local_peak, _ = autocorrelation_frame(voice, t, setup)
        if local_peak <= 0:
            candidates_per_frame[k] = [(0.0, 0.0)]
            intensity[k] = 0.0
            continue
        intensity[k] = (1.0 if local_peak > global_peak
                         else local_peak / global_peak)
        if method == 'sinc':
            candidates_per_frame[k] = find_candidates_sinc(
                r, setup,
                voicing_threshold=voicing_threshold,
                octave_cost=octave_cost,
                max_n_candidates=max_n_candidates,
            )
        else:
            candidates_per_frame[k] = find_candidates_parabolic(
                r, setup,
                voicing_threshold=voicing_threshold,
                octave_cost=octave_cost,
                max_n_candidates=max_n_candidates,
            )

    return frame_t, intensity, candidates_per_frame


# Backwards-compat alias used by commit 1's parity test
sound_to_pitch_frames_parabolic = lambda *a, **kw: sound_to_pitch_frames(
    *a, method='parabolic', **kw)
