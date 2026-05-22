# -*- coding: utf-8 -*-
"""F0 profile — 1-D projection of the voice map.

Collapses the SPL axis so every metric becomes a single trend curve
indexed by fundamental frequency (MIDI semitone).

Reads the per-cycle log (one row per analysed cycle, continuous F0 and
SPL). Each F0 is estimated by an SPL-balanced weighted kernel
regression: cycles are reweighted so every F0's SPL distribution
matches the recording-wide one, so a pitch that happened to be sung
quietly is not mistaken for a low metric value. The result is the
genuine F0-dependence of each metric, free of how loud each pitch was
sung.

Why a 1-D view: the 2-D heatmap needs a meaningful SPL axis. When the
dynamic range is narrow or the recording is uncalibrated, F0 is the
only axis worth reading; projecting onto it also pools every pass over
a pitch into one estimate.
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


def _spl_balance_weights(midi, dB, f0_bin=2.0, spl_bin=5.0):
    """Per-cycle weights that rebalance each F0 region's SPL
    distribution to the recording-wide one.

    A pitch sung mostly quietly (or loudly) otherwise drags an
    SPL-dependent metric down (or up) — an artefact of how the take was
    sung, not a real F0 effect. Post-stratifying on SPL removes it:
    within each F0 band, cycles are reweighted so their SPL mix matches
    the global SPL mix, so every F0 is read 'at the same loudness'."""
    midi = np.asarray(midi, dtype=float)
    dB = np.asarray(dB, dtype=float)
    w = np.ones(len(midi))
    ok = np.isfinite(midi) & np.isfinite(dB)
    if ok.sum() < 20:
        return w
    si = np.floor((dB - np.min(dB[ok])) / spl_bin).astype(int)
    fi = np.floor((midi - np.min(midi[ok])) / f0_bin).astype(int)
    n_spl = int(si[ok].max()) + 1
    g = np.bincount(si[ok], minlength=n_spl).astype(float)
    g /= g.sum()                                   # global SPL profile
    for f in np.unique(fi[ok]):
        sel = ok & (fi == f)
        cnt = np.bincount(si[sel], minlength=n_spl).astype(float)
        ftot = cnt.sum()
        for s in range(n_spl):
            if cnt[s] > 0:
                w[sel & (si == s)] = g[s] * ftot / cnt[s]
    w = np.clip(w, 0.1, 10.0)
    w[ok] /= np.mean(w[ok])
    return w


def _weighted_kernel_trend(x, y, w, xs, bw=1.2):
    """Weighted Gaussian-kernel regression of y on x, evaluated at xs.
    Returns (mean, std) per xs — std is the weighted local spread for
    the ±1 SD band. Uneven F0 sampling is handled naturally: a sparse
    pitch is dominated by its neighbours rather than swinging to its
    own few (possibly biased) cycles."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    w = np.asarray(w, dtype=float)
    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(w)
    x, y, w = x[m], y[m], w[m]
    mean = np.full(len(xs), np.nan)
    std = np.full(len(xs), np.nan)
    if len(x) < 5:
        return mean, std
    for i, xe in enumerate(xs):
        k = np.exp(-0.5 * ((x - xe) / bw) ** 2) * w
        ks = k.sum()
        if ks <= 1e-9:
            continue
        mu = float((k * y).sum() / ks)
        mean[i] = mu
        std[i] = float(np.sqrt(max((k * (y - mu) ** 2).sum() / ks, 0.0)))
    return mean, std


