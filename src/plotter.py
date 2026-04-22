#!/usr/bin/env python3
"""
VoiceMap VRP Plotter
Saves a PNG map for every non-empty metric column in the grouped VRP CSV.
Colour scales reproduce the exact HSV/RGB formulas from FonaDyn's Metric*.sc files.
"""

import os
import colorsys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")           # headless – no display needed
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.colors import Normalize, LogNorm, LinearSegmentedColormap
from typing import Optional

matplotlib.rcParams["font.family"] = ["Microsoft YaHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

# ---------------------------------------------------------------------------
# VRP grid constants  (must match VRPDataVRP.sc)
# ---------------------------------------------------------------------------
MIDI_MIN, MIDI_MAX = 30, 96
SPL_MIN,  SPL_MAX  = 40, 120

# ---------------------------------------------------------------------------
# Custom colourmaps that exactly reproduce the SC Color.hsv() palette funcs
# ---------------------------------------------------------------------------

def _hsv_sweep(h_start: float, h_end: float, name: str, n: int = 256):
    """Full-saturation, full-brightness linear hue sweep h_start→h_end."""
    cols = [colorsys.hsv_to_rgb(h_start + (h_end - h_start) * i / (n - 1), 1.0, 1.0)
            for i in range(n)]
    return LinearSegmentedColormap.from_list(name, cols, N=n)


def _clarity_cmap(n: int = 256):
    # SC: Color.green(v.linlin(0.96, 1.0, 0.5, 1.0))
    # = RGB(0, brightness, 0) with brightness 0.5→1.0
    cols = [(0.0, 0.5 + 0.5 * i / (n - 1), 0.0) for i in range(n)]
    return LinearSegmentedColormap.from_list("fd_clarity", cols, N=n)


def _entropy_cmap(n: int = 256):
    # SC: colorZeroEntropy = Color.hsv(0.33, 0.1, 1)   (very pale green)
    # For v > 0.1: Color.white.blend(Color.new255(165,42,42), sat)
    #   sat = v.linlin(0, 10, 0.1, 0.95)
    # Approximated as a continuous sweep from pale-green to brown.
    pale = colorsys.hsv_to_rgb(0.33, 0.1, 1.0)     # ≈ (0.90, 1.00, 0.90)
    brown = (165 / 255, 42 / 255, 42 / 255)
    cols = []
    for i in range(n):
        sat = 0.1 + 0.85 * i / (n - 1)             # linlin(0,1, 0.1, 0.95)
        r = (1 - sat) * pale[0] + sat * brown[0]
        g = (1 - sat) * pale[1] + sat * brown[1]
        b = (1 - sat) * pale[2] + sat * brown[2]
        cols.append((r, g, b))
    return LinearSegmentedColormap.from_list("fd_entropy", cols, N=n)


def _density_cmap(n: int = 256):
    # SC: cSat = v.explin(1, 10000, 0.95, 0.25); Color.grey(cSat, 1)
    # explin with LogNorm handles the exp axis externally;
    # the cmap itself covers brightness 0.95 (low) → 0.25 (high).
    cols = [(0.95 - 0.70 * i / (n - 1),) * 3 for i in range(n)]
    return LinearSegmentedColormap.from_list("fd_density", cols, N=n)


# Build all custom colormaps once at import time
_CMAP = {
    # Metric*.sc palette function → colormap
    # CPP:      cHue = v.linlin(0, 30, 2/3, 0) → blue→red
    "CPP":      _hsv_sweep(2 / 3, 0.0,  "fd_cpp"),
    # SpecBal:  cHue = v.linlin(-42, 0, 1/3, 0) → green→red
    "SpecBal":  _hsv_sweep(1 / 3, 0.0,  "fd_specbal"),
    # Crest:    cHue = v.linlin(1.414, 4, 1/3, 0) → green→red
    "Crest":    _hsv_sweep(1 / 3, 0.0,  "fd_crest"),
    # dEGGmax:  cHue = v.explin(1, 20, 1/3, 0) → green→red (log axis)
    "dEGGmax":  _hsv_sweep(1 / 3, 0.0,  "fd_degg"),
    # Icontact: cHue = v.linlin(0, 0.7, 0.67, 0) → blue→red
    "Icontact": _hsv_sweep(0.67,  0.0,  "fd_ic"),
    # Qcontact: cHue = v.linlin(0.1, 0.6, 0.83, 0) → purple→red
    "Qcontact": _hsv_sweep(0.83,  0.0,  "fd_qci"),
    # HRFegg:   cHue = v.linlin(-30, 10, 5/6, 0) → magenta→red
    "HRFegg":   _hsv_sweep(5 / 6, 0.0,  "fd_hrf"),
    "Clarity":  _clarity_cmap(),
    "Entropy":  _entropy_cmap(),
    "Total":    _density_cmap(),
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
        cmap=_hsv_sweep(1/3, 0.0, "fd_jitter"),
        norm=None,
    ),
    "JitterRAP": dict(
        label="Jitter RAP (3-pt)",
        vmin=0.0, vmax=3.0, unit="%",
        cmap=_hsv_sweep(1/3, 0.0, "fd_jitter_rap"),
        norm=None,
    ),
    "JitterPPQ5": dict(
        label="Jitter PPQ5 (5-pt)",
        vmin=0.0, vmax=3.0, unit="%",
        cmap=_hsv_sweep(1/3, 0.0, "fd_jitter_ppq5"),
        norm=None,
    ),
    # Shimmer family: pathological threshold ~3.8% for local shimmer.
    "Shimmer": dict(
        label="Shimmer (local)",
        vmin=0.0, vmax=10.0, unit="%",
        cmap=_hsv_sweep(1/3, 0.0, "fd_shimmer"),
        norm=None,
    ),
    "ShimmerDB": dict(
        label="Shimmer",
        vmin=0.0, vmax=1.0, unit="dB",
        cmap=_hsv_sweep(1/3, 0.0, "fd_shimmer_db"),
        norm=None,
    ),
    "ShimmerAPQ11": dict(
        label="Shimmer APQ11 (11-pt)",
        vmin=0.0, vmax=10.0, unit="%",
        cmap=_hsv_sweep(1/3, 0.0, "fd_shimmer_apq11"),
        norm=None,
    ),
    # HNR: higher = healthier voice (>20 dB normal). Use blue→red reversed
    # so high values (good) are cool/calm and low values (noisy) are hot.
    "HNR": dict(
        label="HNR",
        vmin=0.0, vmax=35.0, unit="dB",
        cmap=_hsv_sweep(0.0, 2/3, "fd_hnr"),   # red→blue (low→high)
        norm=None,
    ),
    # ── P2 Singing-specific ────────────────────────────────────────────────
    # Vibrato rate: typical singer 5-7 Hz; Peking opera often 5-6 Hz.
    # vmin/vmax span the realistic vibrato band; mid-green = healthy.
    "VibratoRate": dict(
        label="Vibrato rate",
        vmin=3.0, vmax=9.0, unit="Hz",
        cmap=_hsv_sweep(2/3, 0.0, "fd_vib_rate"),   # blue→red across band
        norm=None,
    ),
    # Vibrato extent: 50-150 cents typical; classical Western ~80, Peking often wider.
    "VibratoExtent": dict(
        label="Vibrato extent",
        vmin=0.0, vmax=300.0, unit="cents",
        cmap=_hsv_sweep(1/3, 0.0, "fd_vib_ext"),    # green→red (wide = dramatic)
        norm=None,
    ),
    # Formants: vocal-tract resonances. Typical ranges for a mixed voice:
    #   F1 ~ 300-1000 Hz   (vowel height)
    #   F2 ~ 900-2500 Hz   (vowel backness)
    #   F3 ~ 2200-3500 Hz  (articulation, part of singer's formant cluster)
    "F1": dict(
        label="F1 — 1st formant",
        vmin=200.0, vmax=1000.0, unit="Hz",
        cmap=_hsv_sweep(2/3, 0.0, "fd_f1"),
        norm=None,
    ),
    "F2": dict(
        label="F2 — 2nd formant",
        vmin=800.0, vmax=2800.0, unit="Hz",
        cmap=_hsv_sweep(2/3, 0.0, "fd_f2"),
        norm=None,
    ),
    "F3": dict(
        label="F3 — 3rd formant",
        vmin=2000.0, vmax=3600.0, unit="Hz",
        cmap=_hsv_sweep(2/3, 0.0, "fd_f3"),
        norm=None,
    ),
    # Singer's Formant Energy (2.8-3.4 kHz band / total, dB).
    # Classical trained singer: -7 to -13 dB; untrained < -13 dB; "ring" is high.
    "SingersFormant": dict(
        label="Singer's Formant Energy",
        vmin=-25.0, vmax=-5.0, unit="dB",
        cmap=_hsv_sweep(2/3, 0.0, "fd_sfe"),   # blue→red (low→high = more ring)
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
        cmap=plt.get_cmap("tab10", 5),
        norm=None,
    ),
    "maxCPhon": dict(
        label="Dominant phonation cluster",
        vmin=0.5, vmax=5.5, unit="",
        cmap=plt.get_cmap("Set2", 5),
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

# Now that clustering is implemented, these columns can have real values.
# Keep the set around so any future legacy "always-zero" metrics can be
# listed here without code changes elsewhere.
_SKIP_ZERO_METRICS: set = set()

# Metrics excluded from the combined overview figure (too many sub-metrics,
# clutters the grid). Cluster breakdowns are still rendered individually.
_SKIP_COMBINED = {
    "Icontact", "HRFegg",
    "Cluster 1", "Cluster 2", "Cluster 3", "Cluster 4", "Cluster 5",
    "cPhon 1",   "cPhon 2",   "cPhon 3",   "cPhon 4",   "cPhon 5",
}


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

    ax.set_facecolor("#333333")

    midi_edges = np.arange(MIDI_MIN - 0.5, MIDI_MAX + 1.5)
    spl_edges  = np.arange(SPL_MIN  - 0.5, SPL_MAX  + 1.5)

    # Custom colormaps are already new objects; built-in names need a copy
    raw_cmap = cfg["cmap"]
    if isinstance(raw_cmap, str):
        cmap_obj = plt.get_cmap(raw_cmap).copy()
    else:
        cmap_obj = raw_cmap
    cmap_obj.set_bad(color="#333333")

    norm = cfg.get("norm") or Normalize(vmin=vmin, vmax=vmax)

    mesh = ax.pcolormesh(
        midi_edges, spl_edges, grid,
        cmap=cmap_obj, norm=norm,
        shading="flat",
        rasterized=True,
    )

    unit_str = f" [{cfg['unit']}]" if cfg["unit"] else ""
    cbar = fig.colorbar(mesh, ax=ax, fraction=0.03, pad=0.01)
    # 不再在颜色条旁重复单位——标题里 "CPP [dB]" 已经写过了，
    # 重复标注会让不同 metric 的颜色条宽度变化（有的有 "dB" / "slope" / ""），
    # 进而让整张图的尺寸参差不齐。
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white", fontsize=7)

    # X axis: major ticks every 6 semitones labelled as MIDI numbers
    major_ticks = list(range(30, MIDI_MAX + 1, 6))
    ax.set_xticks(major_ticks)
    ax.set_xticklabels([str(m) for m in major_ticks], color="white", fontsize=7)
    ax.xaxis.set_minor_locator(mticker.MultipleLocator(1))
    ax.set_xlim(MIDI_MIN - 0.5, MIDI_MAX + 0.5)
    ax.set_xlabel("MIDI", color="white", fontsize=7)

    # Y axis: SPL in dB
    ax.set_yticks(range(SPL_MIN, SPL_MAX + 1, 10))
    ax.set_yticklabels(
        [str(v) for v in range(SPL_MIN, SPL_MAX + 1, 10)],
        color="white", fontsize=7,
    )
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(5))
    ax.set_ylim(SPL_MIN - 0.5, SPL_MAX + 0.5)
    ax.set_ylabel("SPL (dB)", color="white", fontsize=7)

    ax.tick_params(axis="both", which="both", colors="white", labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor("#666666")
    ax.grid(which="major", color="#555555", linewidth=0.4, linestyle="--")
    ax.grid(which="minor", color="#3a3a3a", linewidth=0.2)

    ax.set_title(f"{cfg['label']}{unit_str}", color="white", fontsize=9, pad=4)
    return True


def _plot_one(df: pd.DataFrame, col: str, out_path: str, basename: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("#1a1a1a")
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
    fig.patch.set_facecolor("#1a1a1a")

    for idx, col in enumerate(metrics):
        _draw_vrp_ax(axes[idx // ncols][idx % ncols], fig, df, col)

    for idx in range(len(metrics), nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    fig.suptitle(basename, color="white", fontsize=13, y=1.01)
    fig.tight_layout()

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{basename}_combined.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def _active_metrics(df: pd.DataFrame, requested: Optional[list]) -> list:
    if requested is not None:
        return requested
    candidates = [c for c in df.columns if c not in {"MIDI", "dB"} and c not in _SKIP_ZERO_METRICS]
    return [c for c in candidates if df[c].sum() != 0]


def plot_vrp_csv(
    csv_path: str,
    out_dir: Optional[str] = None,
    metrics: Optional[list] = None,
) -> list:
    """Load a semicolon-delimited _VRP.csv and save one PNG per non-empty metric."""
    df = pd.read_csv(csv_path, sep=";")
    if out_dir is None:
        out_dir = os.path.dirname(csv_path)
    os.makedirs(out_dir, exist_ok=True)
    basename = os.path.splitext(os.path.basename(csv_path))[0]

    saved = []
    for col in _active_metrics(df, metrics):
        if col not in df.columns:
            continue
        _plot_one(df, col, out_dir, basename)
        fpath = os.path.join(out_dir, f"{basename}_{col}.png")
        if os.path.exists(fpath):
            saved.append(fpath)
    return saved


draw_vrp_on_ax = _draw_vrp_ax


def plot_vrp_dataframe(
    df: pd.DataFrame,
    basename: str,
    out_dir: str,
    metrics: Optional[list] = None,
) -> list:
    """Plot directly from the grouped DataFrame returned by the analyser."""
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
