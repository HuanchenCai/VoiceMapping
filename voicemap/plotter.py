#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VoiceMap VRP Plotter
Saves a PNG map for every non-empty metric column in the grouped VRP CSV.
Colour scales reproduce the exact HSV/RGB formulas from FonaDyn's Metric*.sc files.
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")           # headless – no display needed
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.colors import Normalize, LogNorm
from typing import Optional

matplotlib.rcParams["font.family"] = ["Microsoft YaHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

# ---------------------------------------------------------------------------
# VRP grid constants  (must match VRPDataVRP.sc)
# ---------------------------------------------------------------------------
MIDI_MIN, MIDI_MAX = 30, 96
SPL_MIN,  SPL_MAX  = 40, 120

# ---------------------------------------------------------------------------
# Modern color policy (2026 refactor):
# the legacy SC HSV rainbow sweeps were colorblind-unfriendly and printed
# to nearly identical greys on B&W. All metrics now use one of three
# perceptually-uniform palettes — see metrics_registry.PALETTE_*.
# Sequential metrics → viridis. Diverging (SpecBal, etc.) → coolwarm.
# Density (cycle count, log axis) → mako (or viridis fallback).
# Palette factories live in metrics_registry; we just resolve the strings.
from voicemap.metrics_registry import (
    PALETTE_SEQUENTIAL, PALETTE_DIVERGING,
    _density_cmap_modern as _modern_density,
    _categorical_cmap_5 as _modern_cat5,
)

# Legacy hand-built _CMAP table — every entry just resolves to one of the
# three palettes. New metrics get the same palette via spec.cmap when
# the registry-merge runs below; no need to add rows here for them.
_CMAP = {
    "CPP":      PALETTE_SEQUENTIAL,
    "Crest":    PALETTE_SEQUENTIAL,
    "dEGGmax":  PALETTE_SEQUENTIAL,
    "Icontact": PALETTE_SEQUENTIAL,
    "Qcontact": PALETTE_SEQUENTIAL,
    "HRFegg":   PALETTE_SEQUENTIAL,
    "Clarity":  PALETTE_SEQUENTIAL,
    "Entropy":  PALETTE_SEQUENTIAL,
    "SpecBal":  PALETTE_DIVERGING,
    "Total":    _modern_density(),     # mako with viridis fallback
}

# ---------------------------------------------------------------------------
# Per-metric display configuration  (vmin/vmax = FonaDyn minVal/maxVal)
# ---------------------------------------------------------------------------
# norm=None  → linear Normalize(vmin, vmax)
# norm=LogNorm → logarithmic axis (dEGGmax, Total)
# ---------------------------------------------------------------------------
METRIC_CFG = {
    "Clarity": dict(
        label="Audio Clarity",
        vmin=0.96, vmax=1.0,
        unit="",
        cmap=_CMAP["Clarity"],
        norm=None,
    ),
    "CPP": dict(
        label="CPP",
        vmin=0.0, vmax=30.0,
        unit="dB",
        cmap=_CMAP["CPP"],
        norm=None,
    ),
    "SpecBal": dict(
        label="Spectrum Balance",
        vmin=-42.0, vmax=0.0,
        unit="dB",
        cmap=_CMAP["SpecBal"],
        norm=None,
    ),
    "Crest": dict(
        label="Crest Factor",
        vmin=1.414, vmax=4.0,
        unit="",
        cmap=_CMAP["Crest"],
        norm=None,
    ),
    "Entropy": dict(
        label="Sample Entropy (CSE)",
        vmin=0.0, vmax=10.0,
        unit="",
        cmap=_CMAP["Entropy"],
        norm=None,
    ),
    "Qcontact": dict(
        label="Qci - Contact Quotient",
        vmin=0.1, vmax=0.6,
        unit="",
        cmap=_CMAP["Qcontact"],
        norm=None,
    ),
    "dEGGmax": dict(
        label="Qdelta - Peak dEGG",
        vmin=1.0, vmax=20.0,
        unit="slope",
        cmap=_CMAP["dEGGmax"],
        norm=LogNorm(vmin=1.0, vmax=20.0, clip=True),   # SC: explin -> log axis
    ),
    "Icontact": dict(
        label="Ic - Index of Contacting",
        vmin=0.0, vmax=0.7,
        unit="",
        cmap=_CMAP["Icontact"],
        norm=None,
    ),
    "HRFegg": dict(
        label="HRFegg - EGG Harmonic Richness Factor",
        vmin=-30.0, vmax=10.0,
        unit="dB",
        cmap=_CMAP["HRFegg"],
        norm=None,
    ),
    "Total": dict(
        label="Density - Cycle Count",
        vmin=1, vmax=10000,
        unit="c",
        cmap=_CMAP["Total"],
        norm=LogNorm(vmin=1, vmax=10000, clip=True),     # SC: explin -> log axis
    ),
    # ── P1: Jitter / Shimmer / HNR  (clinical voice-quality indices) ──
    # Jitter family: higher = worse; green→red sweep. Clinical pathological
    # threshold is around 1.04% for local jitter (MDVP norm) so vmax=3 puts
    # normal at the cool end, warning at the hot end.
    "Jitter": dict(
        label="Jitter (local)",
        vmin=0.0, vmax=3.0, unit="%",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    "JitterRAP": dict(
        label="Jitter RAP (3-pt)",
        vmin=0.0, vmax=3.0, unit="%",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    "JitterPPQ5": dict(
        label="Jitter PPQ5 (5-pt)",
        vmin=0.0, vmax=3.0, unit="%",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    # Shimmer family: pathological threshold ~3.8% for local shimmer.
    "Shimmer": dict(
        label="Shimmer (local)",
        vmin=0.0, vmax=10.0, unit="%",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    "ShimmerDB": dict(
        label="Shimmer",
        vmin=0.0, vmax=1.0, unit="dB",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    "ShimmerAPQ11": dict(
        label="Shimmer APQ11 (11-pt)",
        vmin=0.0, vmax=10.0, unit="%",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    "ShimmerAPQ3": dict(
        label="Shimmer APQ3 (3-pt)",
        vmin=0.0, vmax=10.0, unit="%",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    "ShimmerAPQ5": dict(
        label="Shimmer APQ5 (5-pt)",
        vmin=0.0, vmax=10.0, unit="%",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    # HNR: higher = healthier voice (>20 dB normal). Use blue→red reversed
    # so high values (good) are cool/calm and low values (noisy) are hot.
    "HNR": dict(
        label="HNR",
        vmin=0.0, vmax=35.0, unit="dB",
        cmap=PALETTE_SEQUENTIAL,   # red→blue (low→high)
        norm=None,
    ),
    # ── Add-on voice-quality metrics (待验证) ──────────────────────────────
    # NHR (Noise-to-Harmonics): inverse of HNR. >0.19 pathological (MDVP).
    # Low = clean. Green→red so "normal" reads cool, "noisy" reads hot.
    "NHR": dict(
        label="NHR (Noise-to-Harm)",
        vmin=0.0, vmax=0.5, unit="",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    # CPPS (smoothed CPP). Same scale as CPP, moving-averaged temporally.
    "CPPS": dict(
        label="CPPS (smoothed CPP)",
        vmin=0.0, vmax=30.0, unit="dB",
        cmap=_CMAP["CPP"],
        norm=None,
    ),
    # PPE (pitch period entropy). 0-1 after log(n_bins) normalisation.
    # 0 = perfectly periodic, 1 = maximally irregular.
    "PPE": dict(
        label="Pitch Period Entropy",
        vmin=0.0, vmax=1.0, unit="",
        cmap=PALETTE_SEQUENTIAL,   # green→red (stable→noisy)
        norm=None,
    ),
    # ZCR (zero-crossing rate) per cycle. Range typically 0.01–0.2 for voice.
    "ZCR": dict(
        label="Zero-Crossing Rate",
        vmin=0.0, vmax=0.3, unit="",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    # ── P2 Singing-specific ────────────────────────────────────────────────
    # Vibrato rate: typical singer 5-7 Hz; Peking opera often 5-6 Hz.
    # vmin/vmax span the realistic vibrato band; mid-green = healthy.
    "VibratoRate": dict(
        label="Vibrato rate",
        vmin=3.0, vmax=9.0, unit="Hz",
        cmap=PALETTE_SEQUENTIAL,   # blue→red across band
        norm=None,
    ),
    # Vibrato extent: 50-150 cents typical; classical Western ~80, Peking often wider.
    "VibratoExtent": dict(
        label="Vibrato extent",
        vmin=0.0, vmax=300.0, unit="cents",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    # Formants: vocal-tract resonances. Typical ranges for a mixed voice:
    #   F1 ~ 300-1000 Hz   (vowel height)
    #   F2 ~ 900-2500 Hz   (vowel backness)
    #   F3 ~ 2200-3500 Hz  (articulation, part of singer's formant cluster)
    "F1": dict(
        label="F1 — 1st formant",
        vmin=200.0, vmax=1000.0, unit="Hz",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    "F2": dict(
        label="F2 — 2nd formant",
        vmin=800.0, vmax=2800.0, unit="Hz",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    "F3": dict(
        label="F3 — 3rd formant",
        vmin=2000.0, vmax=3600.0, unit="Hz",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    "SingersFormant": dict(
        label="Singer's Formant Energy",
        vmin=-25.0, vmax=-5.0, unit="dB",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    # H1-H2 / H1-H3 spectral tilt — diverging around 0:
    # negative = pressed, ~0 = modal, positive = breathy.
    "H1H2": dict(
        label="H1-H2  (voice)",
        vmin=-10.0, vmax=20.0, unit="dB",
        cmap=PALETTE_DIVERGING,
        norm=None,
    ),
    "H1H3": dict(
        label="H1-H3  (voice)",
        vmin=-10.0, vmax=25.0, unit="dB",
        cmap=PALETTE_DIVERGING,
        norm=None,
    ),
    # ── P3 EGG timing quotients ────────────────────────────────────────────
    "OQ": dict(
        label="Open Quotient",
        vmin=0.2, vmax=0.8, unit="",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    "SPQ": dict(
        label="Speed Quotient",
        vmin=0.3, vmax=3.0, unit="",
        cmap=PALETTE_SEQUENTIAL,
        norm=None,
    ),
    # CIQ — diverging (signed asymmetry around 0)
    "CIQ": dict(
        label="Contact Index",
        vmin=-0.6, vmax=0.6, unit="",
        cmap=PALETTE_DIVERGING,
        norm=None,
    ),
    # ── EGG waveform clusters ───────────────────────────────────────────────
    # maxCluster / maxCPhon: dominant cluster id (1..5). Use a discrete 5-step
    # qualitative palette so you can visually distinguish which mode dominates
    # each cell. vmin/vmax tight around the integer range → each bin maps to
    # one colour.
    "maxCluster": dict(
        label="Dominant EGG cluster",
        vmin=0.5, vmax=5.5, unit="",
        cmap=_modern_cat5(),
        norm=None,
    ),
    "maxCPhon": dict(
        label="Dominant phonation cluster",
        vmin=0.5, vmax=5.5, unit="",
        cmap=_modern_cat5(),
        norm=None,
    ),
    # Cluster k / cPhon k: percent of cycles in cell assigned to cluster k.
    # Continuous 0-100% with a perceptually-ordered colormap.
    **{f"Cluster {k}": dict(
        label=f"EGG cluster {k} share",
        vmin=0, vmax=100, unit="%",
        cmap=plt.get_cmap("viridis"),
        norm=None) for k in range(1, 6)},
    **{f"cPhon {k}": dict(
        label=f"Phonation cluster {k} share",
        vmin=0, vmax=100, unit="%",
        cmap=plt.get_cmap("magma"),
        norm=None) for k in range(1, 6)},
}

# Metrics excluded from the combined overview figure (too many sub-metrics,
# clutters the grid). Cluster breakdowns are still rendered individually.
_SKIP_COMBINED = {
    "Icontact", "HRFegg",
    "Cluster 1", "Cluster 2", "Cluster 3", "Cluster 4", "Cluster 5",
    "cPhon 1",   "cPhon 2",   "cPhon 3",   "cPhon 4",   "cPhon 5",
}

# Metric → short category tag for titling. Kept in sync with the GUI's
# _METRIC_SECTIONS but trimmed to an ASCII prefix so matplotlib renders
# it consistently (no reliance on Chinese-glyph font coverage at the
# plot level).
METRIC_CATEGORY = {
    # Acoustic
    **{m: "Acoustic" for m in (
        "Clarity", "CPP", "SpecBal", "Crest", "Entropy",
        "Jitter", "JitterRAP", "JitterPPQ5",
        "Shimmer", "ShimmerDB",
        "ShimmerAPQ3", "ShimmerAPQ5", "ShimmerAPQ11",
        "HNR", "NHR", "CPPS", "PPE", "ZCR")},
    # EGG
    **{m: "EGG" for m in (
        "Qcontact", "Icontact", "dEGGmax", "HRFegg",
        "OQ", "SPQ", "CIQ")},
    # Singing-specific
    **{m: "Singing" for m in (
        "VibratoRate", "VibratoExtent",
        "F1", "F2", "F3", "SingersFormant",
        "H1H2", "H1H3")},
    # Cluster
    **{m: "Cluster" for m in (
        "maxCluster", "Cluster 1", "Cluster 2", "Cluster 3",
        "Cluster 4", "Cluster 5",
        "maxCPhon", "cPhon 1", "cPhon 2", "cPhon 3",
        "cPhon 4", "cPhon 5")},
    "Total": "Density",
}


# ── Merge any keys from metrics_registry that aren't already in our
# hand-crafted METRIC_CFG / METRIC_CATEGORY. New metrics appear in
# plots automatically just by calling register(MetricSpec(...)) — no
# plotter edit needed.
def _merge_registry_into_plotter():
    try:
        from voicemap.metrics_registry import REGISTRY
    except ImportError:
        return
    for spec in REGISTRY.values():
        cmap = spec.cmap
        if isinstance(cmap, str) and cmap in _CMAP:
            cmap = _CMAP[cmap]
        if spec.key not in METRIC_CFG:
            METRIC_CFG[spec.key] = dict(
                label=spec.label or spec.key,
                vmin=spec.vmin, vmax=spec.vmax,
                unit=spec.unit, cmap=cmap, norm=spec.norm)
        if spec.key not in METRIC_CATEGORY:
            METRIC_CATEGORY[spec.key] = spec.category


_merge_registry_into_plotter()


def _build_grid(df: pd.DataFrame, col: str) -> np.ma.MaskedArray:
    """Fill a (SPL × MIDI) masked array from grouped VRP data."""
    n_midi = MIDI_MAX - MIDI_MIN + 1
    n_spl  = SPL_MAX  - SPL_MIN  + 1
    grid = np.full((n_spl, n_midi), np.nan)

    midi_arr = df["MIDI"].to_numpy(dtype=int)
    spl_arr  = df["dB"].to_numpy(dtype=int)
    val_arr  = df[col].to_numpy(dtype=float)
    mi = midi_arr - MIDI_MIN
    si = spl_arr  - SPL_MIN
    mask = (mi >= 0) & (mi < n_midi) & (si >= 0) & (si < n_spl)
    grid[si[mask], mi[mask]] = val_arr[mask]

    return np.ma.masked_invalid(grid)


def _draw_vrp_ax(ax, fig, df: pd.DataFrame, col: str) -> bool:
    """Draw one VRP metric into *ax*. Returns False when the column is empty."""
    cfg = METRIC_CFG.get(col, dict(
        label=col, vmin=None, vmax=None, unit="", cmap="viridis", norm=None
    ))

    grid = _build_grid(df, col)
    if grid.count() == 0:
        return False

    vmin = cfg["vmin"] if cfg["vmin"] is not None else float(np.nanmin(grid))
    vmax = cfg["vmax"] if cfg["vmax"] is not None else float(np.nanmax(grid))
    if vmin >= vmax:
        vmax = vmin + 1.0

    # ── Colour scheme ────────────────────────────────────────────────────
    # White background for the plot area so exported PNGs and Excel
    # figures drop straight into papers/slides without inverting. Empty
    # cells are a slightly-off-white so you can still see them against
    # the plot face. All text and axis chrome is black/dark-grey for
    # contrast. Tokens live in voicemap.gui.theme so chart palette
    # changes are one-line edits.
    from voicemap.gui.theme import (
        PLOT_BG_AX  as _BG_AX,
        PLOT_BG_EMPTY as _BG_EMPTY,
        PLOT_FG     as _FG_TEXT,
        PLOT_FG_SPINE as _FG_SPINE,
        PLOT_GRID   as _GRID_MAJOR,
        PLOT_GRID_LIGHT as _GRID_MINOR,
        PLOT_FG_DIM as _CAT_TAG,
    )
    ax.set_facecolor(_BG_AX)

    midi_edges = np.arange(MIDI_MIN - 0.5, MIDI_MAX + 1.5)
    spl_edges  = np.arange(SPL_MIN  - 0.5, SPL_MAX  + 1.5)

    # Custom colormaps are already new objects; built-in names need a copy
    raw_cmap = cfg["cmap"]
    if isinstance(raw_cmap, str):
        cmap_obj = plt.get_cmap(raw_cmap).copy()
    else:
        cmap_obj = raw_cmap
    cmap_obj.set_bad(color=_BG_EMPTY)

    norm = cfg.get("norm") or Normalize(vmin=vmin, vmax=vmax)

    mesh = ax.pcolormesh(
        midi_edges, spl_edges, grid,
        cmap=cmap_obj, norm=norm,
        shading="flat",
        rasterized=True,
    )

    unit_str = f" [{cfg['unit']}]" if cfg["unit"] else ""
    cbar = fig.colorbar(mesh, ax=ax, fraction=0.03, pad=0.01)
    cbar.ax.yaxis.set_tick_params(color=_FG_TEXT)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color=_FG_TEXT, fontsize=7)
    cbar.outline.set_edgecolor(_FG_SPINE)

    # X axis: major ticks every 6 semitones labelled as MIDI numbers
    major_ticks = list(range(30, MIDI_MAX + 1, 6))
    ax.set_xticks(major_ticks)
    ax.set_xticklabels([str(m) for m in major_ticks], color=_FG_TEXT, fontsize=7)
    ax.xaxis.set_minor_locator(mticker.MultipleLocator(1))
    ax.set_xlim(MIDI_MIN - 0.5, MIDI_MAX + 0.5)
    ax.set_xlabel("MIDI", color=_FG_TEXT, fontsize=7)

    # Y axis: SPL in dB
    ax.set_yticks(range(SPL_MIN, SPL_MAX + 1, 10))
    ax.set_yticklabels(
        [str(v) for v in range(SPL_MIN, SPL_MAX + 1, 10)],
        color=_FG_TEXT, fontsize=7,
    )
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(5))
    ax.set_ylim(SPL_MIN - 0.5, SPL_MAX + 0.5)
    ax.set_ylabel("SPL (dB)", color=_FG_TEXT, fontsize=7)

    ax.tick_params(axis="both", which="both", colors=_FG_TEXT, labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor(_FG_SPINE)
    ax.grid(which="major", color=_GRID_MAJOR, linewidth=0.4, linestyle="--")
    ax.grid(which="minor", color=_GRID_MINOR, linewidth=0.2)

    # Title + category tag
    main_title = f"{cfg['label']}{unit_str}"
    ax.set_title(main_title, color=_FG_TEXT, fontsize=9, pad=4)
    cat = METRIC_CATEGORY.get(col)
    if cat:
        ax.text(1.0, 1.02, cat, transform=ax.transAxes,
                ha="right", va="bottom",
                color=_CAT_TAG, fontsize=7, style="italic")
    return True


def _plot_one(df: pd.DataFrame, col: str, out_path: str, basename: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("white")
    if not _draw_vrp_ax(ax, fig, df, col):
        plt.close(fig)
        return
    fig.tight_layout()
    fname = os.path.join(out_path, f"{basename}_{col}.png")
    fig.savefig(fname, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def plot_vrp_combined(
    df: pd.DataFrame,
    basename: str,
    out_dir: str,
    metrics: Optional[list] = None,
    ncols: int = 5,
) -> Optional[str]:
    """Save all VRP metrics as subplots in one figure. Returns saved path or None."""
    if metrics is None:
        candidates = [c for c in METRIC_CFG if c not in _SKIP_COMBINED]
        metrics = [c for c in candidates if c in df.columns and df[c].sum() != 0]

    if not metrics:
        return None

    nrows = (len(metrics) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 7, nrows * 5), squeeze=False)
    fig.patch.set_facecolor("white")

    for idx, col in enumerate(metrics):
        _draw_vrp_ax(axes[idx // ncols][idx % ncols], fig, df, col)

    for idx in range(len(metrics), nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    from voicemap.gui.theme import PLOT_FG as _FG
    fig.suptitle(basename, color=_FG, fontsize=13, y=1.01)
    fig.tight_layout()

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{basename}_combined.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def _active_metrics(df: pd.DataFrame, requested: Optional[list]) -> list:
    if requested is not None:
        return requested
    candidates = [c for c in df.columns if c not in {"MIDI", "dB"}]
    return [c for c in candidates if df[c].sum() != 0]


def plot_vrp_dataframe(
    df: pd.DataFrame,
    basename: str,
    out_dir: str,
    metrics: Optional[list] = None,
) -> list:
    """Plot directly from the grouped DataFrame returned by the analyser.
    Saves one PNG per non-empty metric column; returns the list of paths
    that were actually written."""
    os.makedirs(out_dir, exist_ok=True)
    saved = []
    for col in _active_metrics(df, metrics):
        if col not in df.columns:
            continue
        _plot_one(df, col, out_dir, basename)
        fpath = os.path.join(out_dir, f"{basename}_{col}.png")
        if os.path.exists(fpath):
            saved.append(fpath)
    return saved


def plot_vrp_csv(
    csv_path: str,
    out_dir: Optional[str] = None,
    metrics: Optional[list] = None,
) -> list:
    """Load a semicolon-delimited _VRP.csv then delegate to plot_vrp_dataframe."""
    df = pd.read_csv(csv_path, sep=";")
    if out_dir is None:
        out_dir = os.path.dirname(csv_path)
    basename = os.path.splitext(os.path.basename(csv_path))[0]
    return plot_vrp_dataframe(df, basename, out_dir, metrics)


draw_vrp_on_ax = _draw_vrp_ax


# ───────────────────────────────────────────────────────────────────────────
# Cross-recording comparison: A | B | A − B, same metric.
# ───────────────────────────────────────────────────────────────────────────
def draw_vrp_comparison(df_a: pd.DataFrame,
                         df_b: pd.DataFrame,
                         col: str,
                         fig,
                         label_a: str = "A",
                         label_b: str = "B") -> bool:
    """Render three heatmaps on `fig`: A | B | A − B. Returns False if
    the metric is missing or empty in both inputs."""
    if col not in df_a.columns or col not in df_b.columns:
        return False
    ga = _build_grid(df_a, col)
    gb = _build_grid(df_b, col)
    if ga.count() == 0 and gb.count() == 0:
        return False

    cfg = METRIC_CFG.get(col, dict(label=col, vmin=None, vmax=None,
                                     unit="", cmap="viridis", norm=None))
    # Comparison palette: white canvas, dark text. Matches the single-metric
    # style so an A|B|Δ export sits next to a single-metric one in a paper
    # without colour-scheme mismatch.
    from voicemap.gui.theme import (
        PLOT_BG_AX  as _BG_AX,
        PLOT_BG_EMPTY as _BG_EMPTY,
        PLOT_FG     as _FG_TEXT,
        PLOT_FG_SPINE as _FG_SPINE,
        PLOT_GRID   as _GRID,
    )

    fig.clear()
    fig.patch.set_facecolor("white")
    axes = fig.subplots(1, 3)

    midi_edges = np.arange(MIDI_MIN - 0.5, MIDI_MAX + 1.5)
    spl_edges  = np.arange(SPL_MIN  - 0.5, SPL_MAX  + 1.5)

    # Left + middle: per-metric palette. Long file stems
    # ("complete_vrp_results_20260506_204735_VRP") would overflow the
    # subplot title and visually overlap with the next subplot. Truncate
    # to a sensible length and break onto 2 lines if metric name is long.
    def _short(s: str, maxlen: int = 36) -> str:
        return s if len(s) <= maxlen else "…" + s[-(maxlen - 1):]
    for ax, grid, label in ((axes[0], ga, label_a), (axes[1], gb, label_b)):
        ax.set_facecolor(_BG_AX)
        ax.set_title(f"{_short(label)}\n{cfg['label']}",
                     color=_FG_TEXT, fontsize=9, pad=4)
        if grid.count() == 0:
            ax.text(0.5, 0.5, "no data", ha="center", va="center",
                    color="#888", transform=ax.transAxes)
            ax.set_xticks([]); ax.set_yticks([])
            continue
        vmin = cfg["vmin"] if cfg["vmin"] is not None else float(np.nanmin(grid))
        vmax = cfg["vmax"] if cfg["vmax"] is not None else float(np.nanmax(grid))
        raw_cmap = cfg["cmap"]
        cmap_obj = plt.get_cmap(raw_cmap).copy() if isinstance(raw_cmap, str) else raw_cmap
        cmap_obj.set_bad(color=_BG_EMPTY)
        norm = cfg.get("norm") or Normalize(vmin=vmin, vmax=vmax)
        mesh = ax.pcolormesh(midi_edges, spl_edges, grid,
                              cmap=cmap_obj, norm=norm, shading="flat")
        cb = fig.colorbar(mesh, ax=ax, fraction=0.03, pad=0.01)
        cb.ax.yaxis.set_tick_params(color=_FG_TEXT)
        plt.setp(cb.ax.yaxis.get_ticklabels(), color=_FG_TEXT, fontsize=6)
        cb.outline.set_edgecolor(_FG_SPINE)
        ax.tick_params(colors=_FG_TEXT, labelsize=6)
        ax.set_xlabel("MIDI", color=_FG_TEXT, fontsize=7)
        ax.set_ylabel("SPL (dB)", color=_FG_TEXT, fontsize=7)
        for sp in ax.spines.values():
            sp.set_edgecolor(_FG_SPINE)
        ax.grid(which="major", color=_GRID, linewidth=0.3, linestyle="--")

    # Right: A − B, diverging palette symmetric around 0
    diff = ga.filled(np.nan) - gb.filled(np.nan)
    diff_ma = np.ma.masked_invalid(diff)
    axd = axes[2]
    axd.set_facecolor(_BG_AX)
    axd.set_title(f"Δ = A − B  ({_short(label_a, 22)} − {_short(label_b, 22)})",
                   color=_FG_TEXT, fontsize=8, pad=4)
    if diff_ma.count() == 0:
        axd.text(0.5, 0.5, "no overlap", ha="center", va="center",
                 color="#888", transform=axd.transAxes)
        axd.set_xticks([]); axd.set_yticks([])
    else:
        absmax = float(np.nanmax(np.abs(diff_ma)))
        if absmax == 0:
            absmax = 1.0
        diff_cmap = plt.get_cmap("RdBu_r").copy()
        diff_cmap.set_bad(color=_BG_EMPTY)
        mesh = axd.pcolormesh(midi_edges, spl_edges, diff_ma,
                               cmap=diff_cmap,
                               vmin=-absmax, vmax=absmax, shading="flat")
        cb = fig.colorbar(mesh, ax=axd, fraction=0.03, pad=0.01)
        cb.ax.yaxis.set_tick_params(color=_FG_TEXT)
        plt.setp(cb.ax.yaxis.get_ticklabels(), color=_FG_TEXT, fontsize=6)
        cb.outline.set_edgecolor(_FG_SPINE)
        axd.tick_params(colors=_FG_TEXT, labelsize=6)
        axd.set_xlabel("MIDI", color=_FG_TEXT, fontsize=7)
        for sp in axd.spines.values():
            sp.set_edgecolor(_FG_SPINE)

    # tight_layout auto-fits axes + labels into the figure rect
    # regardless of how matplotlib's auto-resize stretches the figure
    # to match the canvas widget. pad=0.8 leaves ~6 px breathing room
    # around all axes and keeps the MIDI axis label fully visible even
    # when the canvas height is on the small side.
    try:
        fig.tight_layout(pad=0.8)
    except Exception:
        # tight_layout can throw on degenerate figures (e.g. all axes
        # empty). Fall back to manual margins.
        fig.subplots_adjust(left=0.05, right=0.97, top=0.90,
                             bottom=0.18, wspace=0.30)
    return True


def save_vrp_comparison(csv_a: str, csv_b: str, col: str,
                          out_png: str) -> str:
    """CLI helper: read both CSVs, draw comparison, save PNG."""
    df_a = pd.read_csv(csv_a, sep=";")
    df_b = pd.read_csv(csv_b, sep=";")
    fig, _ = plt.subplots(figsize=(15, 5), dpi=130)
    ok = draw_vrp_comparison(df_a, df_b, col, fig,
                               label_a=os.path.basename(csv_a),
                               label_b=os.path.basename(csv_b))
    if not ok:
        plt.close(fig)
        raise ValueError(f"Metric {col!r} not comparable on these two files")
    fig.savefig(out_png, dpi=130, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_png
