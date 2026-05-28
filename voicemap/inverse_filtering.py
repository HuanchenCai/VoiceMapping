#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IAIF (Iterative Adaptive Inverse Filtering) + voice-only GCI detection.

Used when an audio file lacks an EGG channel. The goal:
  1. Estimate the glottal flow waveform (and its derivative) from voice alone
     via Alku 1992 IAIF.
  2. Detect Glottal Closure Instants (GCI) as negative peaks of the glottal
     flow derivative — these become the cycle boundaries for downstream
     per-cycle metrics that currently rely on EGG-based phase-portrait detection.

The glottal flow waveform is also exposed so EGG-shape metrics
(Qcontact / dEGGmax / OQ / Entropy ...) can be re-derived from it
under '<name>_voice' column names.

References
----------
Alku, P. (1992). Glottal wave analysis with pitch synchronous iterative
adaptive inverse filtering. Speech Communication, 11(2-3), 109-118.

Drugman, T., Alku, P., Alwan, A., & Yegnanarayana, B. (2014). Glottal source
processing: From analogue AR models to data-driven methods. Speech
Communication, 56, 122-141.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt, lfilter, find_peaks

from voicemap.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Low-level: Levinson-Durbin autocorrelation LPC.
# We don't reuse the Burg implementation from metrics.py because IAIF
# canonically uses autocorrelation LPC (matches Alku 1992) and the
# Burg method's lower spectral bias on short frames is not needed here.
# ---------------------------------------------------------------------------
def _lpc_autocorr(x: np.ndarray, order: int) -> np.ndarray:
    """Levinson-Durbin recursion.

    Returns AR coefficients [1, a1, a2, ..., a_p] such that the inverse
    filter A(z) = 1 + a1·z^-1 + ... whitens x. Treats degenerate frames
    (zero/near-zero energy, numerical breakdown) by returning the identity
    filter so downstream lfilter() is a no-op.
    """
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n <= order or order < 1:
        a = np.zeros(order + 1)
        a[0] = 1.0
        return a

    # Biased autocorrelation r[0..order]
    r = np.correlate(x, x, mode='full')[n - 1: n + order]
    if r[0] <= 1e-20:
        a = np.zeros(order + 1)
        a[0] = 1.0
        return a

    a = np.zeros(order + 1)
    a[0] = 1.0
    e = float(r[0])

    for i in range(1, order + 1):
        # Reflection coefficient k_i
        acc = r[i]
        for j in range(1, i):
            acc += a[j] * r[i - j]
        k = -acc / e

        # Update AR coefs in place via symmetric pair swap
        a_prev = a.copy()
        for j in range(1, i):
            a[j] = a_prev[j] + k * a_prev[i - j]
        a[i] = k

        e = e * (1.0 - k * k)
        if e <= 1e-20:
            # Numerical breakdown — leave coefs as is, force identity tail
            for j in range(i + 1, order + 1):
                a[j] = 0.0
            break

    return a


