#!/usr/bin/env python3
"""
Excel (.xlsx) export of a VRP analysis result.

Produces a single workbook with three kinds of sheet:

  Summary                whole-recording statistics per metric
                         (n_cells_nonzero, mean, median, std, min, max).
  Grouped                the full per-cell data (same as the CSV).
  <metric>               one heatmap-shaped pivot per metric
                         (rows = SPL dB, cols = MIDI, value = cell mean).

Metrics that are all-zero on this recording get a sheet anyway (keeps
the workbook structure consistent across recordings for downstream
scripting) but are flagged in the Summary column `has_data`.
"""

import os
import logging
from typing import Iterable, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# Columns the exporter knows about; anything else in the DataFrame is
# silently carried in the Grouped sheet but not pivoted. Keep in sync
# with analyzer.output_vrp_csv's standard_columns.
_METRIC_COLS = [
    # Acoustic
    "Clarity", "CPP", "SpecBal", "Crest", "Entropy",
    "Jitter", "JitterRAP", "JitterPPQ5",
    "Shimmer", "ShimmerDB", "ShimmerAPQ11", "HNR",
    # EGG
    "Qcontact", "Icontact", "dEGGmax", "HRFegg",
    "OQ", "SPQ", "CIQ",
    # Singing-specific
    "VibratoRate", "VibratoExtent",
    "F1", "F2", "F3", "SingersFormant",
    "H1H2", "H1H3",
    # Cluster
    "maxCluster", "Cluster 1", "Cluster 2", "Cluster 3", "Cluster 4", "Cluster 5",
    "maxCPhon", "cPhon 1", "cPhon 2", "cPhon 3", "cPhon 4", "cPhon 5",
    # Density
    "Total",
]


def _summary_row(col: str, s: pd.Series) -> dict:
    """Summary stats for one metric column. Uses nonzero cells only for
    mean/median/std so empty cells don't drag the average."""
    arr = s.values
    # For cluster-index metrics (integers), zero = "no data". For the
    # rest, zero can be a legitimate value (e.g. centered CIQ) so we
    # keep all cells for mean/median.
    if col in ("maxCluster", "maxCPhon"):
        nz = arr[arr > 0]
    else:
        nz = arr
    n = int(np.count_nonzero(arr)) if col.startswith(("max",)) else int(arr.size)
    if len(nz) == 0 or not np.isfinite(nz).any():
        return dict(metric=col, has_data=False, n_cells=n,
                    mean=np.nan, median=np.nan, std=np.nan,
                    min=np.nan, max=np.nan)
    finite = nz[np.isfinite(nz)]
    return dict(
        metric=col, has_data=bool((arr != 0).any()), n_cells=len(finite),
        mean=float(finite.mean()), median=float(np.median(finite)),
        std=float(finite.std()),
        min=float(finite.min()), max=float(finite.max()),
    )


def _pivot_for(col: str, df: pd.DataFrame) -> pd.DataFrame:
    """SPL × MIDI pivot for one metric; same orientation as the heatmap."""
    piv = df.pivot_table(index="dB", columns="MIDI", values=col,
                         aggfunc="mean", fill_value=np.nan)
    # Sort ascending on both axes so the top-left is the lowest voice
    piv = piv.sort_index(ascending=True).sort_index(axis=1, ascending=True)
    piv.index.name   = "SPL (dB)"
    piv.columns.name = "MIDI"
    return piv


def export_vrp_xlsx(grouped_df: pd.DataFrame,
                    out_path: str,
                    metrics: Optional[Iterable[str]] = None) -> str:
    """
    Write grouped VRP DataFrame to an .xlsx workbook.
    Returns the output path.
    """
    if metrics is None:
        metrics = [c for c in _METRIC_COLS if c in grouped_df.columns]
    else:
        metrics = [c for c in metrics if c in grouped_df.columns]

    # Summary sheet
    rows = [_summary_row(c, grouped_df[c]) for c in metrics]
    summary = pd.DataFrame(rows)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    logger.info("Writing Excel: %s  (%d metrics + Summary + Grouped)",
                out_path, len(metrics))

    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        # 1. Summary first so it opens on top
        summary.to_excel(xw, sheet_name="Summary", index=False)
        # 2. Full grouped data (same content as the _VRP.csv)
        grouped_df.to_excel(xw, sheet_name="Grouped", index=False)
        # 3. Per-metric heatmap pivot
        for col in metrics:
            if col in ("Total",):
                # Total gets a pivot too — sum instead of mean
                piv = grouped_df.pivot_table(index="dB", columns="MIDI",
                                               values=col, aggfunc="sum",
                                               fill_value=0).sort_index().sort_index(axis=1)
                piv.index.name, piv.columns.name = "SPL (dB)", "MIDI"
            else:
                piv = _pivot_for(col, grouped_df)
            # Excel sheet names: max 31 chars, no []:*?/\\
            safe = col.replace("/", "-").replace("\\", "-")[:31]
            piv.to_excel(xw, sheet_name=safe)

    return out_path
