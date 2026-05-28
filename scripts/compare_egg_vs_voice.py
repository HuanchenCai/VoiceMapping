#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare EGG-based vs voice-IAIF-based cycle detection and EGG-shape metrics.

Two complementary analyses on the SAME stereo (voice + EGG) recording:

(A) GCI-timing comparison
    Run phase_portrait_cycle_detection on the EGG channel and
    voice_to_cycle_triggers (IAIF) on the voice channel independently.
    Match every voice GCI to its nearest EGG GCI; report cycle counts,
    median offset, IQR, and fraction matched within ±1 ms / ±2 ms.

(B) Per-cycle metric agreement
    Run the full pipeline with iaif_always_run=True so each VRP cell
    has both EGG-derived columns (Qcontact, OQ, ...) and voice-derived
    twins (Qcontact_voice, OQ_voice, ...). For each pair, report
    Pearson r, MAE, and the linear-fit bias/slope.

Usage:
    python scripts/compare_egg_vs_voice.py audio/Jiang_Voice_EGG.wav
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from voicemap.analyzer import VoiceMapAnalyzer
from voicemap.config import VoiceMapConfig
from voicemap.inverse_filtering import voice_to_cycle_triggers


# ---------------------------------------------------------------------------
# (A) GCI timing comparison
# ---------------------------------------------------------------------------
def gci_timing_comparison(stereo_file: str) -> dict:
    """Detect cycles separately on EGG and voice, match nearest-neighbor,
    report timing offsets."""
    print(f"\n[A] GCI timing comparison: {stereo_file}")
    signal, sr = sf.read(stereo_file)
    if signal.ndim != 2:
        raise SystemExit("Need a stereo (voice + EGG) recording for comparison")

    voice = signal[:, 0]
    egg = signal[:, 1]

    cfg = VoiceMapConfig()
    cfg.sample_rate = sr

    a = VoiceMapAnalyzer(cfg)
    voice_p = a.preprocess_voice(voice)
    egg_p = a.preprocess_egg(egg)

    # EGG path
    egg_triggers = a.phase_portrait_cycle_detection(egg_p)
    egg_gci = np.where(egg_triggers > 0.5)[0]

    # Voice IAIF path (use same Hz bounds as the analyzer would)
    f0_max = sr / max(cfg.min_samples, 1)
    f0_min = sr / max(cfg.max_period_samples, 1)
    voice_triggers, _, _ = voice_to_cycle_triggers(
        voice_p, sr, min_f0_hz=f0_min, max_f0_hz=f0_max)
    voice_triggers = a.filter_cycles(voice_triggers)
    voice_gci = np.where(voice_triggers > 0.5)[0]

    # Pair voice→EGG by nearest neighbour (searchsorted is O(N log N))
    if len(egg_gci) == 0 or len(voice_gci) == 0:
        print("  No cycles detected on one of the channels — abort")
        return {}

    insert_pos = np.searchsorted(egg_gci, voice_gci)
    left = np.clip(insert_pos - 1, 0, len(egg_gci) - 1)
    right = np.clip(insert_pos, 0, len(egg_gci) - 1)
    cand_left = egg_gci[left]
    cand_right = egg_gci[right]
    pick_right = np.abs(voice_gci - cand_right) < np.abs(voice_gci - cand_left)
    nearest = np.where(pick_right, cand_right, cand_left)

    offsets_samples = voice_gci - nearest          # positive = voice late
    offsets_ms = offsets_samples / sr * 1000.0
    abs_ms = np.abs(offsets_ms)

    within_1ms = np.mean(abs_ms <= 1.0) * 100
    within_2ms = np.mean(abs_ms <= 2.0) * 100

    duration = len(signal) / sr
    print(f"  duration            : {duration:.1f} s")
    print(f"  cycles (EGG)        : {len(egg_gci):>6d}  "
          f"({len(egg_gci)/duration:.1f} c/s)")
    print(f"  cycles (voice IAIF) : {len(voice_gci):>6d}  "
          f"({len(voice_gci)/duration:.1f} c/s)")
    print(f"  cycle-count ratio   : voice / EGG = {len(voice_gci)/len(egg_gci):.3f}")
    print(f"  GCI offset (ms)     : median={np.median(offsets_ms):+.3f}  "
          f"IQR=[{np.percentile(offsets_ms, 25):+.3f}, "
          f"{np.percentile(offsets_ms, 75):+.3f}]  "
          f"|median|={np.median(abs_ms):.3f}")
    print(f"  matched within ±1ms : {within_1ms:.1f}%")
    print(f"  matched within ±2ms : {within_2ms:.1f}%")

    return dict(n_egg=len(egg_gci), n_voice=len(voice_gci),
                offsets_ms=offsets_ms, within_1ms=within_1ms,
                within_2ms=within_2ms)


