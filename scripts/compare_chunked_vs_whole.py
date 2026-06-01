"""Chunked vs whole-signal VRP parity check.

Runs the analyzer twice on the same audio — the whole-signal path and the
bounded-memory chunked path (a small chunk_s forces several chunks + overlap) —
then reports, per metric column, the median relative difference over the cells
present in BOTH grids.

Jitter/shimmer used to drift ~11-15 % under chunking because they decompose a
window-global Praat scalar; the deferred-marks path (perturb_from_marks run ONCE
on accumulated whole-recording marks) should now bring them in line with every
other metric (boundary cycles aside). Any column with a large median_rel points
at a chunk-boundary effect.

Usage:
    python scripts/compare_chunked_vs_whole.py [audio.wav] [chunk_s]
"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from voicemap.analyzer import VoiceMapAnalyzer  # noqa: E402
from voicemap.config import VoiceMapConfig  # noqa: E402
from voicemap.logger import setup_logger  # noqa: E402


def _ascii(s):
    """Windows-GBK-safe console output."""
    return str(s).encode("ascii", "replace").decode("ascii")


def main():
    audio = sys.argv[1] if len(sys.argv) > 1 else "audio/test_Voice_EGG.wav"
    chunk_s = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    setup_logger("voicemap", level=logging.WARNING)

    cfg = VoiceMapConfig()
    cfg.audio_file = audio

    whole = VoiceMapAnalyzer(cfg).analyze_and_output_vrp(
        return_df=True, export_plots=False)[-1]
    chunked = VoiceMapAnalyzer(cfg).analyze_and_output_vrp_chunked(
        chunk_s=chunk_s, overlap_s=1.0, return_df=True, export_plots=False)[-1]

    key = ["MIDI", "dB"]
    w = whole.set_index(key)
    c = chunked.set_index(key)
    common = w.index.intersection(c.index)
    print(_ascii(f"whole cells={len(w)}  chunked cells={len(c)}  "
                 f"common={len(common)}  chunk_s={chunk_s}"))
    wc, cc = w.loc[common], c.loc[common]

    # K-means label-ID columns are permutation-variant across two independent
    # fits, so their per-cell "diff" is meaningless — skip them (the e2e harness
    # compares these on cell-count only, not value).
    def _is_label_col(c):
        return (c.startswith("Cluster ") or c.startswith("cPhon ")
                or c in ("maxCluster", "maxCPhon"))

    rows = []
    for col in wc.columns:
        if col == "Total" or wc[col].dtype == object or _is_label_col(col):
            continue
        wv = wc[col].to_numpy(dtype=float)
        cv = cc[col].to_numpy(dtype=float)
        m = np.isfinite(wv) & np.isfinite(cv) & (np.abs(wv) > 1e-9)
        if m.sum() < 5:
            continue
        rel = np.abs(cv[m] - wv[m]) / np.abs(wv[m])
        rows.append((col, float(np.median(rel)), int(m.sum())))
    rows.sort(key=lambda r: -r[1])

    print(_ascii(f"{'column':<20}{'median_rel':>12}{'n':>7}"))
    for col, med, n in rows:
        flag = "  <-- " if med > 0.02 else ""
        print(_ascii(f"{col:<20}{med:>12.4f}{n:>7}{flag}"))


if __name__ == "__main__":
    main()
