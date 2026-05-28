#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Does swapping EGG cycle_triggers for IAIF GCIs change the voice metrics?

This is the practical question behind "can IAIF replace EGG-based cycle
detection?". For each voice-derived metric in the pipeline, compare the
per-(MIDI, dB) VRP cell values when the SAME voice signal is processed
with two different cycle_triggers sources:

  - reference path: stereo file → EGG phase-portrait → cycle_triggers
  - replacement path: same file but EGG channel stripped → IAIF → cycle_triggers

If a voice metric is robust to where the cycle boundary lands, the two
runs agree closely (high Pearson r, low MAE). If it isn't, that metric
will degrade in a real no-EGG deployment.

Usage:
    python scripts/compare_triggers_voice_metrics.py audio/Jiang_Voice_EGG.wav
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

import numpy as np
import pandas as pd
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from voicemap.analyzer import VoiceMapAnalyzer
from voicemap.config import VoiceMapConfig


# Voice-only metrics: those whose computation only reads the voice channel.
# Excludes EGG-derived columns (Qcontact / dEGGmax / OQ / SPQ / CIQ /
# Cluster / cPhon / Entropy / HRFegg) and their _voice analogs, since
# those are about the EGG-shape signal — not what we're testing here.
VOICE_METRICS = [
    # Core acoustic
    'Clarity', 'CPP', 'CPPS', 'SpecBal', 'Crest',
    # Perturbation (most cycle-sensitive — jitter literally measures cycle timing)
    'Jitter', 'JitterRAP', 'JitterPPQ5',
    'Shimmer', 'ShimmerDB', 'ShimmerAPQ3', 'ShimmerAPQ5', 'ShimmerAPQ11',
    # Noise / clarity
    'HNR', 'NHR', 'PPE', 'ZCR', 'GNE',
    # Spectral shape
    'RMS', 'F0_Hz',
    'SpectralCentroid', 'SpectralBandwidth', 'SpectralRolloff85',
    'SpectralFlatness', 'SpectralSlope',
    'SpectralSkewness', 'SpectralKurtosis',
    'AlphaRatio', 'HammarbergIndex',
    # Formant
    'F1', 'F2', 'F3', 'SingersFormant',
    'B1', 'B2', 'B3', 'FormantDispersion', 'SPR',
    'H1H2', 'H1H3',
    # Singing
    'VibratoRate', 'VibratoExtent', 'VibratoJitter',
    # MFCC
    *(f'MFCC{i+1}' for i in range(13)),
]


def run_and_get_csv(audio_file: str, output_dir: str) -> str:
    """Run the analyzer end-to-end and return path to the VRP CSV."""
    cfg = VoiceMapConfig()
    cfg.output_dir = output_dir
    a = VoiceMapAnalyzer(cfg)
    _, out_file = a.analyze_and_output_vrp(audio_file, plot_mode="none")
    return out_file


def make_mono_copy(stereo_file: str, dest: str) -> str:
    """Strip the EGG channel — saves a voice-only WAV in dest."""
    sig, sr = sf.read(stereo_file)
    if sig.ndim != 2:
        raise SystemExit("Need a stereo (voice + EGG) recording for comparison")
    sf.write(dest, sig[:, 0], sr)
    return dest


