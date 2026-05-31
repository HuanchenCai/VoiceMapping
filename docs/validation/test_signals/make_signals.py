#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 0.1 — Synthetic test-signal library for VoiceMap validation.

Generates 12 synthetic WAV files with *known* ground truth (F0, jitter,
shimmer, formants, vibrato, SNR) so that every metric can be checked
against a signal whose correct answer we computed analytically rather
than measured.

Design: classic source-filter vocoder.

    glottal flow (Rosenberg pulse, per-cycle period + amplitude)
        -> vocal-tract formant cascade (Klatt 2-pole resonators)
        -> lip radiation (first difference)
        -> [+ optional Gaussian noise for breathy / SNR control]

Because every stage after the source is linear time-invariant, the
*relative* period perturbation (jitter) and *relative* amplitude
perturbation (shimmer) imposed on the source are preserved at the output,
so the values we dial in are recoverable by the metrics under test.

Jitter / shimmer are imposed as a strict alternating +/-d pattern, which
makes the Praat *local* definition exact:
    period_k     = T0 * (1 +/- d_p),   d_p = jitter_local / 2
    amplitude_k  = A0 * (1 +/- d_a),   d_a = shimmer_local / 2
because every |x_i - x_{i-1}| is identical and mean(x) = baseline, so
    mean|dT| / mean(T) = 2 * d_p = jitter_local   (exact)
    mean|dA| / mean(A) = 2 * d_a = shimmer_local   (exact)

Run:
    python docs/validation/test_signals/make_signals.py
