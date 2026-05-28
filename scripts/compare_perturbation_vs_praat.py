#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baseline calibration: does our PerturbationCalculator (driven by EGG
cycle_triggers) agree with Praat's jitter/shimmer reference implementation?

If yes — our jitter/shimmer code is fine, and the IAIF-vs-EGG disagreement
we saw earlier comes purely from IAIF's GCI timing noise.
If no — the existing PerturbationCalculator may have its own bias, and
fixing the IAIF path alone won't be enough.

Run on stereo (voice + EGG) files so the EGG path is unambiguously the
reference. Compares at two granularities:
  (1) whole-file mean — fast sanity check, single number per metric
  (2) 1-s sliding windows — per-window mean of our per-cycle values vs.
      Praat's per-window value; Pearson r tells whether the two track
      each other through F0 / SPL changes within the recording.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd
import soundfile as sf
import parselmouth
from parselmouth.praat import call

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from voicemap.analyzer import VoiceMapAnalyzer
from voicemap.config import VoiceMapConfig


def praat_jitter_shimmer(snd: parselmouth.Sound,
                         pitch_floor: float = 75.0,
                         pitch_ceiling: float = 600.0,
                         period_factor: float = 1.3,
                         amp_factor: float = 1.6) -> dict:
    """One-shot Praat scalar jitter/shimmer/HNR on the given Sound."""
    pitch = snd.to_pitch_cc(time_step=None,
                            pitch_floor=pitch_floor,
                            pitch_ceiling=pitch_ceiling)
    pp = call([snd, pitch], "To PointProcess (cc)")

    # period_floor / period_ceiling = 0.0001 / 0.02 s = MDVP defaults
    j_local  = call(pp, "Get jitter (local)",       0, 0, 1e-4, 0.02, period_factor)
    j_rap    = call(pp, "Get jitter (rap)",         0, 0, 1e-4, 0.02, period_factor)
    j_ppq5   = call(pp, "Get jitter (ppq5)",        0, 0, 1e-4, 0.02, period_factor)
    s_local  = call([snd, pp], "Get shimmer (local)",     0, 0, 1e-4, 0.02, period_factor, amp_factor)
    s_db     = call([snd, pp], "Get shimmer (local_dB)",  0, 0, 1e-4, 0.02, period_factor, amp_factor)
    s_apq3   = call([snd, pp], "Get shimmer (apq3)",      0, 0, 1e-4, 0.02, period_factor, amp_factor)
    s_apq5   = call([snd, pp], "Get shimmer (apq5)",      0, 0, 1e-4, 0.02, period_factor, amp_factor)
    s_apq11  = call([snd, pp], "Get shimmer (apq11)",     0, 0, 1e-4, 0.02, period_factor, amp_factor)
    # Praat returns fraction; we display %
    return {
        'Jitter':       j_local * 100,
        'JitterRAP':    j_rap   * 100,
        'JitterPPQ5':   j_ppq5  * 100,
        'Shimmer':      s_local * 100,
        'ShimmerDB':    s_db,
        'ShimmerAPQ3':  s_apq3  * 100,
        'ShimmerAPQ5':  s_apq5  * 100,
        'ShimmerAPQ11': s_apq11 * 100,
    }


