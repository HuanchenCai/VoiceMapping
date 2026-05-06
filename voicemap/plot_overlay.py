#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plot overlay primitives (M2 — drawing enhancements).

Things this module provides, all platform-aware where it matters:

  save_figure(fig, path, fmt=None)
      Multi-format export: PNG / SVG / PDF / JPG / EPS / TIFF.

  copy_figure_to_clipboard(fig)
      Best-effort clipboard image copy. Win32 → CF_DIB; macOS →
      osascript; Linux → xclip / wl-copy. Returns True on success.

  fit_overlay(ax, xs, ys, method=...)
      Draw a regression line on `ax` through (xs, ys). Methods:
      linear / polynomial / spline / lowess. Falls back gracefully
      when the requested method isn't installed.

  add_annotation(ax, x, y, text)
      Marker + text callout at data coords. Returns the artists.

  fit_voice_center(df, ax, method=...)
      Convenience: per-MIDI median SPL → fit_overlay. Visualises where
      the voice is centred across pitches.

  fit_metric_trend(df, col, ax, method=...)
      Convenience: per-MIDI mean of `col` → secondary y-axis curve.

These are all framework-agnostic — they take a matplotlib Axes / Figure
and don't know about Tk. The GUI calls them from its toolbar handlers.
"""

import io
import os
import sys
import subprocess
from typing import List, Optional

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure


# ─── Multi-format save ───────────────────────────────────────────────────────
SAVE_FORMATS = (
    ("PNG image",     "png"),
    ("SVG vector",    "svg"),
    ("PDF document",  "pdf"),
    ("JPEG image",    "jpg"),
    ("EPS vector",    "eps"),
    ("TIFF image",    "tiff"),
)


def save_figure(fig: Figure, path: str,
                fmt: Optional[str] = None,
                dpi: int = 300) -> str:
    """Write fig to `path`. fmt inferred from extension if None.
    Returns the path actually written."""
    if fmt is None:
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        fmt = ext or "png"
    # JPEG can't have an alpha channel; force opaque white background.
    save_kwargs = dict(format=fmt, dpi=dpi, bbox_inches="tight")
    facecolor = fig.get_facecolor()
    if fmt in ("jpg", "jpeg"):
        save_kwargs["facecolor"] = "white"
    else:
        save_kwargs["facecolor"] = facecolor
    fig.savefig(path, **save_kwargs)
    return path


# ─── Clipboard image copy (cross-platform) ───────────────────────────────────
def copy_figure_to_clipboard(fig: Figure, dpi: int = 200) -> bool:
    """Copy a matplotlib figure as an image to the system clipboard.
    Returns True on success, False otherwise (logs reason in caller)."""
    if sys.platform.startswith("win"):
        return _copy_win(fig, dpi)
    if sys.platform == "darwin":
        return _copy_macos(fig, dpi)
    return _copy_linux(fig, dpi)


def _copy_win(fig: Figure, dpi: int) -> bool:
    try:
        import win32clipboard          # type: ignore
        from PIL import Image
    except ImportError:
        return False
    try:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        buf.seek(0)
        im = Image.open(buf).convert("RGB")
        out = io.BytesIO()
        im.save(out, format="BMP")
        # Strip 14-byte BMP file header → CF_DIB expects a DIB only
        data = out.getvalue()[14:]
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        finally:
            win32clipboard.CloseClipboard()
        return True
    except Exception:
        return False


def _copy_macos(fig: Figure, dpi: int) -> bool:
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            fig.savefig(tf.name, format="png", dpi=dpi, bbox_inches="tight",
                        facecolor=fig.get_facecolor())
            tmp = tf.name
        subprocess.run(
            ["osascript", "-e",
             f'set the clipboard to (read (POSIX file "{tmp}") as «class PNGf»)'],
            check=True)
        os.unlink(tmp)
        return True
    except Exception:
        return False


def _copy_linux(fig: Figure, dpi: int) -> bool:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    png = buf.read()
    # Try wl-copy (Wayland) first, then xclip (X11)
    for cmd in (
        ["wl-copy", "--type", "image/png"],
        ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"],
    ):
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
            p.communicate(png, timeout=5)
            if p.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False


# ─── Fit overlays ────────────────────────────────────────────────────────────
FIT_METHODS = ("linear", "polynomial", "spline", "lowess")


def fit_overlay(ax: Axes, xs, ys,
                method: str = "linear",
                degree: int = 3,
                color: str = "#ff3e88",
                label: Optional[str] = None) -> list:
    """Plot a fit through (xs, ys) on `ax`. Returns list of artists added."""
    artists: list = []
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    x, y = x[finite], y[finite]
    if len(x) < 2:
        return artists
    order = np.argsort(x)
    xs_, ys_ = x[order], y[order]

    if method == "linear":
        coef = np.polyfit(xs_, ys_, 1)
        xx = np.linspace(xs_.min(), xs_.max(), 200)
        yy = np.polyval(coef, xx)
        method_label = f"linear (slope={coef[0]:.3g})"
    elif method == "polynomial":
        deg = max(2, int(degree))
        coef = np.polyfit(xs_, ys_, deg)
        xx = np.linspace(xs_.min(), xs_.max(), 200)
        yy = np.polyval(coef, xx)
        method_label = f"poly deg={deg}"
    elif method == "spline":
        try:
            from scipy.interpolate import UnivariateSpline
            sp = UnivariateSpline(xs_, ys_, s=max(len(xs_) * 0.5, 1.0))
            xx = np.linspace(xs_.min(), xs_.max(), 200)
            yy = sp(xx)
            method_label = "spline"
        except Exception:
            return artists
    elif method == "lowess":
        try:
            from statsmodels.nonparametric.smoothers_lowess import lowess
            r = lowess(ys_, xs_, frac=0.3, return_sorted=True)
            xx, yy = r[:, 0], r[:, 1]
            method_label = "lowess"
        except ImportError:
            # Fallback: cubic poly, behaviourally similar smoothing
            coef = np.polyfit(xs_, ys_, 3)
            xx = np.linspace(xs_.min(), xs_.max(), 200)
            yy = np.polyval(coef, xx)
            method_label = "poly3 (lowess unavailable)"
    else:
        return artists

    line, = ax.plot(xx, yy, color=color, linewidth=1.8, alpha=0.9,
                     zorder=8, solid_capstyle="round",
                     label=label or method_label)
    artists.append(line)

    # Faint dot scatter of the input points so users see what was fitted
    pts = ax.scatter(xs_, ys_, s=14, color=color, alpha=0.55,
                      edgecolors="white", linewidths=0.5, zorder=7)
    artists.append(pts)
    return artists


def fit_voice_center(df: pd.DataFrame, ax: Axes,
                     method: str = "polynomial", degree: int = 3,
                     color: str = "#ff3e88") -> list:
    """Per-MIDI median SPL → curve overlay (voice range center line)."""
    if "MIDI" not in df.columns or "dB" not in df.columns:
        return []
    g = df.groupby("MIDI")["dB"].median()
    xs = g.index.to_numpy(dtype=float)
    ys = g.to_numpy(dtype=float)
    return fit_overlay(ax, xs, ys, method=method, degree=degree, color=color,
                        label=f"voice center ({method})")


def fit_metric_trend(df: pd.DataFrame, col: str, ax: Axes,
                     method: str = "polynomial", degree: int = 3,
                     color: str = "#00d9ff") -> list:
    """Per-MIDI mean of `col` plotted as a secondary-axis curve.

    Useful when you want to show how a metric changes across pitch
    without losing the heatmap underneath. Creates a twin y-axis on
    the right so the metric scale is independent from SPL.
    """
    if col not in df.columns or "MIDI" not in df.columns:
        return []
    g = df.groupby("MIDI")[col].mean()
    xs = g.index.to_numpy(dtype=float)
    ys = g.to_numpy(dtype=float)
    finite = np.isfinite(xs) & np.isfinite(ys) & (ys != 0)
    if finite.sum() < 2:
        return []
    ax2 = ax.twinx()
    ax2.set_ylabel(f"{col} (per-MIDI mean)", color=color, fontsize=7)
    ax2.tick_params(axis="y", colors=color, labelsize=6)
    ax2.spines["right"].set_color(color)
    artists = fit_overlay(ax2, xs[finite], ys[finite],
                          method=method, degree=degree, color=color,
                          label=f"{col} trend")
    artists.append(ax2)
    return artists


# ─── Annotation ──────────────────────────────────────────────────────────────
def add_annotation(ax: Axes, x: float, y: float, text: str,
                   color: str = "#ff3e88") -> list:
    """Marker dot + label callout at data coords (x, y)."""
    artists: list = []
    pt = ax.plot([x], [y], "o", color=color, markersize=8,
                 markeredgecolor="black", markeredgewidth=0.7, zorder=10)[0]
    artists.append(pt)
    txt = ax.annotate(
        text, xy=(x, y), xytext=(8, 8), textcoords="offset points",
        color="#1a1a1a", fontsize=9, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", fc="white",
                  ec=color, alpha=0.92),
        arrowprops=dict(arrowstyle="-", color=color, alpha=0.7,
                        connectionstyle="arc3,rad=0.0"),
        zorder=11)
    artists.append(txt)
    return artists


# ─── Overlay state helper (used by GUI to track + clear overlays) ───────────
class OverlayManager:
    """Keep a list of artists added on top of the heatmap so the GUI can
    clear them with one call without nuking the underlying pcolormesh."""

    def __init__(self):
        self._artists: List = []
        self._twin_axes: List = []

    def add(self, artists):
        for a in artists:
            if a is None:
                continue
            # twin axes themselves are returned by fit_metric_trend so we
            # remove them on clear; everything else gets .remove()-d.
            if isinstance(a, Axes):
                self._twin_axes.append(a)
            else:
                self._artists.append(a)

    def clear(self):
        for a in self._artists:
            try:
                a.remove()
            except (NotImplementedError, ValueError):
                pass
        for tw in self._twin_axes:
            try:
                tw.remove()
            except (NotImplementedError, ValueError):
                pass
        self._artists.clear()
        self._twin_axes.clear()
