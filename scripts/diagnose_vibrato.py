#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vibrato diagnostic: detection rate + true vs artifact vertical bars.

For a given recording:
  1. Run analyzer, get per-cycle vibrato_rate / extent.
  2. Detection rate: % of cycles where vibrato was detected.
  3. SNR gate diagnostic: look at the mag/noise_floor distribution to
     see whether the gate is rejecting genuine vibrato.
  4. Bar diagnostic: for each MIDI column on the VRP, compute the
     CV of VibratoRate across SPL rows. Low CV with many rows
     present = uniform column (either real sustain or bug).
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
    metrics, out_file, grouped_df = result
    rate = metrics['vibrato_rate']
    extent = metrics['vibrato_extent']
    midi = metrics['midi']
    n = len(rate)

    print(f"\n=== {args.audio} ===")
    print(f"cycles total                 : {n}")
    print(f"vibrato detected (rate > 0)  : {(rate > 0).sum()} ({100*(rate > 0).mean():.1f}%)")
    print(f"  rate mean (nonzero)        : {rate[rate > 0].mean():.2f} Hz")
    print(f"  rate range                 : {rate[rate > 0].min():.2f} - {rate[rate > 0].max():.2f} Hz")
    print(f"  extent mean (nonzero)      : {extent[extent > 0].mean():.1f} cents pk-pk")
    print(f"  extent range               : {extent[extent > 0].min():.1f} - {extent[extent > 0].max():.1f} cents")
    print(f"  extent > 400 (clipped to 0): {(extent > 400).sum()}")

    # ── Bar diagnostic on the VRP grid ──
    df = grouped_df[['MIDI','dB','VibratoRate']].copy()
    df = df[df['VibratoRate'] > 0]
    print(f"\nVRP cells with VibratoRate > 0: {len(df)} (out of {len(grouped_df)})")

    # Per-MIDI column: number of nonzero SPL rows + std/mean ratio
    cols = df.groupby('MIDI').agg(
        rows=('VibratoRate','count'),
        v_mean=('VibratoRate','mean'),
        v_std=('VibratoRate','std'),
        spl_range=('dB', lambda x: f'{x.min():.0f}-{x.max():.0f}'),
    ).reset_index()
    cols['cv_pct'] = 100.0 * cols['v_std'] / cols['v_mean'].replace(0, np.nan)
    cols = cols[cols['rows'] >= 5].sort_values('cv_pct')
    print(f"\nMIDI columns with >=5 voiced SPL rows, sorted by within-column CV (%):")
    print(f"  ('low CV with many rows' = uniform column = either sustain or artifact)\n")
    print(cols.head(15).to_string(index=False))

if __name__ == "__main__":
    main()
