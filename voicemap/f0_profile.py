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
import matplotlib.colors as mcolors
from matplotlib.ticker import MultipleLocator
from matplotlib.collections import LineCollection, PolyCollection

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


def draw_f0_profile(fig, df, metric_keys, show_band=False, show_scatter=True):
    """Render the F0-profile chart onto `fig` (cleared first).

    Each metric becomes one 0-1 normalised polyline indexed by MIDI —
    the Total-weighted mean over that pitch's SPL cells. With
    `show_scatter`, every individual (MIDI, SPL) cell is also drawn as a
    faint dot (size ∝ cycle count), so the SPL spread that the mean
    collapses stays visible — the mean is the trunk, the dots are the
    detail. With `show_band`, a ±1 SD ribbon is drawn too. A thin
    coverage strip on top shows ΣTotal per F0."""
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

    # Per-cell scatter setup — dot size ∝ cycle count, so the SPL cells
    # that dominate the weighted mean read as bigger dots. A small x
    # jitter spreads the otherwise-coincident dots at each integer MIDI.
    jit_rng = np.random.default_rng(0)
    tot = df["Total"].to_numpy(dtype=float) if "Total" in df.columns else None
    tot_max = float(tot.max()) if tot is not None and tot.size else 1.0

    drawn = 0
    for idx, key in enumerate(metric_keys):
        st = agg["stats"].get(key)
        rng = _norm_range(key)
        if st is None or rng is None:
            continue
        lo, hi = rng
        color = _LINE_PALETTE[idx % len(_LINE_PALETTE)]

        # Raw per-cell values — the SPL detail behind the weighted mean.
        if show_scatter and key in df.columns:
            cx = df["MIDI"].to_numpy(dtype=float)
            cy = _normalise(df[key].to_numpy(dtype=float), lo, hi)
            jit = (jit_rng.random(len(cx)) - 0.5) * 0.4
            if tot is not None:
                sz = 3.0 + 22.0 * np.sqrt(np.clip(tot / tot_max, 0.0, 1.0))
            else:
                sz = 8.0
            ax.scatter(cx + jit, cy, s=sz, color=color, alpha=0.22,
                       edgecolors="none", zorder=1)

        if show_band:
            ax.fill_between(midi,
                            _normalise(st["mean"] - st["std"], lo, hi),
                            _normalise(st["mean"] + st["std"], lo, hi),
                            color=color, alpha=0.15, linewidth=0, zorder=2)
        ax.plot(midi, _normalise(st["mean"], lo, hi),
                color=color, lw=2.0, label=key, zorder=4)
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


def _trend(x, y, frac=0.25):
    """Smooth trend of y over x. LOWESS when statsmodels is installed
    (the project's optional dep), else a cubic-polynomial fallback —
    the same degradation path plot_overlay.py uses. Returns (xs, ys)
    sorted by x, or None when there are too few points."""
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 12:
        return None
    order = np.argsort(x)
    x, y = x[order], y[order]
    try:
        from statsmodels.nonparametric.smoothers_lowess import lowess
        sm = lowess(y, x, frac=frac, return_sorted=True)
        # Per-cycle input repeats x heavily (F0 is window-resolution) —
        # collapse to one smoothed value per distinct F0.
        ux, ui = np.unique(sm[:, 0], return_index=True)
        return ux, sm[ui, 1]
    except Exception:
        coef = np.polyfit(x, y, 3)
        xs = np.linspace(x.min(), x.max(), 240)
        return xs, np.clip(np.polyval(coef, xs), 0.0, 1.0)


def _smooth1d(a, win):
    """Moving-average smooth — keeps the opacity gradient gradual
    instead of combed by the jagged per-F0 cycle counts."""
    a = np.asarray(a, dtype=float)
    if win < 2 or len(a) < win:
        return a
    return np.convolve(a, np.ones(win) / win, mode="same")


def _smooth_nan(a, win):
    """Moving-average smooth that tolerates NaN gaps — averages only
    over finite samples and keeps originally-NaN points NaN. Used to
    de-comb the ±1 SD band edge."""
    a = np.asarray(a, dtype=float)
    valid = np.isfinite(a)
    if win < 2 or valid.sum() < 2:
        return a
    k = np.ones(win)
    num = np.convolve(np.where(valid, a, 0.0), k, mode="same")
    den = np.convolve(valid.astype(float), k, mode="same")
    out = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
    out[~valid] = np.nan
    return out


def _coverage_weight(midi_all, tx, half=1.0):
    """Per-tx weight in [0, 1] from local cycle density — how many
    cycles sit within ±half semitone of each trend point. Smoothed and
    normalised by the 75th-percentile density so the well-populated F0
    range reads at full strength and only genuinely sparse pitches fade
    out, with a gradual (not combed) gradient between."""
    m = np.sort(np.asarray(midi_all, dtype=float))
    m = m[np.isfinite(m)]
    tx = np.asarray(tx, dtype=float)
    if len(m) == 0:
        return np.zeros(len(tx))
    cnt = (np.searchsorted(m, tx + half, side="right")
           - np.searchsorted(m, tx - half, side="left")).astype(float)
    cnt = _smooth1d(cnt, 9)
    pos = cnt[cnt > 0]
    ref = float(np.percentile(pos, 75)) if len(pos) else 1.0
    return np.clip(cnt / max(ref, 1.0), 0.0, 1.0)


def _local_std(x, y, tx, half=0.6):
    """Std of y over the points whose x lies within ±half of each tx.
    NaN where fewer than 3 samples fall in the window. Used for the
    ±1 SD ribbon — the local spread of per-cycle values around the
    trend."""
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    out = np.full(len(tx), np.nan)
    if len(x) < 3:
        return out
    order = np.argsort(x)
    xs, ys = x[order], y[order]
    lo_idx = np.searchsorted(xs, np.asarray(tx) - half, side="left")
    hi_idx = np.searchsorted(xs, np.asarray(tx) + half, side="right")
    for i in range(len(tx)):
        if hi_idx[i] - lo_idx[i] >= 3:
            out[i] = float(np.std(ys[lo_idx[i]:hi_idx[i]]))
    return out


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

    Reads the per-cycle log (one row per cycle, continuous MIDI) rather
    than the binned VRP. Each metric becomes one LOWESS trend line over
    every cycle's (F0, normalised metric) — a smooth curve at full F0
    resolution, not the coarse semitone-binned mean. With `show_band` a
    ±1 SD ribbon (local spread of the per-cycle values around the
    trend) is drawn too. `show_scatter` optionally overlays the raw
    per-cycle dots; the 1-D view keeps it off (the point cloud belongs
    to the 2-D map)."""
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