# ---------------------------------------------------------------------------
# (B) Per-cycle metric agreement
# ---------------------------------------------------------------------------
def metric_agreement(stereo_file: str) -> pd.DataFrame:
    """Run the full pipeline with iaif_always_run=True so both EGG-derived
    and voice-derived metric columns coexist in the CSV. Compare each pair."""
    print(f"\n[B] Per-cycle metric agreement (iaif_always_run=True)")
    cfg = VoiceMapConfig()
    cfg.iaif_always_run = True
    cfg.cycle_log = True   # need per-cycle, not VRP-cell-binned

    a = VoiceMapAnalyzer(cfg)
    _, out_file = a.analyze_and_output_vrp(stereo_file, plot_mode="none")

    cycles_csv = out_file.replace("_VRP.csv", "_cycles.csv")
    if not os.path.exists(cycles_csv):
        print(f"  expected per-cycle log not found: {cycles_csv}")
        return pd.DataFrame()
    df = pd.read_csv(cycles_csv, sep=';')
    print(f"  per-cycle log: {cycles_csv}  ({len(df)} cycles)")

    pairs = [
        ('Qcontact', 'Qcontact_voice'),
        ('dEGGmax',  'dEGGmax_voice'),
        ('Icontact', 'Icontact_voice'),
        ('Entropy',  'Entropy_voice'),
        ('HRFegg',   'HRFegg_voice'),
        ('OQ',       'OQ_voice'),
        ('SPQ',      'SPQ_voice'),
        ('CIQ',      'CIQ_voice'),
    ]

    rows = []
    for egg_col, voice_col in pairs:
        a_arr = df[egg_col].values
        b_arr = df[voice_col].values
        mask = (a_arr != 0) & (b_arr != 0) & np.isfinite(a_arr) & np.isfinite(b_arr)
        n = int(mask.sum())
        if n < 10:
            rows.append(dict(metric=egg_col, n=n,
                             egg_mean=np.nan, voice_mean=np.nan,
                             pearson_r=np.nan, mae=np.nan,
                             bias=np.nan, slope=np.nan))
            continue
        x = a_arr[mask]; y = b_arr[mask]
        r = float(np.corrcoef(x, y)[0, 1])
        mae = float(np.mean(np.abs(x - y)))
        # OLS: y = slope·x + bias
        slope, bias = np.polyfit(x, y, 1)
        rows.append(dict(metric=egg_col, n=n,
                         egg_mean=float(x.mean()),
                         voice_mean=float(y.mean()),
                         pearson_r=r, mae=mae,
                         bias=float(bias), slope=float(slope)))
    summary = pd.DataFrame(rows)

    print()
    print(f"{'metric':12s} {'n':>6s} {'EGG μ':>10s} {'voice μ':>10s} "
          f"{'r':>7s} {'MAE':>10s} {'bias':>8s} {'slope':>7s}")
    for _, row in summary.iterrows():
        print(f"{row['metric']:12s} {int(row['n']):>6d} "
              f"{row['egg_mean']:>10.4f} {row['voice_mean']:>10.4f} "
              f"{row['pearson_r']:>7.3f} {row['mae']:>10.4f} "
              f"{row['bias']:>+8.3f} {row['slope']:>7.3f}")
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stereo_file",
                    help="2-channel WAV: channel 0 = voice, channel 1 = EGG")
    ap.add_argument("--skip-timing", action="store_true",
                    help="skip part (A): GCI timing comparison")
    ap.add_argument("--skip-metrics", action="store_true",
                    help="skip part (B): metric agreement")
    args = ap.parse_args()

    if not args.skip_timing:
        gci_timing_comparison(args.stereo_file)
    if not args.skip_metrics:
        metric_agreement(args.stereo_file)


if __name__ == "__main__":
    main()