def compare_csvs(csv_egg: str, csv_iaif: str) -> pd.DataFrame:
    """Per-(MIDI, dB) cell comparison of every voice metric column.

    Joins on (MIDI, dB) so only cells present in BOTH paths are scored —
    a fair cell-level comparison, not penalising one path for having more
    coverage.
    """
    df_e = pd.read_csv(csv_egg,  sep=';')
    df_i = pd.read_csv(csv_iaif, sep=';')
    merged = df_e.merge(df_i, on=['MIDI', 'dB'],
                        suffixes=('_egg', '_iaif'), how='inner')

    rows = []
    for col in VOICE_METRICS:
        col_e = f"{col}_egg"
        col_i = f"{col}_iaif"
        if col_e not in merged.columns or col_i not in merged.columns:
            continue
        x = merged[col_e].values
        y = merged[col_i].values
        mask = (x != 0) & (y != 0) & np.isfinite(x) & np.isfinite(y)
        n = int(mask.sum())
        if n < 10:
            rows.append(dict(metric=col, n=n, r=np.nan, mae=np.nan,
                              mean_egg=np.nan, mean_iaif=np.nan,
                              rel_bias_pct=np.nan))
            continue
        xv = x[mask]; yv = y[mask]
        r = float(np.corrcoef(xv, yv)[0, 1])
        mae = float(np.mean(np.abs(xv - yv)))
        bias = float(np.mean(yv - xv))
        scale = float(np.mean(np.abs(xv))) + 1e-9
        rows.append(dict(metric=col, n=n,
                          r=r, mae=mae,
                          mean_egg=float(xv.mean()),
                          mean_iaif=float(yv.mean()),
                          rel_bias_pct=100.0 * bias / scale))
    out = pd.DataFrame(rows)

    # Sort: most-degraded metrics first so the user sees risk up top
    out['_sort_key'] = out['r'].fillna(-2.0)
    out = out.sort_values('_sort_key', ascending=False).drop(columns='_sort_key')

    return out, len(merged)


def print_table(summary: pd.DataFrame, n_cells: int) -> None:
    print(f"\nVoice metrics — EGG triggers vs IAIF triggers, "
          f"per VRP cell ({n_cells} cells in common)\n")
    print(f"{'metric':22s} {'n':>5s} {'EGG μ':>10s} {'IAIF μ':>10s} "
          f"{'r':>7s} {'MAE':>10s} {'bias%':>8s}")
    print("-" * 78)
    for _, row in summary.iterrows():
        n = int(row['n']) if not np.isnan(row['n']) else 0
        r = row['r']
        r_str = f"{r:>7.3f}" if not np.isnan(r) else "    nan"
        print(f"{row['metric']:22s} {n:>5d} "
              f"{row['mean_egg']:>10.4f} {row['mean_iaif']:>10.4f} "
              f"{r_str} {row['mae']:>10.4f} {row['rel_bias_pct']:>+7.1f}%")

    # Quick categorical buckets
    print()
    very_strong = (summary['r'] >= 0.9).sum()
    strong = ((summary['r'] >= 0.7) & (summary['r'] < 0.9)).sum()
    moderate = ((summary['r'] >= 0.4) & (summary['r'] < 0.7)).sum()
    weak = (summary['r'] < 0.4).sum()
    print(f"agreement buckets:  r≥0.9: {very_strong}   "
          f"0.7≤r<0.9: {strong}   "
          f"0.4≤r<0.7: {moderate}   "
          f"r<0.4: {weak}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stereo_file")
    ap.add_argument("--out", default=None,
                    help="optional path to save the comparison CSV")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="vmap_cmp_") as td:
        print(f"workdir: {td}")
        # Path 1: stereo → EGG triggers
        print("\n[1/2] Running with EGG cycle_triggers (stereo)...")
        egg_out_dir = os.path.join(td, "egg_run"); os.makedirs(egg_out_dir)
        csv_egg = run_and_get_csv(args.stereo_file, egg_out_dir)

        # Path 2: strip EGG → IAIF triggers (mono)
        print("\n[2/2] Running with IAIF cycle_triggers (mono)...")
        mono_file = os.path.join(td, "mono_voice.wav")
        make_mono_copy(args.stereo_file, mono_file)
        iaif_out_dir = os.path.join(td, "iaif_run"); os.makedirs(iaif_out_dir)
        csv_iaif = run_and_get_csv(mono_file, iaif_out_dir)

        summary, n_cells = compare_csvs(csv_egg, csv_iaif)
        print_table(summary, n_cells)

        if args.out:
            summary.to_csv(args.out, index=False, sep=';')
            print(f"\nSaved comparison CSV: {args.out}")


if __name__ == "__main__":
    main()