def run_voicemap_perturbation(stereo_file: str) -> tuple[dict, np.ndarray, np.ndarray]:
    """Run the standard VoiceMap pipeline (EGG cycle_triggers, no IAIF)
    and return the per-cycle perturbation series + GCI sample indices."""
    cfg = VoiceMapConfig()
    cfg.cycle_log = True
    a = VoiceMapAnalyzer(cfg)
    metrics, _, _ = a.analyze_and_output_vrp(stereo_file, plot_mode="none",
                                              return_df=True)
    out = {
        'Jitter':       metrics['jitter'],
        'JitterRAP':    metrics['jitter_rap'],
        'JitterPPQ5':   metrics['jitter_ppq5'],
        'Shimmer':      metrics['shimmer'],
        'ShimmerDB':    metrics['shimmer_db'],
        'ShimmerAPQ3':  metrics['shimmer_apq3'],
        'ShimmerAPQ5':  metrics['shimmer_apq5'],
        'ShimmerAPQ11': metrics['shimmer_apq11'],
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stereo_file")
    ap.add_argument("--window-s", type=float, default=0.0,
                    help="if >0, also do per-window comparison (1.0 = 1 s)")
    args = ap.parse_args()

    print(f"\n=== file: {args.stereo_file} ===")

    # Load voice channel for Praat
    signal, sr = sf.read(args.stereo_file)
    if signal.ndim != 2:
        raise SystemExit("need stereo (voice + EGG) for this test")
    voice = signal[:, 0]
    snd_full = parselmouth.Sound(voice, sampling_frequency=sr)

    # Praat — whole file
    print("\n[1] Praat (voice channel, whole file)...")
    praat = praat_jitter_shimmer(snd_full)

    # Our PerturbationCalculator — driven by EGG triggers
    print("[2] VoiceMap PerturbationCalculator (EGG cycle_triggers)...")
    ours = run_voicemap_perturbation(args.stereo_file)

    # File-level: our values are per-cycle, take the simple mean
    print(f"\n--- whole-file comparison ---")
    print(f"{'metric':14s} {'VoiceMap mean':>14s} {'Praat':>10s}  {'ratio (V/P)':>12s}")
    for k in praat:
        v = ours[k]
        v_mean = float(np.mean(v[v > 0])) if (v > 0).any() else float('nan')
        p = praat[k]
        ratio = v_mean / p if p else float('nan')
        print(f"{k:14s} {v_mean:>14.4f} {p:>10.4f}  {ratio:>12.3f}")

    # Optional: per-window comparison
    if args.window_s > 0:
        print(f"\n--- {args.window_s:.1f} s sliding window comparison ---")
        win = args.window_s
        n = int(len(voice) / sr / win)
        rows = []
        # For "our" per-window value we need cycle times — derive from analyzer.
        # Re-run lite to fetch cycle indices.
        cfg = VoiceMapConfig()
        a = VoiceMapAnalyzer(cfg)
        voice_pre, egg_pre, sr2, _ = a.load_audio(args.stereo_file)
        egg_p = a.preprocess_egg(egg_pre)
        triggers = a.phase_portrait_cycle_detection(egg_p)
        gci = np.where(triggers > 0.5)[0]
        # one fewer perturbation value than triggers (it's a between-cycle measure)
        cycle_t = gci[:-1] / sr  # seconds; align to start-of-cycle

        for k in praat:
            our_arr = ours[k]
            if len(our_arr) != len(cycle_t):
                # adjustment — pad/truncate to align
                m = min(len(our_arr), len(cycle_t))
                our_arr = our_arr[:m]
                ct = cycle_t[:m]
            else:
                ct = cycle_t

            ours_per_win = []
            praat_per_win = []
            for i in range(n):
                t0, t1 = i * win, (i + 1) * win
                mask = (ct >= t0) & (ct < t1)
                cyc_vals = our_arr[mask]
                cyc_vals = cyc_vals[cyc_vals > 0]
                if len(cyc_vals) < 5:
                    continue
                ours_per_win.append(np.mean(cyc_vals))

                # Praat on the window
                start = int(t0 * sr)
                end = int(t1 * sr)
                if end - start < int(0.1 * sr):
                    continue
                try:
                    snd_win = parselmouth.Sound(voice[start:end],
                                                 sampling_frequency=sr)
                    pw = praat_jitter_shimmer(snd_win)
                    praat_per_win.append(pw[k])
                except Exception:
                    ours_per_win.pop()  # drop matching item
                    continue

            ours_per_win = np.array(ours_per_win, dtype=float)
            praat_per_win = np.array(praat_per_win, dtype=float)
            mask = np.isfinite(ours_per_win) & np.isfinite(praat_per_win)
            if mask.sum() < 5:
                rows.append(dict(metric=k, n=int(mask.sum()),
                                  r=np.nan, mean_v=np.nan, mean_p=np.nan,
                                  ratio=np.nan))
                continue
            ov = ours_per_win[mask]; pv = praat_per_win[mask]
            r = float(np.corrcoef(ov, pv)[0, 1])
            rows.append(dict(metric=k, n=int(mask.sum()),
                              r=r, mean_v=float(ov.mean()),
                              mean_p=float(pv.mean()),
                              ratio=float(ov.mean() / pv.mean()) if pv.mean() else float('nan')))
        df = pd.DataFrame(rows)
        print(f"{'metric':14s} {'n':>4s} {'V mean':>9s} {'P mean':>9s} "
              f"{'ratio':>7s} {'Pearson r':>10s}")
        for _, row in df.iterrows():
            r = row['r']
            r_str = f"{r:>10.3f}" if not np.isnan(r) else "       nan"
            print(f"{row['metric']:14s} {int(row['n']):>4d} "
                  f"{row['mean_v']:>9.4f} {row['mean_p']:>9.4f} "
                  f"{row['ratio']:>7.3f} {r_str}")


if __name__ == "__main__":
    main()
