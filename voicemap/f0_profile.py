# -*- coding: utf-8 -*-
"""F0 profile — 1-D projection of the 2-D voice map.

Collapses the SPL axis of a grouped VRP DataFrame so every metric
becomes a single curve indexed by fundamental frequency (MIDI
semitone). Each F0 column is aggregated as a Total-weighted mean with
a Total-weighted standard-deviation band.

Why this exists: the 2-D heatmap needs a meaningful SPL axis. When the
dynamic range is narrow or the recording is uncalibrated, SPL carries
little information and F0 becomes the only axis worth reading.
Projecting onto F0 also pools every pass over a given pitch into one
statistical estimate — cleaner and more reproducible than following a
parameter along the time axis.

Reuses the grouped VRP DataFrame as-is (same one the heatmap draws
from); no re-analysis is needed.
"""

from __future__ import annotations

import numpy as np
from matplotlib.ticker import MultipleLocator

from voicemap.metrics_registry import get as get_spec
# Single source of truth for the MIDI axis bounds — shared with the
# 2-D heatmap so both plots use an identical, fixed F0 axis.
from voicemap.plotter import MIDI_MIN, MIDI_MAX


# Line palette — Okabe-Ito colourblind-safe set, matching the project's
# stated colour-vision-deficiency policy (see metrics_registry.py).
_LINE_PALETTE = [
    "#0072B2", "#E69F00", "#009E73", "#CC79A7",
    "#F0E442", "#56B4E9", "#D55E00", "#000000",
]


def _weighted_stats(values: np.ndarray, weights: np.ndarray):
    """Return (mean, std) weighted by `weights`, ignoring NaN samples."""
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not mask.any():
        return np.nan, np.nan
    v = values[mask]
    w = weights[mask].astype(float)
    wsum = w.sum()
    mean = float((w * v).sum() / wsum)
    var = float((w * (v - mean) ** 2).sum() / wsum)
    return mean, float(np.sqrt(max(var, 0.0)))


def aggregate_by_f0(df, metric_keys, midi_min=MIDI_MIN, midi_max=MIDI_MAX):
    """Project the grouped VRP `df` onto the fixed F0 axis.

    The MIDI axis is fixed to the 2-D voice-map range
    (MIDI_MIN..MIDI_MAX) so the F0 axis lines up with the heatmap and
    stays identical across recordings — curves from different takes can
    then be overlaid directly. Pitches with no data stay NaN so
    polylines break there instead of bridging an unsung range.

    Returns a dict:
      midi      — contiguous MIDI semitone values (np.ndarray)
      coverage  — ΣTotal per MIDI, the data-density / confidence signal
      stats     — {key: {"mean": arr, "std": arr}} aligned with `midi`
    """
    midi = np.arange(midi_min, midi_max + 1)
    n = len(midi)

    coverage = np.zeros(n, dtype=float)
    stats = {k: {"mean": np.full(n, np.nan), "std": np.full(n, np.nan)}
             for k in metric_keys}
    has_total = "Total" in df.columns

    for m_val, grp in df.groupby("MIDI"):
        i = int(round(float(m_val))) - midi_min
        if i < 0 or i >= n:
            continue
        w = (grp["Total"].to_numpy(dtype=float) if has_total
             else np.ones(len(grp)))
        coverage[i] = float(np.nansum(w))
        for k in metric_keys:
            if k not in grp.columns:
                continue
            mean, std = _weighted_stats(grp[k].to_numpy(dtype=float), w)
            stats[k]["mean"][i] = mean
            stats[k]["std"][i] = std

    return {"midi": midi, "coverage": coverage, "stats": stats}


def _norm_range(key):
    """(vmin, vmax) used to map a metric onto the shared 0-1 axis.

    Pulled from the metric registry, which holds each metric's display
    limits — theoretical where one exists, an empirical constant
    otherwise. Returns None when no usable range is registered."""
    spec = get_spec(key)
    if spec is not None and spec.vmin is not None and spec.vmax is not None:
        lo, hi = float(spec.vmin), float(spec.vmax)
        if hi > lo:
            return lo, hi
    return None


def _normalise(arr, lo, hi):
    return np.clip((arr - lo) / (hi - lo), 0.0, 1.0)


def draw_f0_profile(fig, df, metric_keys, show_band=True):
    """Render the F0-profile chart onto `fig` (cleared first).

    Each metric becomes one 0-1 normalised polyline indexed by MIDI;
    with `show_band` a ±1 SD ribbon is drawn around it. A thin coverage
    strip on top shows ΣTotal per F0 so low-data pitches can be read
    with appropriate caution."""
    fig.clear()

    if df is None or "MIDI" not in getattr(df, "columns", []):
        _placeholder(fig, "No data - run an analysis or load a VRP CSV")
        return
    if not metric_keys:
        _placeholder(fig, "No metric selected - tick a metric on the left")
        return

    agg = aggregate_by_f0(df, metric_keys)
    midi = agg["midi"]

    # Two stacked axes share the F0 x-axis: a short coverage strip on
    # top, the normalised metric curves below.
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 7], hspace=0.10)
    ax_cov = fig.add_subplot(gs[0])
    ax = fig.add_subplot(gs[1], sharex=ax_cov)

    ax_cov.fill_between(midi, agg["coverage"], step="mid",
                        color="#888888", alpha=0.55, linewidth=0)
    ax_cov.set_ylabel("Coverage\n(cycles)", fontsize=7)
    ax_cov.tick_params(labelbottom=False, labelsize=7)
    ax_cov.margins(x=0)
    ax_cov.set_facecolor("white")

    drawn = 0
    for idx, key in enumerate(metric_keys):
        st = agg["stats"].get(key)
        rng = _norm_range(key)
        if st is None or rng is None:
            continue
        lo, hi = rng
        color = _LINE_PALETTE[idx % len(_LINE_PALETTE)]
        ax.plot(midi, _normalise(st["mean"], lo, hi),
                color=color, lw=2.0, label=key)
        if show_band:
            ax.fill_between(midi,
                            _normalise(st["mean"] - st["std"], lo, hi),
                            _normalise(st["mean"] + st["std"], lo, hi),
                            color=color, alpha=0.15, linewidth=0)
        drawn += 1

    ax.set_ylim(-0.02, 1.02)
    # X axis fixed to the 2-D voice-map MIDI range (sharex carries it to
    # the coverage strip) so the F0 axis lines up with the heatmap and
    # is identical across recordings.
    ax.set_xlim(MIDI_MIN - 0.5, MIDI_MAX + 0.5)
    ax.set_xticks(list(range(30, MIDI_MAX + 1, 6)))
    ax.xaxis.set_minor_locator(MultipleLocator(1))
    ax.set_xlabel("Fundamental frequency F0 (MIDI semitone)")
    ax.set_ylabel("Normalised metric value (0-1)")
    ax.grid(True, color="#dddddd", linewidth=0.6)
    ax.set_facecolor("white")
    if drawn:
        ax.legend(loc="upper right", fontsize=8, ncol=2, framealpha=0.9)

    # Explicit margins — tight_layout warns on the shared-x gridspec.
    fig.subplots_adjust(left=0.09, right=0.97, top=0.96, bottom=0.10)


def _placeholder(fig, message):
    ax = fig.add_subplot(111)
    ax.text(0.5, 0.5, message, ha="center", va="center",
            fontsize=11, color="#888888")
    ax.axis("off")
