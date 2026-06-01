#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 4.1 — end-to-end CSV regression across the three analysis modes.

Runs the full analyzer in each mode on a short fixture and reduces the output
VRP to a compact per-column signature (n_nonzero cells + mean). Compares the
signature against a committed baseline (`docs/validation/regression/
e2e_baseline.json`) so any accidental metric drift turns this red.

    python scripts/e2e_regression.py            # check against baseline
    python scripts/e2e_regression.py --update   # (re)generate the baseline

Modes / fixtures (built in-memory from committed assets, kept short for speed):
  • mono            — synthetic modal vowel,  analysis_mode='acoustic'
  • stereo+EGG      — 5 s slice of test_Voice_EGG.wav (ch1 voice + ch2 EGG),
                      analysis_mode='full'
  • stereo+no-EGG   — voice ch1 + noise ch2 (channel 2 is NOT EGG),
                      analysis_mode='acoustic'

Tolerance: mean compared with rtol 2e-2 + atol 1e-3 (a coarse drift detector
robust to the CPP tie-break dither; a real formula change shifts means far
more). Categorical label columns (maxCluster / maxCPhon) are compared on
n_nonzero only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

AUDIO = os.path.join(ROOT, "audio", "test_Voice_EGG.wav")
TS_DIR = os.path.join(ROOT, "docs", "validation", "test_signals")
BASELINE = os.path.join(ROOT, "docs", "validation", "regression",
                        "e2e_baseline.json")
FIX_SECONDS = 5.0
CATEGORICAL = {"maxCluster", "maxCPhon"}


def _build_fixtures(tmp: str) -> list:
    """Return [(name, wav_path, mode), …] for the three modes."""
    sig, sr = sf.read(AUDIO)
    sr = int(sr)
    n = int(FIX_SECONDS * sr)
    voice = (sig[:, 0] if sig.ndim == 2 else sig)[:n].astype(np.float64)
    egg = (sig[:, 1] if (sig.ndim == 2 and sig.shape[1] > 1) else sig[:n]
           )[:n].astype(np.float64)

    # mono: a committed synthetic modal vowel (mono)
    mono_src = os.path.join(TS_DIR, "vowel_modal_200Hz_5s.wav")
    mono_path = mono_src if os.path.exists(mono_src) else None
    if mono_path is None:                       # fall back to the sliced voice
        mono_path = os.path.join(tmp, "mono.wav")
        sf.write(mono_path, voice.astype(np.float32), sr)

    # stereo + EGG: real voice + real EGG slice
    se_path = os.path.join(tmp, "stereo_egg.wav")
    sf.write(se_path, np.column_stack([voice, egg]).astype(np.float32), sr)

    # stereo + no-EGG: real voice + seeded noise in channel 2 (not EGG)
    rng = np.random.default_rng(0)
    noise = 0.05 * rng.standard_normal(len(voice))
    sne_path = os.path.join(tmp, "stereo_noegg.wav")
    sf.write(sne_path, np.column_stack([voice, noise]).astype(np.float32), sr)

    return [
        ("mono",          mono_path, "acoustic"),
        ("stereo+EGG",    se_path,   "full"),
        ("stereo+no-EGG", sne_path,  "acoustic"),
    ]


def _signature(df) -> dict:
    """Per-column {n_nonzero, mean} over the VRP grid."""
    import pandas as pd  # noqa: F401
    sig = {}
    for col in df.columns:
        if col in ("MIDI", "dB"):
            continue
        v = df[col].values
        if not np.issubdtype(v.dtype, np.number):
            continue
        finite = v[np.isfinite(v)]
        nz = int(np.count_nonzero(finite))
        mean = float(finite.mean()) if finite.size else 0.0
        sig[col] = {"nz": nz, "mean": mean}
    return sig


def _run_mode(wav: str, mode: str, out_dir: str) -> dict:
    from voicemap.config import VoiceMapConfig
    from voicemap.analyzer import VoiceMapAnalyzer
    cfg = VoiceMapConfig(analysis_mode=mode, output_dir=out_dir)
    analyzer = VoiceMapAnalyzer(cfg)
    res = analyzer.analyze_and_output_vrp(wav, return_df=True,
                                          export_plots=False)
    grouped = res[-1]            # (..., grouped_df)
    return _signature(grouped)


def _compare(name: str, ref: dict, cur: dict) -> list:
    """Return list of (column, status, detail) rows."""
    rows = []
    for col, r in ref.items():
        if col not in cur:
            rows.append((col, "FAIL", "missing in current output"))
            continue
        c = cur[col]
        # n_nonzero: allow ±2 cells of slack (dither can flip a borderline cell)
        nz_ok = abs(c["nz"] - r["nz"]) <= max(2, int(0.02 * max(r["nz"], 1)))
        if col in CATEGORICAL:
            rows.append((col, "PASS" if nz_ok else "FAIL",
                         f"nz {r['nz']}->{c['nz']}"))
            continue
        d = abs(c["mean"] - r["mean"])
        mean_ok = d <= 2e-2 * abs(r["mean"]) + 1e-3
        ok = nz_ok and mean_ok
        rows.append((col, "PASS" if ok else "FAIL",
                     f"mean {r['mean']:.4g}->{c['mean']:.4g} (Δ{d:.2g}) "
                     f"nz {r['nz']}->{c['nz']}"))
    new = [c for c in cur if c not in ref]
    for col in new:
        rows.append((col, "NEW", f"not in baseline (mean {cur[col]['mean']:.4g})"))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true",
                    help="(re)generate the baseline instead of checking")
    args = ap.parse_args()

    import logging
    logging.disable(logging.WARNING)            # quiet the per-stage logs

    with tempfile.TemporaryDirectory() as tmp:
        fixtures = _build_fixtures(tmp)
        out_dir = os.path.join(tmp, "out")
        os.makedirs(out_dir, exist_ok=True)
        current = {}
        for name, wav, mode in fixtures:
            print(f"  running {name:14s} (mode={mode}) …", flush=True)
            current[name] = _run_mode(wav, mode, out_dir)

    if args.update:
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w", encoding="utf-8") as fh:
            json.dump(current, fh, indent=2, sort_keys=True)
        ncols = sum(len(v) for v in current.values())
        print(f"\nbaseline written: {os.path.relpath(BASELINE, ROOT)} "
              f"({len(current)} modes, {ncols} columns)")
        return

    if not os.path.exists(BASELINE):
        raise SystemExit("no baseline — run with --update first")
    with open(BASELINE, encoding="utf-8") as fh:
        baseline = json.load(fh)

    bar = "=" * 70
    n_fail = 0
    for name, _w, _m in fixtures:
        rows = _compare(name, baseline.get(name, {}), current.get(name, {}))
        fails = [r for r in rows if r[1] == "FAIL"]
        news = [r for r in rows if r[1] == "NEW"]
        n_fail += len(fails)
        print(f"\n{bar}\n  MODE: {name}   "
              f"{len(rows)-len(fails)-len(news)}/{len(rows)-len(news)} PASS"
              f"{' + ' + str(len(news)) + ' NEW' if news else ''}\n{bar}")
        for col, st, detail in rows:
            if st != "PASS":
                print(f"  [{st}] {col:20s} {detail}")
        if not fails and not news:
            print("  all columns within tolerance")
    print(f"\n{bar}\n  {'PASS' if n_fail == 0 else 'FAIL'}: {n_fail} drifted "
          f"column(s) across 3 modes\n{bar}")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