def draw_f0_scatter(fig, cycle_df, metric_keys, show_trend=True,
                    show_scatter=False, show_band=True):
    """Render the per-cycle F0 trend chart onto `fig` (cleared first).

    Reads the per-cycle log (one row per cycle, continuous MIDI). Each
    metric becomes one SPL-balanced kernel-regression trend line over
    every cycle's (F0, normalised metric) — the genuine F0-dependence,
    corrected for how loud each pitch happened to be sung. With
    `show_band` a ±1 SD ribbon (local spread of the per-cycle values)
    is drawn too. `show_scatter` optionally overlays the raw per-cycle
    dots; the 1-D view keeps it off (the point cloud belongs to the
    2-D map)."""
    fig.clear()

    if cycle_df is None or "MIDI" not in getattr(cycle_df, "columns", []):
        _placeholder(fig, "No per-cycle data - run an analysis first")
        return
    if not metric_keys:
        _placeholder(fig, "No metric selected - tick a metric on the left")
        return

    midi = cycle_df["MIDI"].to_numpy(dtype=float)
    dB = (cycle_df["dB"].to_numpy(dtype=float)
          if "dB" in cycle_df.columns else np.full(len(midi), np.nan))
    # SPL-balancing weights (depend only on F0+SPL, shared by every
    # metric) + the dense F0 grid the kernel trend is evaluated on.
    w_spl = _spl_balance_weights(midi, dB)
    fin = np.isfinite(midi)
    tx = (np.arange(np.floor(midi[fin].min()),
                    np.ceil(midi[fin].max()) + 0.25, 0.25)
          if fin.any() else np.array([]))

    gs = fig.add_gridspec(2, 1, height_ratios=[1, 7], hspace=0.10)
    ax_cov = fig.add_subplot(gs[0])
    ax = fig.add_subplot(gs[1], sharex=ax_cov)

    # Coverage strip — cycle count per semitone-wide F0 bin.
    ax_cov.hist(midi, bins=np.arange(MIDI_MIN, MIDI_MAX + 2),
                color="#888888", alpha=0.55)
    ax_cov.set_ylabel("Cycles\nper F0", fontsize=7)
    ax_cov.tick_params(labelbottom=False, labelsize=7)
    ax_cov.set_facecolor("white")

    drawn = 0
    for idx, key in enumerate(metric_keys):
        if key not in cycle_df.columns:
            continue
        rng = _norm_range(key)
        if rng is None:
            continue
        lo, hi = rng
        color = _LINE_PALETTE[idx % len(_LINE_PALETTE)]
        vals = _normalise(cycle_df[key].to_numpy(dtype=float), lo, hi)
        if show_scatter:
            ax.scatter(midi, vals, s=5, color=color, alpha=0.10,
                       edgecolors="none", rasterized=True, zorder=2)
        if not show_trend or len(tx) < 2:
            ax.plot([], [], color=color, lw=2.4, label=key)
            drawn += 1
            continue
        # SPL-balanced kernel trend: each F0 estimated as if sung at the
        # global SPL mix, so a quietly-sung pitch is not read as low.
        ty, tsd = _weighted_kernel_trend(midi, vals, w_spl, tx)
        if show_band:
            ax.fill_between(tx, np.clip(ty - tsd, 0.0, 1.0),
                            np.clip(ty + tsd, 0.0, 1.0),
                            color=color, alpha=0.15, linewidth=0, zorder=3)
        ax.plot(tx, ty, color=color, lw=2.4, zorder=5, label=key)
        drawn += 1

    ax.set_ylim(-0.02, 1.02)
    ax.set_xlim(MIDI_MIN - 0.5, MIDI_MAX + 0.5)
    ax.set_xticks(list(range(30, MIDI_MAX + 1, 6)))
    ax.xaxis.set_minor_locator(MultipleLocator(1))
    ax.set_xlabel("Fundamental frequency F0 (MIDI semitone)")
    ax.set_ylabel("Normalised metric value (0-1)")
    ax.grid(True, color="#dddddd", linewidth=0.6)
    ax.set_facecolor("white")
    if drawn:
        ax.legend(loc="upper right", fontsize=8, ncol=2, framealpha=0.9)

    fig.subplots_adjust(left=0.09, right=0.97, top=0.96, bottom=0.10)


def _placeholder(fig, message):
    ax = fig.add_subplot(111)
    ax.text(0.5, 0.5, message, ha="center", va="center",
            fontsize=11, color="#888888")
    ax.axis("off")