def _hp_filter_design(fs: float, cutoff_hz: float = 30.0,
                      order: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Butterworth high-pass — shared by pre-emphasis and post-integration
    de-drifting."""
    nyq = fs / 2.0
    return butter(order, cutoff_hz / nyq, btype='high')


# ---------------------------------------------------------------------------
# IAIF — frame-by-frame with overlap-add.
# ---------------------------------------------------------------------------
def iaif(signal: np.ndarray,
         fs: float,
         frame_ms: float = 25.0,
         hop_ms: float = 5.0,
         p_vt: int | None = None,
         p_gl: int = 4,
         hpf_cutoff_hz: float = 30.0,
         ) -> tuple[np.ndarray, np.ndarray]:
    """Iterative Adaptive Inverse Filtering on a voice signal.

    Implements the refined Alku 1992 IAIF algorithm: two passes of LP
    estimation, with the second pass refined by first explicitly
    estimating the glottal source contribution and removing it before
    re-fitting the vocal tract.

    Parameters
    ----------
    signal : np.ndarray
        Mono voice signal (1-D).
    fs : float
        Sample rate (Hz).
    frame_ms : float
        Analysis frame length in milliseconds. 25 ms is the speech-
        processing standard; long enough to span a few F0 cycles at
        adult voices, short enough that VT can be treated as stationary.
    hop_ms : float
        Frame hop in milliseconds. 5 ms gives 80% overlap → smooth time
        variation of VT/source estimates across an F0 sweep.
    p_vt : int, optional
        Vocal-tract LP order. Default = round(2·fs/1000) + 4 (~92 at
        44.1 kHz). Higher than the canonical speech-band rule because
        VoiceMap analyzes the full audio bandwidth — empirically a lower
        order leaves formant residue in dg that hurts GCI detection.
    p_gl : int
        Glottal source LP order. 4 is the canonical IAIF value.
    hpf_cutoff_hz : float
        Pre-emphasis HPF cutoff (Hz). Removes DC drift that would
        confuse the order-1 LP step. 30 Hz is well below any phonation F0.

    Returns
    -------
    g : np.ndarray
        Glottal flow waveform, same length as ``signal``.
    dg : np.ndarray
        Glottal flow derivative (output of the inverse filter before
        integration). GCI candidates are negative peaks of dg.
    """
    s_in = np.asarray(signal, dtype=np.float64)
    if s_in.ndim != 1:
        raise ValueError(f"iaif: expected 1-D signal, got shape {s_in.shape}")
    N = len(s_in)
    if N < int(0.05 * fs):  # < 50 ms — nothing meaningful to fit
        return np.zeros(N), np.zeros(N)

    if p_vt is None:
        # 2·fs/1000 + 4 — higher than the speech-bandwidth-only rule
        # (fs/1000+4 ≈ 48 @ 44.1k) because phonation analysis here uses the
        # full audio bandwidth, not just the 0-4 kHz speech band. Lowering
        # the order to 48 left visible formant residue in dg that fooled
        # the GCI detector on synthetic test vowels.
        p_vt = int(round(2.0 * fs / 1000.0)) + 4

    # Step 0: pre-emphasis HPF — remove DC drift before any LP analysis.
    b_hp, a_hp = _hp_filter_design(fs, hpf_cutoff_hz)
    s = filtfilt(b_hp, a_hp, s_in)

    frame_len = max(int(round(frame_ms * fs / 1000.0)), p_vt * 3)
    hop_len = max(int(round(hop_ms * fs / 1000.0)), 1)
    if frame_len > N:
        # Signal shorter than one analysis frame — degrade gracefully:
        # treat the whole signal as a single frame.
        frame_len = N
        hop_len = N

    win = np.hanning(frame_len).astype(np.float64)

    dg_out = np.zeros(N, dtype=np.float64)
    norm = np.zeros(N, dtype=np.float64)

    n_frames = max(1, (N - frame_len) // hop_len + 1)
    for i in range(n_frames):
        start = i * hop_len
        end = start + frame_len
        if end > N:
            # last frame: shift back so it ends at N (standard tail handling)
            end = N
            start = end - frame_len
            if start < 0:
                start = 0
        frame = s[start:end]
        if len(frame) < p_vt * 2:
            continue
        frame_w = frame * win[: len(frame)]

        # ── IAIF iterations ───────────────────────────────────────────
        # (1) LP order 1 on windowed frame — preliminary low-frequency
        #     glottal-tilt estimate. Inverse-filtering with this removes
        #     the dominant glottal contribution before fitting the VT.
        a_g1 = _lpc_autocorr(frame_w, 1)
        y1 = lfilter(a_g1, [1.0], frame)

        # (2) LP order p_vt on the result → preliminary vocal tract.
        a_vt1 = _lpc_autocorr(y1 * win[: len(y1)], p_vt)

        # (3) Preliminary glottal flow derivative — inverse-filter the
        #     pre-emphasized signal with the VT estimate.
        dg1 = lfilter(a_vt1, [1.0], frame)

        # (4) Integrate to preliminary glottal flow (windowed; the result
        #     only feeds the LP step below, never the output).
        g1 = np.cumsum(dg1)

        # (5) LP order p_gl on preliminary glottal flow → glottal source
        #     model (refined, captures the source spectral tilt).
        a_g = _lpc_autocorr(g1 * win[: len(g1)], p_gl)

        # (6) Vocal-tract input: remove the refined glottal contribution
        #     from the pre-emphasized speech.
        v = lfilter(a_g, [1.0], frame)

        # (7) Refined LP order p_vt on the VT input → final vocal tract.
        a_vt = _lpc_autocorr(v * win[: len(v)], p_vt)

        # (8) Final glottal flow derivative for this frame.
        dg_frame = lfilter(a_vt, [1.0], frame)

        # OLA: weighted mean across frames covering each sample.
        # Apply window once at synthesis; divide by sum-of-windows so the
        # output is the Hann-weighted average of per-frame estimates
        # (independent of the overlap factor).
        w = win[: end - start]
        dg_out[start:end] += dg_frame * w
        norm[start:end] += w

    norm = np.maximum(norm, 1e-12)
    dg_out /= norm

    # Integrate to glottal flow; HPF to suppress DC drift from cumsum.
    g_out = np.cumsum(dg_out)
    g_out = filtfilt(b_hp, a_hp, g_out)

    logger.info("IAIF: N=%d  fs=%.0f  p_vt=%d  p_gl=%d  frames=%d  "
                "frame=%dms  hop=%dms",
                N, fs, p_vt, p_gl, n_frames, int(frame_ms), int(hop_ms))
    return g_out, dg_out


# ---------------------------------------------------------------------------
# GCI detection from the glottal flow derivative.
# ---------------------------------------------------------------------------
def detect_gci_from_dg(dg: np.ndarray,
                       fs: float,
                       min_f0_hz: float = 60.0,
                       max_f0_hz: float = 1500.0,
                       prominence_factor: float = 0.3,
                       ) -> np.ndarray:
    """Locate Glottal Closure Instants as negative peaks of dg.

    Physical picture: at glottal closure the flow drops abruptly, so
    dg = dU/dt shows a sharp negative spike. We pick those as cycle
    boundaries.

    Parameters
    ----------
    dg : np.ndarray
        Glottal flow derivative from :func:`iaif`.
    fs : float
        Sample rate.
    min_f0_hz / max_f0_hz : float
        Expected F0 range. ``min_distance = fs / max_f0`` rejects double-
        detections inside one period; the max bound is informational
        (not enforced — we'd rather miss a cycle than insert a spurious
        one in a low-energy region).
    prominence_factor : float
        Peak prominence threshold relative to dg's standard deviation.
        0.3·σ is a robust default — generous enough to catch closures
        in soft voicing, restrictive enough to ignore noise.

    Returns
    -------
    np.ndarray
        Sample indices of detected GCIs, sorted ascending.
    """
    dg = np.asarray(dg, dtype=np.float64)
    if dg.size == 0:
        return np.array([], dtype=np.int64)

    sigma = float(np.std(dg))
    if sigma <= 1e-12:
        return np.array([], dtype=np.int64)

    min_dist = max(int(round(fs / max(max_f0_hz, 1.0))), 1)

    # Closure ⇒ large negative dg ⇒ pick positive peaks of -dg.
    peaks, _ = find_peaks(-dg,
                          distance=min_dist,
                          prominence=prominence_factor * sigma)
    return peaks.astype(np.int64)


def voice_to_cycle_triggers(voice_signal: np.ndarray,
                            fs: float,
                            min_f0_hz: float = 60.0,
                            max_f0_hz: float = 1500.0,
                            ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convenience wrapper: voice → (cycle_triggers, glottal_flow, glottal_flow_derivative).

    cycle_triggers is the 0/1 sample-aligned trigger array consumed by the
    rest of the analyzer pipeline (matches the format produced by
    ``VoiceMapAnalyzer.phase_portrait_cycle_detection``). Length equals
    the input signal length.
    """
    g, dg = iaif(voice_signal, fs)
    gci = detect_gci_from_dg(dg, fs, min_f0_hz=min_f0_hz, max_f0_hz=max_f0_hz)

    triggers = np.zeros(len(voice_signal), dtype=np.float64)
    if gci.size > 0:
        triggers[gci] = 1.0

    logger.info("voice-only GCI detection: %d cycles found "
                "(F0 search range %.0f-%.0f Hz)",
                int(gci.size), min_f0_hz, max_f0_hz)
    return triggers, g, dg
