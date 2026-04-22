#!/usr/bin/env python3
"""
Voice Mapping — CLI entry point.

Feature-parity with the GUI: every knob the GUI exposes is a flag here,
plus a --batch mode for processing a whole directory of recordings in
one invocation. The GUI and CLI share the same analyzer, so the CSV
columns produced are identical.

Usage
  # Single file, all defaults (writes <out>/complete_vrp_results_<ts>_VRP.csv
  # + per-metric PNGs under <out>/plots/)
  python main.py audio.wav

  # GUI
  python main.py --gui

  # Custom clarity + cluster params + combined overview plot
  python main.py audio.wav --clarity 0.97 --cluster-k 6 --cluster-n-harm 12 \
                           --plot-mode combined

  # Use pre-trained centroids for cross-recording label consistency
  python main.py audio.wav --load-centroids cEGG.csv

  # Train on one recording, save centroids, re-use on another
  python main.py refA.wav --save-centroids cEGG.csv
  python main.py test.wav --load-centroids cEGG.csv

  # Batch mode: all .wav files under a directory share the same settings
  # (and optionally the same centroids). One CSV per input; summary printed.
  python main.py --batch audio/ --plot-mode none --load-centroids cEGG.csv
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# src/ on import path so we can load the analyzer package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


# ─── CLI definition ──────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="voicemap",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Voice Mapping — VRP analysis (CLI-equivalent to the GUI).",
        epilog=__doc__.split("Usage", 1)[-1] if __doc__ else None,
    )
    # Input / mode
    p.add_argument("audio", nargs="?",
                   help="input stereo .wav (ch1=mic, ch2=EGG). Omitted => use "
                        "DEFAULT_CONFIG.audio_file. Ignored when --batch is set.")
    p.add_argument("--gui", "-g", action="store_true",
                   help="launch the graphical interface instead of CLI.")
    p.add_argument("--batch", metavar="DIR",
                   help="process every .wav under DIR (recursive); one CSV per file.")

    # Output
    p.add_argument("-o", "--output-dir", metavar="DIR", default=None,
                   help="where CSVs (+ plots) go. Default: config.output_dir (result/).")
    p.add_argument("--plot-mode", choices=("none", "per-metric", "combined"),
                   default="per-metric",
                   help="PNG export: none | per-metric (default) | combined overview.")

    # Analysis parameters
    p.add_argument("--clarity", type=float, default=None, metavar="F",
                   help="clarity threshold (0.80 – 1.00). Default: config.clarity_threshold.")

    # EGG cluster parameters
    p.add_argument("--cluster-k", type=int, default=None, metavar="N",
                   help="K in K-means for EGG + cPhon clustering (default 5).")
    p.add_argument("--cluster-n-harm", type=int, default=None, metavar="N",
                   help="harmonics used as EGG cluster features (default 10).")
    p.add_argument("--load-centroids", metavar="CSV",
                   help="skip K-means training, classify against this centroid CSV. "
                        "Ensures label semantics match across recordings.")
    p.add_argument("--save-centroids", metavar="CSV",
                   help="after analysis, write the trained centroids to this CSV. "
                        "Ignored in --batch mode if --load-centroids is also set.")
    p.add_argument("--train-centroids", nargs="+", metavar=("OUT.csv", "wav"),
                   help="joint-train EGG cluster centroids across multiple WAVs "
                        "and write OUT.csv. Usage: --train-centroids out.csv a.wav b.wav [...]. "
                        "Exits after writing; does not run a normal analysis.")

    # Logging
    p.add_argument("-v", "--verbose", action="store_true",
                   help="DEBUG level logging.")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="WARNING level only.")
    return p


def _resolve_log_level(args) -> int:
    if args.quiet:
        return logging.WARNING
    if args.verbose:
        return logging.DEBUG
    return logging.INFO


def _build_config(args):
    from config import VoiceMapConfig, DEFAULT_CONFIG
    kwargs = {}
    if args.clarity is not None:
        kwargs["clarity_threshold"] = float(args.clarity)
    if args.output_dir:
        kwargs["output_dir"] = args.output_dir
    # Let the analyzer keep its other defaults (MIDI/SPL ranges, SR, etc.)
    if kwargs:
        return VoiceMapConfig(**kwargs)
    return DEFAULT_CONFIG


def _make_analyzer(args, config):
    from analyzer import VoiceMapAnalyzer
    a = VoiceMapAnalyzer(config)
    if args.cluster_k is not None:
        a.cluster_calculator.n_clusters = int(args.cluster_k)
        a.phon_calculator.n_clusters    = int(args.cluster_k)
    if args.cluster_n_harm is not None:
        a.cluster_calculator.n_harmonics = int(args.cluster_n_harm)
    if args.load_centroids:
        a.load_centroids(args.load_centroids)
    return a


def _run_one(args, config, logger, audio_path: str, save_centroids_once: bool = False) -> str:
    """Analyse one file; return CSV path. Optionally save centroids after."""
    analyzer = _make_analyzer(args, config)

    logger.info("Analysing: %s", audio_path)
    t0 = time.perf_counter()
    data, out_csv = analyzer.analyze_and_output_vrp(
        audio_path, plot_mode=args.plot_mode)
    dt = time.perf_counter() - t0

    logger.info("Done in %.2fs → %s  (%d points)", dt, out_csv, len(data["midi"]))

    if save_centroids_once and args.save_centroids:
        try:
            analyzer.save_centroids(args.save_centroids)
            logger.info("Centroids saved: %s", args.save_centroids)
        except Exception as e:  # noqa: BLE001
            logger.error("Could not save centroids: %s", e)

    return out_csv


# ─── Main dispatch ───────────────────────────────────────────────────────────
def main():
    args = _build_parser().parse_args()

    # GUI short-circuit — no config/analyzer setup needed
    if args.gui:
        from gui import main as gui_main
        gui_main()
        return

    from logger import setup_logger, get_logger
    setup_logger("voicemap", level=_resolve_log_level(args))
    logger = get_logger("voicemap")
    logger.info("Voice Mapping CLI")

    config = _build_config(args)

    # --train-centroids shortcut: pool EGG features across all given wavs,
    # fit a single K-means, write CSV, exit.
    if args.train_centroids:
        if len(args.train_centroids) < 2:
            logger.error("--train-centroids needs OUT.csv and at least one wav")
            sys.exit(1)
        out_csv = args.train_centroids[0]
        wavs    = args.train_centroids[1:]
        for w in wavs:
            if not os.path.exists(w):
                logger.error("WAV not found: %s", w); sys.exit(1)
        from analyzer import VoiceMapAnalyzer
        a = VoiceMapAnalyzer(config)
        if args.cluster_k is not None:
            a.cluster_calculator.n_clusters = int(args.cluster_k)
        if args.cluster_n_harm is not None:
            a.cluster_calculator.n_harmonics = int(args.cluster_n_harm)
        a.train_cluster_centroids(wavs)
        a.save_centroids(out_csv)
        logger.info("Joint centroids written: %s", out_csv)
        return

    # Batch mode
    if args.batch:
        root = Path(args.batch)
        if not root.is_dir():
            logger.error("Batch directory not found: %s", root)
            sys.exit(1)
        wavs = sorted(p for p in root.rglob("*.wav") if p.is_file())
        if not wavs:
            logger.error("No .wav files under %s", root)
            sys.exit(1)
        logger.info("Batch: %d file(s)", len(wavs))
        saved = []
        failed = []
        for i, wav in enumerate(wavs, 1):
            logger.info("[%d/%d] %s", i, len(wavs), wav.name)
            try:
                # Save centroids from the FIRST file only (so later files can
                # load them); with --load-centroids, saving is pointless.
                do_save = (i == 1 and not args.load_centroids)
                out = _run_one(args, config, logger, str(wav),
                               save_centroids_once=do_save)
                saved.append(out)
            except Exception as e:  # noqa: BLE001
                logger.error("  failed: %s", e)
                failed.append(str(wav))
        logger.info("Batch complete: %d ok, %d failed", len(saved), len(failed))
        if failed:
            logger.warning("Failed files:")
            for f in failed:
                logger.warning("  %s", f)
            sys.exit(2)
        return

    # Single-file mode
    from config import DEFAULT_CONFIG
    audio_file = args.audio or DEFAULT_CONFIG.audio_file
    if not os.path.exists(audio_file):
        logger.error("Audio file not found: %s", audio_file)
        sys.exit(1)

    try:
        _run_one(args, config, logger, audio_file, save_centroids_once=True)
    except Exception as e:  # noqa: BLE001
        logger.error("Analysis failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
