# -*- coding: utf-8 -*-
"""VRP CSV writing + plot dispatch.

Extracted from ``VoiceMapAnalyzer.output_vrp_csv`` (was 253 lines,
overloaded with: dataframe building → range filter → cluster aggregation →
empty-cluster rescue → column ordering → CSV write → plot dispatch).

Kept as a free function. ``analyzer.output_vrp_csv`` now delegates here
so the public API is unchanged.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, Optional, TYPE_CHECKING

import numpy as np
import pandas as pd

from voicemap.logger import get_logger
from voicemap.plotter import plot_vrp_dataframe, plot_vrp_combined

if TYPE_CHECKING:
    from voicemap.analyzer import VoiceMapAnalyzer

logger = get_logger(__name__)


def write_vrp(analyzer: "VoiceMapAnalyzer",
              metrics: Dict[str, np.ndarray],
              return_df: bool = False,
              plot_mode: str = "per-metric",
              export_plots: Optional[bool] = None,
              write_disk: bool = True):
    """Build the per-cell aggregate DataFrame, optionally write it to CSV
    and emit per-metric / combined PNGs.

    plot_mode:
      "none"       — skip PNG export (fastest; GUI embeds in-memory)
      "per-metric" — one PNG per active metric (default; CLI-compatible)
      "combined"   — single overview PNG with a grid of all metrics

    `export_plots` is a legacy bool kwarg. False ⇒ "none", True ⇒ keep
    current plot_mode; kept so older callers still work.

    Returns ``out_file`` (str) by default, or ``(out_file, grouped_df)``
    when ``return_df=True``. ``out_file`` is empty when ``write_disk=False``.
    """
    if export_plots is False:
        plot_mode = "none"
    config = analyzer.config
    logger.info("Outputting VRP CSV...")
    spl_corr = metrics['spl'] + config.spl_correction_db

    # Cluster labels may be shorter than metric arrays (e.g. trailing cycles
    # dropped during feature extraction); align to the shortest array.
    base_n = len(metrics['midi'])
    cluster = metrics.get('cluster', np.zeros(base_n, dtype=np.int32))
    phon    = metrics.get('phon',    np.zeros(base_n, dtype=np.int32))
    if len(cluster) < base_n:
        cluster = np.concatenate([cluster, np.zeros(base_n - len(cluster),
                                                     dtype=cluster.dtype)])
    if len(phon) < base_n:
        phon = np.concatenate([phon, np.zeros(base_n - len(phon),
                                               dtype=phon.dtype)])

    # P1 per-cycle scalars: align to base_n same as cluster arrays
    def _pad(arr, n, dtype=np.float64):
        if arr is None:
            return np.zeros(n, dtype=dtype)
        arr = np.asarray(arr, dtype=dtype)
        if len(arr) < n:
            return np.concatenate([arr, np.zeros(n - len(arr), dtype=dtype)])
        return arr[:n]

    df = pd.DataFrame({
        'MIDI':     np.round(np.where(metrics['midi'] > 0, metrics['midi'], 0)).astype(int),
        'dB':       np.round(np.where(spl_corr > 0, spl_corr, 0)).astype(int),
        'Total':    1,
        'Clarity':  metrics['clarity'],
        'CPP':      metrics['cpp'],
        'SpecBal':  metrics['specbal'],
        'Crest':    metrics['crest'],
        'Entropy':  metrics['entropy'],
        'Qcontact': metrics['qcontact'],
        'dEGGmax':  metrics['deggmax'],
        'Icontact': metrics['icontact'],
        'HRFegg':   metrics['hrf'],
        'Jitter':        _pad(metrics.get('jitter'),        base_n),
        'JitterRAP':     _pad(metrics.get('jitter_rap'),    base_n),
        'JitterPPQ5':    _pad(metrics.get('jitter_ppq5'),   base_n),
        'Shimmer':       _pad(metrics.get('shimmer'),       base_n),
        'ShimmerDB':     _pad(metrics.get('shimmer_db'),    base_n),
        'ShimmerAPQ3':   _pad(metrics.get('shimmer_apq3'),  base_n),
        'ShimmerAPQ5':   _pad(metrics.get('shimmer_apq5'),  base_n),
        'ShimmerAPQ11':  _pad(metrics.get('shimmer_apq11'), base_n),
        'HNR':           _pad(metrics.get('hnr'),           base_n),
        'NHR':           _pad(metrics.get('nhr'),           base_n),
        'CPPS':          _pad(metrics.get('cpps'),          base_n),
        'PPE':           _pad(metrics.get('ppe'),           base_n),
        'ZCR':           _pad(metrics.get('zcr'),           base_n),
        # 频谱形态 / 声压 / Vibrato / GNE / 共振峰带宽（待验证）
        'RMS':                _pad(metrics.get('rms'),               base_n),
        'F0_Hz':              _pad(metrics.get('f0_hz'),             base_n),
        'SpectralCentroid':   _pad(metrics.get('spec_centroid'),     base_n),
        'SpectralBandwidth':  _pad(metrics.get('spec_bandwidth'),    base_n),
        'SpectralRolloff85':  _pad(metrics.get('spec_rolloff85'),    base_n),
        'SpectralFlatness':   _pad(metrics.get('spec_flatness'),     base_n),
        'SpectralSlope':      _pad(metrics.get('spec_slope'),        base_n),
        'SpectralSkewness':   _pad(metrics.get('spec_skewness'),     base_n),
        'SpectralKurtosis':   _pad(metrics.get('spec_kurtosis'),     base_n),
        'AlphaRatio':         _pad(metrics.get('alpha_ratio'),       base_n),
        'HammarbergIndex':    _pad(metrics.get('hammarberg'),        base_n),
        'B1':                 _pad(metrics.get('b1'),                base_n),
        'B2':                 _pad(metrics.get('b2'),                base_n),
        'B3':                 _pad(metrics.get('b3'),                base_n),
        'FormantDispersion':  _pad(metrics.get('formant_dispersion'),base_n),
        'SPR':                _pad(metrics.get('spr'),               base_n),
        'GNE':                _pad(metrics.get('gne'),               base_n),
        'MPT':                _pad(metrics.get('mpt'),               base_n),
        'VoicingRatio':       _pad(metrics.get('voicing_ratio'),     base_n),
        'DUV':                _pad(metrics.get('duv'),               base_n),
        'VibratoJitter':      _pad(metrics.get('vib_jitter'),        base_n),
        **{f'MFCC{i+1}':      _pad(metrics.get(f'mfcc{i+1}'),        base_n)
           for i in range(13)},
        'VibratoRate':   _pad(metrics.get('vibrato_rate'),   base_n),
        'VibratoExtent': _pad(metrics.get('vibrato_extent'), base_n),
        'F1':            _pad(metrics.get('f1'),  base_n),
        'F2':            _pad(metrics.get('f2'),  base_n),
        'F3':            _pad(metrics.get('f3'),  base_n),
        'SingersFormant': _pad(metrics.get('sfe'), base_n),
        'H1H2':           _pad(metrics.get('h1h2'), base_n),
        'H1H3':           _pad(metrics.get('h1h3'), base_n),
        'OQ':             _pad(metrics.get('oq'),  base_n),
        'SPQ':            _pad(metrics.get('spq'), base_n),
        'CIQ':            _pad(metrics.get('ciq'), base_n),
        '_cluster': cluster.astype(int),
        '_phon':    phon.astype(int),
    })
    logger.info("  Raw points: %d", len(df))

    range_mask = (
        (df['MIDI'] >= config.n_min_midi) & (df['MIDI'] <= config.n_max_midi) &
        (df['dB']   >= config.n_min_spl)  & (df['dB']   <= config.n_max_spl)
    )
    df = df[range_mask].copy()
    logger.info("  After range filter: %d", len(df))

    # Per-cell aggregation for scalar metrics
    grouped = df.groupby(['MIDI', 'dB']).agg({
        'Clarity': 'max',   # SC VRPControllerPlots: max(clarity, clarityMap.at(...) ? 0)
        'CPP': 'mean', 'SpecBal': 'mean',
        'Crest': 'mean', 'Entropy': 'mean', 'Qcontact': 'mean',
        'dEGGmax': 'mean', 'Icontact': 'mean', 'HRFegg': 'mean',
        'Jitter': 'mean', 'JitterRAP': 'mean', 'JitterPPQ5': 'mean',
        'Shimmer': 'mean', 'ShimmerDB': 'mean',
        'ShimmerAPQ3': 'mean', 'ShimmerAPQ5': 'mean', 'ShimmerAPQ11': 'mean',
        'HNR': 'mean', 'NHR': 'mean',
        'CPPS': 'mean', 'PPE': 'mean', 'ZCR': 'mean',
        # 扩展指标
        'RMS': 'mean', 'F0_Hz': 'mean',
        'SpectralCentroid': 'mean', 'SpectralBandwidth': 'mean',
        'SpectralRolloff85': 'mean', 'SpectralFlatness': 'mean',
        'SpectralSlope': 'mean', 'SpectralSkewness': 'mean',
        'SpectralKurtosis': 'mean',
        'AlphaRatio': 'mean', 'HammarbergIndex': 'mean',
        'B1': 'mean', 'B2': 'mean', 'B3': 'mean',
        'FormantDispersion': 'mean',
        'SPR': 'mean', 'GNE': 'mean',
        'MPT': 'mean', 'VoicingRatio': 'mean', 'DUV': 'mean',
        'VibratoJitter': 'mean',
        **{f'MFCC{i+1}': 'mean' for i in range(13)},
        'VibratoRate': 'mean', 'VibratoExtent': 'mean',
        'F1': 'mean', 'F2': 'mean', 'F3': 'mean',
        'SingersFormant': 'mean',
        'H1H2': 'mean', 'H1H3': 'mean',
        'OQ': 'mean', 'SPQ': 'mean', 'CIQ': 'mean',
        'Total': 'sum',
    }).reset_index()

    # Empty-cluster rescue, post-clarity-filter. sklearn KMeans can leave
    # a cluster empty; our in-calculator rescue reassigns a "worst-fit"
    # cycle to fill it, but that cycle often fails the clarity gate and
    # disappears from the filtered df — leaving the cluster empty again
    # by the time we aggregate. Here we sweep the filtered df itself
    # and reassign ONE cycle to each missing label so every k in
    # {1..n_clusters} is represented in the VRP output.
    def _rescue_empty(col: str, n: int):
        present = set(df[col].values[df[col].values > 0])
        for k in range(1, n + 1):
            if k in present:
                continue
            candidates = df.index[df[col] > 0]
            if len(candidates):
                df.at[candidates[0], col] = k
                logger.info("  Empty %s=%d rescued (reassigned 1 cycle "
                            "in filtered set so VRP has all %d clusters)",
                            col, k, n)

    _rescue_empty('_cluster', 5)
    _rescue_empty('_phon',    5)

    # Per-cell cluster aggregation: maxCluster = dominant label; Cluster k = %
    cluster_cols = analyzer._aggregate_cluster_labels(
        df, label_col='_cluster', n=5, prefix='Cluster ', max_col='maxCluster')
    phon_cols = analyzer._aggregate_cluster_labels(
        df, label_col='_phon',    n=5, prefix='cPhon ',   max_col='maxCPhon')

    grouped = grouped.merge(cluster_cols, on=['MIDI', 'dB'], how='left')
    grouped = grouped.merge(phon_cols,    on=['MIDI', 'dB'], how='left')

    standard_columns = [
        'MIDI', 'dB', 'Total', 'Clarity', 'Crest', 'SpecBal', 'CPP', 'Entropy',
        'dEGGmax', 'Qcontact', 'Icontact', 'HRFegg',
        # P3 (EGG timing)
        'OQ', 'SPQ', 'CIQ',
        # P1
        'Jitter', 'JitterRAP', 'JitterPPQ5',
        'Shimmer', 'ShimmerDB',
        'ShimmerAPQ3', 'ShimmerAPQ5', 'ShimmerAPQ11',
        'HNR',
        # Add-on voice-quality (待验证)
        'NHR', 'CPPS', 'PPE', 'ZCR',
        # 频谱形态 / 声压 / Vibrato / GNE / 共振峰带宽（待验证）
        'RMS', 'F0_Hz',
        'SpectralCentroid', 'SpectralBandwidth', 'SpectralRolloff85',
        'SpectralFlatness', 'SpectralSlope',
        'SpectralSkewness', 'SpectralKurtosis',
        'AlphaRatio', 'HammarbergIndex',
        'B1', 'B2', 'B3', 'FormantDispersion',
        'SPR', 'GNE',
        'MPT', 'VoicingRatio', 'DUV',
        'VibratoJitter',
        *(f'MFCC{i+1}' for i in range(13)),
        # P2 (singing-specific)
        'VibratoRate', 'VibratoExtent',
        'F1', 'F2', 'F3', 'SingersFormant',
        'H1H2', 'H1H3',
        # P0 cluster
        'maxCluster',
        'Cluster 1', 'Cluster 2', 'Cluster 3', 'Cluster 4', 'Cluster 5',
        'maxCPhon', 'cPhon 1', 'cPhon 2', 'cPhon 3', 'cPhon 4', 'cPhon 5',
    ]
    for col in standard_columns:
        if col not in grouped.columns:
            grouped[col] = 0
        grouped[col] = grouped[col].fillna(0)
    grouped = grouped[standard_columns]

    if write_disk:
        os.makedirs(config.output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = f"{config.output_dir}/complete_vrp_results_{ts}_VRP.csv"
        grouped.to_csv(out_file, index=False, sep=';')
        logger.info("Saved: %s", out_file)
    else:
        out_file = ""   # no disk write — caller is doing a partial render

    logger.info("=== VRP Statistics ===")
    logger.info("Unique (MIDI,dB) pairs: %d  Total cycles: %d",
                len(grouped), grouped['Total'].sum())
    logger.info("MIDI %.1f  SPL %.1f dB  Clarity %.3f",
                grouped['MIDI'].mean(), grouped['dB'].mean(),
                grouped['Clarity'].mean())

    # --- Generate VRP map images ---
    # 22 PNGs at dpi=150 via savefig cost ~0.4s each → dominates wall time.
    # Caller picks the trade-off: none / per-metric / combined overview.
    # Skip entirely if no disk write requested (partial render path).
    if not write_disk or plot_mode == "none":
        if plot_mode == "none":
            logger.info("Skipping PNG export (plot_mode=none)")
    else:
        plot_dir = os.path.join(config.output_dir, "plots")
        ts_base  = os.path.splitext(os.path.basename(out_file))[0]
        if plot_mode == "combined":
            saved_path = plot_vrp_combined(grouped, ts_base, plot_dir)
            if saved_path:
                logger.info("Combined overview saved: %s", saved_path)
        else:   # "per-metric"
            saved = plot_vrp_dataframe(grouped, ts_base, plot_dir)
            if saved:
                logger.info("Plots saved to: %s  (%d images)",
                            plot_dir, len(saved))

    if return_df:
        return out_file, grouped
    return out_file
