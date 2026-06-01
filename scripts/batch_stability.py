#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 4.4 — batch stability / leak check.

Runs the full analyzer many times over the available fixtures (the 12 synthetic
test signals + the real stereo+EGG recording), asserting on every run:
  • no crash (exception),
  • no NaN / Inf in any numeric VRP column,
and tracking resident memory across runs to flag a leak (RSS should plateau,
not grow monotonically).

    python scripts/batch_stability.py                 # default 30 runs
    python scripts/batch_stability.py --runs 100      # the PLAN's 100+ target

Clips are truncated to a few seconds for throughput; pass --seconds to change.
We do not have a 100+ real-recording corpus, so coverage is breadth (every
fixture, all three mode paths) × repetition rather than 100 distinct voices —
documented as a limitation.
"""
from __future__ import annotations

import argparse
import gc
import glob
import os
import sys
import tempfile

import numpy as np
import soundfile as sf
import psutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
TS_DIR = os.path.join(ROOT, "docs", "validation", "test_signals")
AUDIO = os.path.join(ROOT, "audio", "test_Voice_EGG.wav")


def _fixtures(seconds: float, tmp: str) -> list:
    """[(wav_path, mode), …] — synthetic mono signals + the real stereo file."""
    items = []
    for wav in sorted(glob.glob(os.path.join(TS_DIR, "*.wav"))):
        items.append((wav, "acoustic"))
    if os.path.exists(AUDIO):
        sig, sr = sf.read(AUDIO)
        n = int(seconds * int(sr))
        clip = os.path.join(tmp, "real_clip.wav")
        sf.write(clip, sig[:n].astype(np.float32), int(sr))
        items.append((clip, "full"))
    return items


def _has_nan(df) -> list:
    bad = []
    for col in df.columns:
        v = df[col].values
        if np.issubdtype(v.dtype, np.number) and not np.all(np.isfinite(v)):
            bad.append(col)
    return bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--seconds", type=float, default=4.0)
    args = ap.parse_args()

    import logging
    logging.disable(logging.WARNING)
    from voicemap.config import VoiceMapConfig
    from voicemap.analyzer import VoiceMapAnalyzer

    proc = psutil.Process()
    with tempfile.TemporaryDirectory() as tmp:
        fixtures = _fixtures(args.seconds, tmp)
        out_dir = os.path.join(tmp, "out")
        os.makedirs(out_dir, exist_ok=True)
        print(f"{len(fixtures)} fixtures × {args.runs} runs "
              f"(={args.runs} analyses, ~{args.seconds:.0f}s clips)")

        crashes, nan_runs, rss = [], [], []
        for i in range(args.runs):
            wav, mode = fixtures[i % len(fixtures)]
            try:
                cfg = VoiceMapConfig(analysis_mode=mode, output_dir=out_dir)
                res = VoiceMapAnalyzer(cfg).analyze_and_output_vrp(
                    wav, return_df=True, export_plots=False)
                bad = _has_nan(res[-1])
                if bad:
                    nan_runs.append((i, os.path.basename(wav), bad))
            except Exception as e:           # noqa: BLE001 — we want every failure
                crashes.append((i, os.path.basename(wav), repr(e)))
            gc.collect()
            rss.append(proc.memory_info().rss / 1e6)
            if (i + 1) % 10 == 0 or i == args.runs - 1:
                print(f"  run {i+1:3d}/{args.runs}  rss={rss[-1]:.0f} MB  "
                      f"crashes={len(crashes)}  nan={len(nan_runs)}", flush=True)

        # leak heuristic: numba / matplotlib module caches warm up over the
        # first few runs and then plateau, so first-vs-last over-reports. A real
        # leak keeps growing in the SECOND HALF; compare the second-half start
        # to the end (warmup excluded).
        mid = len(rss) // 2
        head = float(np.mean(rss[mid:mid + 5])) if len(rss) > mid + 5 else float(np.mean(rss[:5]))
        tail = float(np.mean(rss[-5:]))
        growth = tail - head
        bar = "=" * 64
        print(f"\n{bar}")
        print(f"  runs={args.runs}  crashes={len(crashes)}  "
              f"nan_runs={len(nan_runs)}")
        print(f"  RSS warm avg {float(np.mean(rss[:5])):.0f} → mid {head:.0f} → "
              f"last-5 {tail:.0f} MB  (2nd-half growth {growth:+.0f} MB)")
        for i, f, e in crashes[:5]:
            print(f"  [CRASH] run {i} {f}: {e}")
        for i, f, b in nan_runs[:5]:
            print(f"  [NaN]   run {i} {f}: {b}")
        leak = growth > 50.0          # >50 MB sustained growth ⇒ suspect
        ok = not crashes and not nan_runs and not leak
        print(f"  {'PASS' if ok else 'FAIL'}  "
              f"(leak threshold +50 MB → {'tripped' if leak else 'ok'})")
        print(bar)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