Outputs:
    docs/validation/test_signals/*.wav   (12 files, mono float32)
    docs/validation/test_signals/manifest.json

Naming follows docs/validation/conventions.md §3 (decimals written `p`).
All ground truth is recorded in manifest.json; nothing here is random
without a fixed seed.
"""

from __future__ import annotations

import json
import os

import numpy as np
import soundfile as sf

# ─── Global conventions (see docs/validation/conventions.md) ─────────────────
SR = 44100                 # sample rate, Hz
PEAK = 0.9                 # output normalisation peak (linear)
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Vowel formant tables (Hz) — Peterson & Barney style male averages.
# bandwidths in Hz.
VOWELS = {
    "neutral": dict(F=[700.0, 1200.0, 2600.0], B=[60.0, 90.0, 120.0]),
    "a":       dict(F=[730.0, 1090.0, 2440.0], B=[60.0, 90.0, 120.0]),
    "e":       dict(F=[530.0, 1840.0, 2480.0], B=[60.0, 90.0, 120.0]),
    "i":       dict(F=[270.0, 2290.0, 3010.0], B=[60.0, 90.0, 120.0]),
}


# ─── Source-filter building blocks ───────────────────────────────────────────
def rosenberg_shape(u: np.ndarray, oq: float = 0.6, sq: float = 2.5
                    ) -> np.ndarray:
    """Rosenberg-C glottal-flow pulse as a function of *normalised phase*
    `u` in [0, 1) — one full period maps to [0, 1).

    Evaluating the pulse from a continuous phase (rather than rendering it
    into an integer number of samples) is what lets sub-sample period
    perturbations — i.e. realistic jitter of a fraction of a sample at
    high F0 — survive into the waveform.

    oq = open quotient; sq = speed quotient (rise/fall ratio of open phase).
    """
    u = np.asarray(u, dtype=np.float64)
    g = np.zeros_like(u)
    tp = oq * sq / (sq + 1.0)            # rising fraction of the period
    tn = oq / (sq + 1.0)                 # falling fraction
    rise = u < tp
    fall = (u >= tp) & (u < tp + tn)
    g[rise] = 0.5 * (1.0 - np.cos(np.pi * u[rise] / tp))
    g[fall] = np.cos(np.pi * (u[fall] - tp) / (2.0 * tn))
    return g


def klatt_resonator(x: np.ndarray, f: float, bw: float, sr: int) -> np.ndarray:
    """Single 2-pole formant resonator, unity gain at DC (Klatt 1980)."""
    r = np.exp(-np.pi * bw / sr)
    theta = 2.0 * np.pi * f / sr
    b = 2.0 * r * np.cos(theta)
    c = -(r * r)
    a = 1.0 - b - c
    y = np.zeros_like(x)
    y1 = y2 = 0.0
    for n in range(len(x)):
        yn = a * x[n] + b * y1 + c * y2
        y2 = y1
        y1 = yn
        y[n] = yn
    return y


def formant_cascade(source: np.ndarray, formants, bandwidths, sr: int
                    ) -> np.ndarray:
    """Cascade of formant resonators + lip radiation (first difference)."""
    y = source
    for f, bw in zip(formants, bandwidths):
        y = klatt_resonator(y, f, bw, sr)
    y = np.diff(y, prepend=y[0])          # lip radiation
    return y


def _cycle_boundaries(f0_inst, dur, jitter_frac=0.0):
    """Cycle boundary times (seconds, float) for an instantaneous-F0
    callable f0_inst(t)->Hz, with an alternating +/-(jitter_frac/2)
    period perturbation. Boundaries are kept in continuous time so that
    sub-sample period changes are preserved when later sampled."""
    bounds = []
    signs = []
    t = 0.0
    k = 0
    d_p = jitter_frac / 2.0
    while t < dur + 0.05:                   # a little past the end
        bounds.append(t)
        f0 = float(f0_inst(t))
        sign = 1.0 if (k % 2 == 0) else -1.0
        period_k = (1.0 / f0) * (1.0 + sign * d_p)
        signs.append(sign)
        t += period_k
        k += 1
    return np.array(bounds, dtype=np.float64), np.array(signs, dtype=np.float64)


def synth_vowel(dur, f0_inst, vowel="neutral",
                jitter_frac=0.0, shimmer_frac=0.0, snr_db=None,
                seed=0):
    """Synthesise a voiced vowel via continuous-phase glottal rendering.

    f0_inst : callable t->Hz (instantaneous F0; constant for steady vowels)
    jitter_frac / shimmer_frac : target Praat *local* values as fractions.
    snr_db  : if set, add Gaussian noise to reach this SNR (dB).
    """
    rng = np.random.default_rng(seed)
    n_total = int(round(dur * SR))
    t = np.arange(n_total, dtype=np.float64) / SR

    bounds, signs = _cycle_boundaries(f0_inst, dur, jitter_frac)
    d_a = shimmer_frac / 2.0
    amp_per_cycle = 1.0 + signs * d_a       # alternating amplitude (shimmer)

    # For each sample, find its enclosing cycle and the within-cycle phase.
    k = np.searchsorted(bounds, t, side="right") - 1
    k = np.clip(k, 0, len(bounds) - 2)
    cycle_len = bounds[k + 1] - bounds[k]
    u = (t - bounds[k]) / cycle_len         # normalised phase in [0, 1)
    source = rosenberg_shape(u) * amp_per_cycle[k]

    F = VOWELS[vowel]["F"]
    B = VOWELS[vowel]["B"]
    y = formant_cascade(source, F, B, SR)

    if snr_db is not None:
        sig_rms = np.sqrt(np.mean(y ** 2))
        noise = rng.standard_normal(len(y))
        noise_rms = np.sqrt(np.mean(noise ** 2))
        target_noise_rms = sig_rms / (10.0 ** (snr_db / 20.0))
        y = y + noise * (target_noise_rms / noise_rms)

    return y


def normalize(y: np.ndarray) -> np.ndarray:
    peak = np.max(np.abs(y)) or 1.0
    return (y / peak * PEAK).astype(np.float32)


# ─── The 12 signals ──────────────────────────────────────────────────────────
def build_all():
    manifest = []

    def const(f0):
        return lambda t: f0

    def add(filename, y, gt, fn_name, **extra):
        path = os.path.join(OUT_DIR, filename)
        y = normalize(y)
        sf.write(path, y, SR, subtype="FLOAT")
        entry = dict(filename=filename, sample_rate=SR,
                     duration_s=round(len(y) / SR, 6),
                     ground_truth=gt, generator_seed=extra.get("seed", 0),
                     generator_function=fn_name)
        manifest.append(entry)
        print(f"  wrote {filename:42s} ({len(y)/SR:.2f}s)  gt={gt}")

    print("Synthesising 12 test signals...")

    # 1. modal baseline — F0=200, no perturbation
    add("vowel_modal_200Hz_5s.wav",
        synth_vowel(5.0, const(200.0), "neutral"),
        dict(F0_Hz=200.0, jitter_local_pct=0.0, shimmer_local_pct=0.0,
             formants_Hz=VOWELS["neutral"]["F"], SNR_dB=None),
        "synth_vowel(const 200)")

    # 2. breathy — Gaussian noise, SNR≈15 dB  (HNR≈15 dB)
    add("vowel_breathy_200Hz_SNR15dB.wav",
        synth_vowel(5.0, const(200.0), "neutral", snr_db=15.0, seed=2),
        dict(F0_Hz=200.0, jitter_local_pct=0.0, shimmer_local_pct=0.0,
             formants_Hz=VOWELS["neutral"]["F"], SNR_dB=15.0,
             HNR_dB_approx=15.0),
        "synth_vowel(const 200, snr=15)", seed=2)

    # 3. jitter 0.5 %
    add("vowel_jitter_0p5pct.wav",
        synth_vowel(3.0, const(200.0), "neutral", jitter_frac=0.005),
        dict(F0_Hz=200.0, jitter_local_pct=0.5, shimmer_local_pct=0.0,
             formants_Hz=VOWELS["neutral"]["F"], SNR_dB=None),
        "synth_vowel(const 200, jitter=0.005)")

    # 4. jitter 2 %
    add("vowel_jitter_2pct.wav",
        synth_vowel(3.0, const(200.0), "neutral", jitter_frac=0.02),
        dict(F0_Hz=200.0, jitter_local_pct=2.0, shimmer_local_pct=0.0,
             formants_Hz=VOWELS["neutral"]["F"], SNR_dB=None),
        "synth_vowel(const 200, jitter=0.02)")

    # 5. shimmer 5 %
    add("vowel_shimmer_5pct.wav",
        synth_vowel(3.0, const(200.0), "neutral", shimmer_frac=0.05),
        dict(F0_Hz=200.0, jitter_local_pct=0.0, shimmer_local_pct=5.0,
             formants_Hz=VOWELS["neutral"]["F"], SNR_dB=None),
        "synth_vowel(const 200, shimmer=0.05)")

    # 6. vibrato 6 Hz / 100 cent peak-to-peak (F0=200)
    f0c, fvib, extent_cents = 200.0, 6.0, 100.0
    def f0_vibrato(t):
        return f0c * 2.0 ** ((extent_cents / 2.0) / 1200.0
                             * np.sin(2.0 * np.pi * fvib * t))
    add("vowel_vibrato_6Hz_100cent.wav",
        synth_vowel(5.0, f0_vibrato, "neutral"),
        dict(F0_Hz=200.0, vibrato_rate_Hz=6.0, vibrato_extent_cent_pp=100.0,
             jitter_local_pct=0.0, shimmer_local_pct=0.0,
             formants_Hz=VOWELS["neutral"]["F"], SNR_dB=None),
        "synth_vowel(vibrato 6Hz/100cent)")

    # 7. pitch glide 150 -> 400 Hz (log-linear)
    f_start, f_end, gdur = 150.0, 400.0, 4.0
    def f0_glide(t):
        frac = min(t / gdur, 1.0)
        return f_start * (f_end / f_start) ** frac
    add("vowel_pitch_glide_150_to_400Hz.wav",
        synth_vowel(gdur, f0_glide, "neutral"),
        dict(F0_start_Hz=150.0, F0_end_Hz=400.0, glide="log-linear",
             formants_Hz=VOWELS["neutral"]["F"], SNR_dB=None),
        "synth_vowel(glide 150->400)")

    # 8. three vowels a / e / i, known F1/F2/F3, F0=150
    seg = 1.5
    parts = []
    for v in ("a", "e", "i"):
        parts.append(synth_vowel(seg, const(150.0), v))
    add("vowel_formants_a_e_i.wav",
        np.concatenate(parts),
        dict(F0_Hz=150.0, segments=[
            dict(vowel="a", t0=0.0, t1=1.5, formants_Hz=VOWELS["a"]["F"]),
            dict(vowel="e", t0=1.5, t1=3.0, formants_Hz=VOWELS["e"]["F"]),
            dict(vowel="i", t0=3.0, t1=4.5, formants_Hz=VOWELS["i"]["F"]),
        ], SNR_dB=None),
        "synth_vowel(a)+(e)+(i)")

    # 9. high pitch corner case — 800 Hz
    add("vowel_high_pitch_800Hz.wav",
        synth_vowel(3.0, const(800.0), "neutral"),
        dict(F0_Hz=800.0, jitter_local_pct=0.0, shimmer_local_pct=0.0,
             formants_Hz=VOWELS["neutral"]["F"], SNR_dB=None),
        "synth_vowel(const 800)")

    # 10. low pitch corner case — 70 Hz
    add("vowel_low_pitch_70Hz.wav",
        synth_vowel(3.0, const(70.0), "neutral"),
        dict(F0_Hz=70.0, jitter_local_pct=0.0, shimmer_local_pct=0.0,
             formants_Hz=VOWELS["neutral"]["F"], SNR_dB=None),
        "synth_vowel(const 70)")

    # 11. silence — NaN / boundary handling
    add("silent_5s.wav",
        np.zeros(int(5.0 * SR)),
        dict(F0_Hz=None, note="all voicing-gated metrics must be NaN/empty"),
        "zeros(5s)")

    # 12. linear chirp 50 -> 1000 Hz — aperiodic; voicing-gated metrics = 0
    cdur = 5.0
    t = np.arange(int(cdur * SR)) / SR
    k = (1000.0 - 50.0) / cdur
    chirp = np.sin(2.0 * np.pi * (50.0 * t + 0.5 * k * t * t))
    add("chirp_50_1000Hz.wav",
        chirp,
        dict(F0_Hz=None, kind="linear_chirp", f_start_Hz=50.0,
             f_end_Hz=1000.0,
             note="aperiodic; voicing-gated metrics should be 0/empty"),
        "linear_chirp(50->1000)")

    # ─── manifest ────────────────────────────────────────────────────────────
    manifest_path = os.path.join(OUT_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(dict(sample_rate=SR, n_signals=len(manifest),
                       signals=manifest), fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(manifest)} signals + manifest.json to {OUT_DIR}")
    return manifest


if __name__ == "__main__":
    build_all()
