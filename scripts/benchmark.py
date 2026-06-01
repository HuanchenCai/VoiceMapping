#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 4.2 — performance benchmark.

Runs the full analyzer (stereo + EGG, the heaviest mode) on clips of growing
duration and reports wall time, the wall/audio real-time ratio, peak resident
memory, and cycle count — so the O(N) scaling is visible and regressions in
either time or memory are obvious.

    python scripts/benchmark.py
    python scripts/benchmark.py --durations 10,30,60,70

A numba warm-up run (discarded) precedes the measured runs so the JIT compile
cost does not pollute the first timing.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import threading
import time

import numpy as np
import soundfile as sf
import psutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
AUDIO = os.path.join(ROOT, "audio", "test_Voice_EGG.wav")


def _clip(seconds: float, tmp: str) -> str:
    """A `seconds`-long stereo (voice+EGG) clip, sliced/tiled from the fixture."""
    sig, sr = sf.read(AUDIO)
    sr = int(sr)
    if sig.ndim == 1:
        sig = np.column_stack([sig, sig])
    need = int(seconds * sr)
    if len(sig) < need:                          # tile to reach the length
        reps = int(np.ceil(need / len(sig)))
        sig = np.tile(sig, (reps, 1))
    out = os.path.join(tmp, f"clip_{int(seconds)}s.wav")
    sf.write(out, sig[:need].astype(np.float32), sr)
    return out


class _PeakRSS(threading.Thread):
    """Sample this process's RSS every 50 ms; expose the peak."""

    def __init__(self):
        super().__init__(daemon=True)
        self._proc = psutil.Process()
        self._stop_evt = threading.Event()      # not _stop: shadows Thread._stop
        self.peak = self._proc.memory_info().rss

    def run(self):
        while not self._stop_evt.is_set():
            self.peak = max(self.peak, self._proc.memory_info().rss)
            time.sleep(0.05)

    def stop(self):
        self._stop_evt.set()
        self.join(timeout=1.0)


def _run_once(wav: str) -> tuple:
    from voicemap.config import VoiceMapConfig
    from voicemap.analyzer import VoiceMapAnalyzer
    import logging
    logging.disable(logging.WARNING)
    with tempfile.TemporaryDirectory() as out:
        cfg = VoiceMapConfig(analysis_mode="full", output_dir=out)
        analyzer = VoiceMapAnalyzer(cfg)
        sampler = _PeakRSS()
        base = sampler._proc.memory_info().rss
        sampler.start()
        t0 = time.perf_counter()
        res = analyzer.analyze_and_output_vrp(wav, return_df=True,
                                              export_plots=False)
        wall = time.perf_counter() - t0
        sampler.stop()
        df = res[-1]
        n_cycles = int(df["Total"].sum()) if "Total" in df.columns else -1
        return wall, (sampler.peak - base) / 1e6, sampler.peak / 1e6, n_cycles


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--durations", default="10,30,60",
                    help="comma-separated seconds (default 10,30,60)")
    args = ap.parse_args()
    durs = [float(x) for x in args.durations.split(",")]

    with tempfile.TemporaryDirectory() as tmp:
        clips = {d: _clip(d, tmp) for d in durs}
        print("warming up numba (discarded) …", flush=True)
        _run_once(clips[durs[0]])

        print(f"\n{'audio(s)':>8} {'wall(s)':>8} {'wall/audio':>10} "
              f"{'Δram(MB)':>9} {'peak(MB)':>9} {'cycles':>8} {'ms/cyc':>7}")
        rows = []
        for d in durs:
            wall, dram, peak, ncyc = _run_once(clips[d])
            ms_cyc = 1000.0 * wall / ncyc if ncyc > 0 else float("nan")
            rows.append((d, wall, ncyc))
            print(f"{d:8.0f} {wall:8.2f} {wall/d:10.2f} {dram:9.1f} "
                  f"{peak:9.1f} {ncyc:8d} {ms_cyc:7.3f}", flush=True)

        # O(N) scaling: wall time per audio-second should be roughly constant
        if len(rows) >= 2:
            r0, r1 = rows[0], rows[-1]
            scale = (r1[1] / r1[0]) / (r0[1] / r0[0])   # ratio of (wall/audio)
            print(f"\n  scaling: (wall/audio) at {r1[0]:.0f}s is {scale:.2f}× "
                  f"that at {r0[0]:.0f}s  (1.0 = perfectly linear O(N))")


if __name__ == "__main__":
    main()
