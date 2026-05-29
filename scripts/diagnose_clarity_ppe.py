#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic for Clarity-MIDI octave drift + PPE / SpectralMoments quirks.

For a recording:
  - Plot midi(t) and look for sudden ±12-semitone jumps that the
    subharmonic-repair pass didn't catch.
  - Compute the fraction of cycles whose MIDI differs by ≥ 6 / ≥ 12
    semitones from the local median (post-repair). High fraction
    means tracking is unstable.
  - PPE: examine distribution shape — Little 2009 expected values
    sit around 0.4-0.7 for healthy voices. Anything close to 1.0
    means the per-window normalised entropy is saturating.
  - SpectralMoments: report distribution + check for NaN / inf / zero
    domination that signals bandwidth^3 division blowup.
"""

from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from voicemap.analyzer import VoiceMapAnalyzer

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    args = ap.parse_args()

    a = VoiceMapAnalyzer()
    result = a.analyze_and_output_vrp(args.audio, plot_mode="none", return_df=True)
    metrics, _, _ = result
    midi = metrics['midi']
    clarity = metrics['clarity']
    ppe = metrics['ppe']
    centroid = metrics['spec_centroid']
    bandwidth = metrics['spec_bandwidth']
    skewness = metrics['spec_skewness']
    kurtosis = metrics['spec_kurtosis']
    n = len(midi)
    print(f"\n=== {args.audio}  ({n} cycles) ===")

    # ── Clarity / MIDI octave drift ──
    print(f"\n[Clarity / MIDI]")
    voiced = midi > 20.1   # voiced cycles
    print(f"  voiced cycles            : {voiced.sum()}  ({100*voiced.mean():.1f}%)")
    print(f"  Clarity ≥ 0.96 (vrp cut) : {(clarity >= 0.96).sum()}  ({100*(clarity >= 0.96).mean():.1f}%)")

    if voiced.sum() < 50:
        print("  (too few voiced cycles to diagnose drift)")
    else:
        m = midi.copy()
        # Cycle-to-cycle deltas
        diffs = np.diff(m[voiced])
        big_jump = (np.abs(diffs) >= 6).sum()
        octave_jump = (np.abs(diffs) >= 11.5).sum()
        print(f"  cycle-to-cycle |Δmidi|   : "
              f"median {np.median(np.abs(diffs)):.2f}  P95 {np.percentile(np.abs(diffs), 95):.2f}  "
              f"max {np.max(np.abs(diffs)):.2f} semitones")
        print(f"  ≥ 6 semitone jumps        : {big_jump} ({100*big_jump/len(diffs):.2f}%)")
        print(f"  ≥ ±octave jumps           : {octave_jump} ({100*octave_jump/len(diffs):.2f}%)")
        # Rolling median deviation
        from scipy.ndimage import median_filter
        m_voiced = m[voiced]
        if len(m_voiced) > 41:
            ref = median_filter(m_voiced, size=41, mode='nearest')
            dev = m_voiced - ref
            print(f"  |MIDI - rolling median|  : "
                  f"median {np.median(np.abs(dev)):.2f}  P95 {np.percentile(np.abs(dev), 95):.2f} "
                  f"semitones  (≥6 = {100*(np.abs(dev) >= 6).mean():.2f}%)")

    # ── PPE distribution ──
    print(f"\n[PPE]  (Little 2009 healthy voice ≈ 0.4–0.7; >0.9 suggests saturation)")
    nz = ppe[ppe > 0]
    if len(nz) > 0:
        print(f"  nonzero cycles : {len(nz)}  ({100*len(nz)/n:.1f}%)")
        print(f"  range          : {nz.min():.3f} – {nz.max():.3f}")
        print(f"  median         : {np.median(nz):.3f}")
        print(f"  mean           : {nz.mean():.3f}")
        print(f"  fraction > 0.9 : {(nz > 0.9).mean():.1%}")
        print(f"  fraction > 0.95: {(nz > 0.95).mean():.1%}")
    else:
        print("  all zeros")

    # ── SpectralMoments sanity ──
    print(f"\n[SpectralMoments]")
    print(f"  centroid:  median {np.median(centroid):.0f} Hz  range [{centroid.min():.0f}, {centroid.max():.0f}]")
    print(f"  bandwidth: median {np.median(bandwidth):.0f} Hz  range [{bandwidth.min():.0f}, {bandwidth.max():.0f}]")
    n_nan = int(np.isnan(skewness).sum())
    n_inf = int(np.isinf(skewness).sum())
    print(f"  skewness:  median {np.median(skewness):.2f}  range [{skewness.min():.2f}, {skewness.max():.2f}]  NaN={n_nan} Inf={n_inf}")
    n_nan = int(np.isnan(kurtosis).sum())
    n_inf = int(np.isinf(kurtosis).sum())
    print(f"  kurtosis:  median {np.median(kurtosis):.2f}  range [{kurtosis.min():.2f}, {kurtosis.max():.2f}]  NaN={n_nan} Inf={n_inf}")
    # Bandwidth-near-zero blowup indicator
    tiny_bw = (bandwidth < 1.0).sum()
    if tiny_bw > 0:
        print(f"  ⚠ bandwidth < 1 Hz in {tiny_bw} cycles — skewness/kurtosis blowup risk")

if __name__ == "__main__":
    main()
