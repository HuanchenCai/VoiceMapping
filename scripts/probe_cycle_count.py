#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnose whether EGG over-counts or voice-cc under-counts.

For a stereo (voice + EGG) recording:
  1. Detect EGG triggers via phase-portrait (VoiceMap default).
  2. Detect Praat-cc cycle marks at multiple voicing thresholds.
  3. Pair each EGG trigger with its nearest voice-cc mark; report:
       - cycle count vs nominal F0 × duration (which method over/under counts)
       - distribution of inter-trigger intervals
       - precision / recall of voice-cc vs EGG within ±5 ms
  4. Tells us how much "more cycle headroom" lowering voicingThreshold
     would buy on a real recording.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from voicemap.analyzer import VoiceMapAnalyzer
import voicemap.praat_pitch as ppt
import voicemap.praat_perturbation as ptt


def egg_triggers(voice_signal, egg_signal, sr):
    a = VoiceMapAnalyzer()
    egg_p = a.preprocess_egg(egg_signal)
    trig = a.phase_portrait_cycle_detection(egg_p)
    return np.where(trig > 0.5)[0] / sr   # seconds


def praat_cc_marks(voice, sr, voicing_threshold):
    pitch = ppt.sound_to_pitch(
        voice, sr,
        pitch_floor=75.0, pitch_ceiling=600.0,
        voicing_threshold=voicing_threshold,
    )
    return ptt.sound_pitch_to_pointprocess_cc(voice, sr, pitch), pitch


def median_F0_from_marks(t_marks):
    if len(t_marks) < 2:
        return float('nan')
    periods = np.diff(t_marks)
    periods = periods[(periods > 1e-4) & (periods < 0.02)]
    if len(periods) == 0:
        return float('nan')
    return float(1.0 / np.median(periods))


def cycle_pair_stats(t_a, t_b, tol_ms):
    """For each t_a, find nearest t_b. Return: # of t_a within tol of any t_b,
    median offset (ms), P90 offset (ms)."""
    if len(t_a) == 0 or len(t_b) == 0:
        return 0, float('nan'), float('nan')
    insert = np.searchsorted(t_b, t_a)
    left = np.clip(insert - 1, 0, len(t_b) - 1)
    right = np.clip(insert, 0, len(t_b) - 1)
    d_left = np.abs(t_a - t_b[left])
    d_right = np.abs(t_a - t_b[right])
    nearest = np.minimum(d_left, d_right)
    within = int((nearest * 1000.0 <= tol_ms).sum())
    median_ms = float(np.median(nearest) * 1000.0)
    p90_ms = float(np.percentile(nearest, 90) * 1000.0)
    return within, median_ms, p90_ms


def voiced_fraction(pitch):
    return float(np.mean(np.isfinite(pitch.F0) & (pitch.F0 > 0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stereo_file")
    args = ap.parse_args()

    sig, sr = sf.read(args.stereo_file)
    if sig.ndim != 2:
        raise SystemExit("need stereo file (voice + EGG)")
    voice = sig[:, 0].astype(np.float64)
    egg = sig[:, 1].astype(np.float64)
    duration = len(voice) / sr
    print(f"\n=== {args.stereo_file}  (duration {duration:.1f}s, fs {sr}) ===\n")

    # ── EGG triggers (single setting; VoiceMap default phase-portrait) ──
    print("[EGG]")
    egg_t = egg_triggers(voice, egg, sr)
    egg_f0 = median_F0_from_marks(egg_t)
    print(f"  triggers = {len(egg_t):>6d}   ({len(egg_t)/duration:>6.1f} ev/s)   median F0 from periods = {egg_f0:.1f} Hz")

    # ── Praat-cc marks at varying voicingThreshold ──
    print("\n[Praat-cc] voicing_threshold scan")
    print(f"  {'thresh':>7s}  {'count':>6s}  {'ev/s':>6s}  {'med F0':>7s}  {'voiced%':>7s}  "
          f"{'EGG→cc P recall':>17s}  {'cc→EGG P precision':>19s}")
    for vt in [0.45, 0.30, 0.20, 0.10, 0.05]:
        cc_t, pitch = praat_cc_marks(voice, sr, vt)
        cc_f0 = median_F0_from_marks(cc_t)
        vf = voiced_fraction(pitch) * 100.0
        # Recall: how many EGG triggers are matched within ±5ms by a cc mark
        n_rec, med_rec, p90_rec = cycle_pair_stats(egg_t, cc_t, tol_ms=5.0)
        recall = 100.0 * n_rec / max(len(egg_t), 1)
        # Precision: how many cc marks are matched within ±5ms by an EGG trigger
        n_prec, med_prec, p90_prec = cycle_pair_stats(cc_t, egg_t, tol_ms=5.0)
        precision = 100.0 * n_prec / max(len(cc_t), 1)
        print(f"  {vt:>7.2f}  {len(cc_t):>6d}  {len(cc_t)/duration:>6.1f}  "
              f"{cc_f0:>7.1f}  {vf:>6.1f}%  "
              f"{recall:>16.1f}%  {precision:>18.1f}%")


if __name__ == "__main__":
    main()
