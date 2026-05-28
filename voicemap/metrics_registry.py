#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Metric registry — single source of truth for every CSV column.

Each metric the analyzer produces is described by a `MetricSpec` and
registered into the global `REGISTRY`. Downstream consumers (plotter
colour scheme, GUI dropdown sections, Excel export, validation script)
read REGISTRY instead of duplicating per-metric metadata across files.

Adding a new metric becomes a 2-step change:
  1. Implement the calculator in src/metrics.py (or anywhere)
  2. Call `register(MetricSpec(...))` once for each output column

Existing 16 calculators are wrapped here with their old metadata so
plotter.METRIC_CFG and gui._METRIC_SECTIONS can be derived from this
file rather than duplicated.

NOTE: this module deliberately avoids importing the heavy analyzer
or plotter machinery so that registry queries stay cheap and import-
order safe.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm  # type: ignore


# ─── Spec ────────────────────────────────────────────────────────────────────
@dataclass
class MetricSpec:
    """Everything we need to know about one CSV column / heatmap layer."""
    key: str                           # CSV column name & GUI display name
    category: str                      # Acoustic / EGG / Singing / Cluster / Density
    label: str = ""                    # Pretty label for plot title
    unit: str = ""                     # Display unit, e.g. "dB", "%", "Hz"
    vmin: Optional[float] = None       # Heatmap colour limits
    vmax: Optional[float] = None
    cmap: Any = "viridis"              # matplotlib cmap or named string
    norm: Any = None                   # matplotlib norm (e.g. LogNorm)
    aggregator: str = "mean"           # "mean" | "max" | "sum"
    description: str = ""              # 1-line description for docs

    # The spec is a pure metadata layer; the calculator hook is
    # optional. Built-in metrics are computed via analyzer.calculate_
    # all_metrics() and share the column name declared here.
    calculator: Optional[Callable] = None
    requires: Tuple[str, ...] = ()     # input deps if calculator is provided

    # Marker for metrics still in development / not cross-validated.
    待验证: bool = False


# ─── Global registry ─────────────────────────────────────────────────────────
REGISTRY: dict = {}


def register(spec: MetricSpec) -> MetricSpec:
    """Add a spec to the registry. Last write wins (re-registration overrides)."""
    REGISTRY[spec.key] = spec
    return spec


def get(key: str) -> Optional[MetricSpec]:
    return REGISTRY.get(key)


def all_keys() -> list:
    return list(REGISTRY.keys())


def by_category(category: str) -> list:
    return [s for s in REGISTRY.values() if s.category == category]


def categories(order: Optional[list] = None) -> list:
    """Distinct category list. Pass `order` to enforce display order."""
    seen = []
    for s in REGISTRY.values():
        if s.category not in seen:
            seen.append(s.category)
    if order:
        return [c for c in order if c in seen] + [c for c in seen if c not in order]
    return seen


def keys_by_category(category: str) -> list:
    return [s.key for s in REGISTRY.values() if s.category == category]


# ─── Plotter integration helpers ─────────────────────────────────────────────
def to_metric_cfg() -> dict:
    """Build the legacy METRIC_CFG dict from current REGISTRY entries.
    Lets plotter.py keep its existing API while pulling data from here."""
    out = {}
    for s in REGISTRY.values():
        out[s.key] = dict(label=s.label or s.key,
                          vmin=s.vmin, vmax=s.vmax,
                          unit=s.unit, cmap=s.cmap, norm=s.norm)
    return out


def to_metric_category() -> dict:
    """Build the legacy METRIC_CATEGORY dict from REGISTRY."""
    return {s.key: s.category for s in REGISTRY.values()}


# ─── Built-in registrations ──────────────────────────────────────────────────
# Mirrors the original plotter.METRIC_CFG, gui._METRIC_SECTIONS, and
# analyzer's groupby aggregator. When a new metric is added, append to
# this block (or call register() from elsewhere).

# ─── Colormap policy ─────────────────────────────────────────────────────
# 全部 metric 使用三套感知均匀（perceptually uniform）调色板之一，
# 都是 luminance 单调（B&W 打印为干净灰度渐变）且通过红绿色盲安全
# 测试（deuteranopia / protanopia）。
#
#   PALETTE_SEQUENTIAL — 'viridis': blue → green → yellow.
#       默认调色板，用于所有"越大越显著"的指标（CPP / HNR / F1 等）。
#   PALETTE_DIVERGING  — 'coolwarm': red ← white → blue.
#       适用于有自然中点的指标（SpecBal=0、AlphaRatio=0、
#       H1H2 / H1H3=0、MFCCs=0）。
#   PALETTE_DENSITY    — 'mako': dark plum → bright green-blue.
#       适用于 Total / cycle count 等动态范围极大的对数轴。
#
# 类别型（maxCluster / maxCPhon）→ Okabe-Ito 5 色集，色盲安全。
PALETTE_SEQUENTIAL = "viridis"
PALETTE_DIVERGING  = "coolwarm"
PALETTE_DENSITY    = "mako"

# Okabe-Ito (Wong, Nature Methods 2011) — 8 distinguishable colours
# under all common color-vision deficiencies. We use the first 5 for
# 5-cluster discrete maps.
_OKABE_ITO_5 = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#F0E442"]


def _categorical_cmap_5():
    """5-class colorblind-safe ListedColormap for maxCluster / maxCPhon."""
    from matplotlib.colors import ListedColormap
    return ListedColormap(_OKABE_ITO_5, name="vm_cat5")


def _density_cmap_modern():
    """Density: try mako (seaborn-installed via matplotlib >= 3.7);
    fall back to viridis if mako isn't registered (older matplotlib)."""
    try:
        return plt.get_cmap(PALETTE_DENSITY)
    except (ValueError, KeyError):
        return plt.get_cmap("viridis")


def _populate_builtins():
    """Register the original 40 metrics. Called once at module import."""

    # ── Density ────────────────────────────────────────────────────────────
    register(MetricSpec(
        key="Total", category="Density", label="Density - Cycle Count",
        vmin=1, vmax=10000, unit="c", aggregator="sum",
        cmap=_density_cmap_modern(),
        norm=LogNorm(vmin=1, vmax=10000, clip=True),
        description="Number of analysed cycles in this (MIDI, dB) cell."))

    # ── Acoustic ───────────────────────────────────────────────────────────
    register(MetricSpec(
        key="Clarity", category="Acoustic", label="Audio Clarity",
        vmin=0.96, vmax=1.0, unit="", cmap="fd_clarity",
        aggregator="max",
        description="McLeod-Wyvill NSDF pitch-detection confidence."))
    register(MetricSpec(
        key="CPP", category="Acoustic", label="CPP",
        vmin=0.0, vmax=30.0, unit="dB", cmap="fd_cpp",
        description="Cepstral Peak Prominence."))
    register(MetricSpec(
        key="CPPS", category="Acoustic", label="CPPS (smoothed CPP)",
        vmin=0.0, vmax=30.0, unit="dB", cmap="fd_cpp",
        description="Smoothed CPP (Hillenbrand 1996)."))
    register(MetricSpec(
        key="SpecBal", category="Acoustic", label="Spectrum Balance",
        vmin=-42.0, vmax=0.0, unit="dB", cmap=PALETTE_DIVERGING,
        description="10·log10(E_below_1500Hz / E_above)."))
    register(MetricSpec(
        key="Crest", category="Acoustic", label="Crest Factor",
        vmin=1.414, vmax=4.0, unit="", cmap="fd_crest",
        description="Peak / RMS amplitude ratio."))
    register(MetricSpec(
        key="Entropy", category="Acoustic", label="Sample Entropy (CSE)",
        vmin=0.0, vmax=10.0, unit="", cmap="fd_entropy",
        description="Sample Entropy on per-cycle EGG harmonic vectors."))

    # Perturbation
    for k, label, vmax in [
        ("Jitter",       "Jitter (local)",     3.0),
        ("JitterRAP",    "Jitter RAP (3-pt)",  3.0),
        ("JitterPPQ5",   "Jitter PPQ5 (5-pt)", 3.0),
    ]:
        register(MetricSpec(
            key=k, category="Acoustic", label=label,
            vmin=0.0, vmax=vmax, unit="%",
            cmap="viridis",
            description="MDVP-style period perturbation with 1.3× factor."))
    for k, label, vmax in [
        ("Shimmer",       "Shimmer (local)", 10.0),
        ("ShimmerAPQ3",   "Shimmer APQ3 (3-pt)", 10.0),
        ("ShimmerAPQ5",   "Shimmer APQ5 (5-pt)", 10.0),
        ("ShimmerAPQ11",  "Shimmer APQ11 (11-pt)", 10.0),
    ]:
        register(MetricSpec(
            key=k, category="Acoustic", label=label,
            vmin=0.0, vmax=vmax, unit="%",
            cmap="viridis",
            description="MDVP-style amplitude perturbation."))
    register(MetricSpec(
        key="ShimmerDB", category="Acoustic", label="Shimmer",
        vmin=0.0, vmax=1.0, unit="dB",
        cmap="viridis",
        description="dB shimmer = mean |20·log10(A[i]/A[i-1])|."))

    register(MetricSpec(
        key="HNR", category="Acoustic", label="HNR",
        vmin=0.0, vmax=35.0, unit="dB",
        cmap="viridis",
        description="Harmonics-to-Noise Ratio (Praat autocorrelation)."))
    register(MetricSpec(
        key="NHR", category="Acoustic", label="NHR (Noise-to-Harm)",
        vmin=0.0, vmax=0.5, unit="",
        cmap="viridis",
        待验证=True,
        description="Noise-to-Harmonics Ratio = 1/10^(HNR/10)."))
    register(MetricSpec(
        key="PPE", category="Acoustic", label="Pitch Period Entropy",
        vmin=0.0, vmax=1.0, unit="",
        cmap="viridis",
        待验证=True,
        description="Shannon entropy of log-period in sliding window."))
    register(MetricSpec(
        key="ZCR", category="Acoustic", label="Zero-Crossing Rate",
        vmin=0.0, vmax=0.3, unit="",
        cmap="viridis",
        待验证=True,
        description="Per-cycle zero-crossings / cycle length."))

    # ── EGG ────────────────────────────────────────────────────────────────
    register(MetricSpec(
        key="Qcontact", category="EGG", label="Qci - Contact Quotient",
        vmin=0.1, vmax=0.6, unit="", cmap="fd_qci",
        description="FonaDyn integral-based contact quotient."))
    register(MetricSpec(
        key="dEGGmax", category="EGG", label="Qdelta - Peak dEGG",
        vmin=1.0, vmax=20.0, unit="slope", cmap="fd_degg",
        norm=LogNorm(vmin=1.0, vmax=20.0, clip=True),
        description="Peak amplitude of EGG derivative."))
    register(MetricSpec(
        key="Icontact", category="EGG", label="Ic - Index of Contacting",
        vmin=0.0, vmax=0.7, unit="", cmap="fd_ic",
        description="log10(dEGGmax) · Qcontact."))
    register(MetricSpec(
        key="HRFegg", category="EGG", label="HRFegg - EGG Harmonic Richness",
        vmin=-30.0, vmax=10.0, unit="dB", cmap="fd_hrf",
        description="Harmonic Richness Factor on EGG DFT."))
    register(MetricSpec(
        key="OQ", category="EGG", label="Open Quotient",
        vmin=0.2, vmax=0.8, unit="",
        cmap="viridis",
        description="(T - GOI) / T from dEGG peaks."))
    register(MetricSpec(
        key="SPQ", category="EGG", label="Speed Quotient",
        vmin=0.3, vmax=3.0, unit="",
        cmap="viridis",
        description="T_opening / T_closing."))
    register(MetricSpec(
        key="CIQ", category="EGG", label="Contact Index",
        vmin=-0.6, vmax=0.6, unit="",
        cmap="viridis",
        description="(T_closing - T_opening) / T_open."))

    # ── EGG-shape analogs derived from IAIF-reconstructed glottal flow ──
    # Populated only on mono inputs (no EGG channel). Same numeric formulas
    # as the EGG versions above, but applied to the negated glottal flow
    # (-g is "high when closed", mirroring EGG's contact semantics). Color
    # ranges intentionally match their EGG twins so the two heatmaps are
    # visually comparable when both are available.
    register(MetricSpec(
        key="Qcontact_voice", category="EGG", label="Qci (voice-derived)",
        vmin=0.1, vmax=0.6, unit="", cmap="fd_qci",
        待验证=True,
        description="Qcontact computed on -glottal_flow (IAIF). "
                    "Mono-mode equivalent of Qcontact when EGG is absent."))
    register(MetricSpec(
        key="dEGGmax_voice", category="EGG", label="Qdelta (voice-derived)",
        vmin=1.0, vmax=20.0, unit="slope", cmap="fd_degg",
        norm=LogNorm(vmin=1.0, vmax=20.0, clip=True),
        待验证=True,
        description="Peak negative dG/dt — closure speed proxy from IAIF."))
    register(MetricSpec(
        key="Icontact_voice", category="EGG", label="Ic (voice-derived)",
        vmin=0.0, vmax=0.7, unit="", cmap="fd_ic",
        待验证=True,
        description="log10(dEGGmax_voice) · Qcontact_voice."))
    register(MetricSpec(
        key="Entropy_voice", category="EGG", label="CSE (voice-derived)",
        vmin=0.0, vmax=10.0, unit="", cmap="fd_entropy",
        待验证=True,
        description="Sample Entropy on per-cycle DFT of -glottal_flow."))
    register(MetricSpec(
        key="HRFegg_voice", category="EGG", label="HRF (voice-derived)",
        vmin=-30.0, vmax=10.0, unit="dB", cmap="fd_hrf",
        待验证=True,
        description="Harmonic Richness Factor on per-cycle DFT of glottal flow."))
    register(MetricSpec(
        key="OQ_voice", category="EGG", label="OQ (voice-derived)",
        vmin=0.2, vmax=0.8, unit="",
        cmap="viridis",
        待验证=True,
        description="Open Quotient timing from glottal flow derivative."))
    register(MetricSpec(
        key="SPQ_voice", category="EGG", label="SPQ (voice-derived)",
        vmin=0.3, vmax=3.0, unit="",
        cmap="viridis",
        待验证=True,
        description="Speed Quotient from glottal flow derivative."))
    register(MetricSpec(
        key="CIQ_voice", category="EGG", label="CIQ (voice-derived)",
        vmin=-0.6, vmax=0.6, unit="",
        cmap="viridis",
        待验证=True,
        description="Contact Index from glottal flow derivative."))

    # ── Singing ────────────────────────────────────────────────────────────
    register(MetricSpec(
        key="VibratoRate", category="Singing", label="Vibrato rate",
        vmin=3.0, vmax=9.0, unit="Hz",
        cmap="viridis",
        description="Dominant F0 modulation in 4-8 Hz band."))
    register(MetricSpec(
        key="VibratoExtent", category="Singing", label="Vibrato extent",
        vmin=0.0, vmax=300.0, unit="cents",
        cmap="viridis",
        description="Peak-to-peak F0 modulation amplitude."))
    register(MetricSpec(
        key="F1", category="Singing", label="F1 - 1st formant",
        vmin=200.0, vmax=1000.0, unit="Hz",
        cmap="viridis",
        description="LPC spectrum peak ≥ f1_floor."))
    register(MetricSpec(
        key="F2", category="Singing", label="F2 - 2nd formant",
        vmin=800.0, vmax=2800.0, unit="Hz",
        cmap="viridis",
        description="2nd LPC peak above F1."))
    register(MetricSpec(
        key="F3", category="Singing", label="F3 - 3rd formant",
        vmin=2000.0, vmax=3600.0, unit="Hz",
        cmap="viridis",
        description="3rd LPC peak."))
    register(MetricSpec(
        key="SingersFormant", category="Singing", label="Singer's Formant Energy",
        vmin=-25.0, vmax=-5.0, unit="dB",
        cmap="viridis",
        description="2.8-3.4 kHz band energy / total (dB)."))
    register(MetricSpec(
        key="H1H2", category="Singing", label="H1-H2 (voice)",
        vmin=-10.0, vmax=20.0, unit="dB",
        cmap=PALETTE_DIVERGING,
        description="Voice DFT amplitude difference H1 − H2 (dB)."))
    register(MetricSpec(
        key="H1H3", category="Singing", label="H1-H3 (voice)",
        vmin=-10.0, vmax=25.0, unit="dB",
        cmap=PALETTE_DIVERGING,
        description="Voice DFT amplitude difference H1 − H3 (dB)."))

    # ── Cluster ────────────────────────────────────────────────────────────
    import matplotlib.pyplot as _plt   # local import to avoid eager dep
    # maxCluster / maxCPhon are categorical (1..5) — use Okabe-Ito
    # 5-colour palette so colorblind users can still tell clusters apart
    # (tab10 / Set2 fail under deuteranopia).
    register(MetricSpec(
        key="maxCluster", category="Cluster", label="Dominant EGG cluster",
        vmin=0.5, vmax=5.5, unit="",
        cmap=_categorical_cmap_5(),
        description="argmax of EGG-shape cluster shares per cell."))
    register(MetricSpec(
        key="maxCPhon", category="Cluster", label="Dominant phonation cluster",
        vmin=0.5, vmax=5.5, unit="",
        cmap=_categorical_cmap_5(),
        description="argmax of cPhon (quality-K-means) shares per cell."))
    for k in range(1, 6):
        register(MetricSpec(
            key=f"Cluster {k}", category="Cluster",
            label=f"EGG cluster {k} share",
            vmin=0, vmax=100, unit="%",
            cmap=_plt.get_cmap(PALETTE_SEQUENTIAL),
            description=f"% of cycles in EGG cluster {k}."))
        register(MetricSpec(
            key=f"cPhon {k}", category="Cluster",
            label=f"Phonation cluster {k} share",
            vmin=0, vmax=100, unit="%",
            cmap=_plt.get_cmap(PALETTE_SEQUENTIAL),
            description=f"% of cycles in phonation cluster {k}."))


def _populate_m1_addons():
    """Register the extended metric set (待验证)."""
    import matplotlib.pyplot as _plt

    # ── Acoustic — spectral moments + RMS + F0_Hz + Alpha + Hammarberg ────
    register(MetricSpec(
        key="RMS", category="Acoustic", label="RMS amplitude",
        vmin=0.0, vmax=0.5, unit="",
        cmap="viridis",
        待验证=True,
        description="Time-domain root-mean-square per frame."))
    register(MetricSpec(
        key="F0_Hz", category="Acoustic", label="F0",
        vmin=80.0, vmax=800.0, unit="Hz",
        cmap="viridis",
        待验证=True,
        description="Fundamental frequency in Hz (= 440·2^((MIDI-69)/12))."))
    register(MetricSpec(
        key="SpectralCentroid", category="Acoustic", label="Spectral Centroid",
        vmin=0.0, vmax=4000.0, unit="Hz",
        cmap="viridis",
        待验证=True,
        description="Σ(f·|X|²)/Σ|X|² — spectral 'center of mass'."))
    register(MetricSpec(
        key="SpectralBandwidth", category="Acoustic", label="Spectral Bandwidth",
        vmin=0.0, vmax=3000.0, unit="Hz",
        cmap="viridis",
        待验证=True,
        description="Spectral spread around centroid."))
    register(MetricSpec(
        key="SpectralRolloff85", category="Acoustic", label="Spectral Rolloff (85%)",
        vmin=0.0, vmax=8000.0, unit="Hz",
        cmap="viridis",
        待验证=True,
        description="Frequency below which 85% of spectral energy lies."))
    register(MetricSpec(
        key="SpectralFlatness", category="Acoustic", label="Spectral Flatness",
        vmin=0.0, vmax=1.0, unit="",
        cmap="viridis",
        待验证=True,
        description="geomean / mean — 0 tonal, 1 noisy."))
    register(MetricSpec(
        key="SpectralSlope", category="Acoustic", label="Spectral Slope",
        vmin=-0.05, vmax=0.0, unit="",
        cmap=PALETTE_DIVERGING,
        待验证=True,
        description="Linear slope of log10(|X|) vs frequency (0-5 kHz)."))
    register(MetricSpec(
        key="SpectralSkewness", category="Acoustic", label="Spectral Skewness",
        vmin=-3.0, vmax=10.0, unit="",
        cmap=PALETTE_DIVERGING,
        待验证=True,
        description="Third spectral moment around centroid."))
    register(MetricSpec(
        key="SpectralKurtosis", category="Acoustic", label="Spectral Kurtosis",
        vmin=-3.0, vmax=50.0, unit="",
        cmap=PALETTE_DIVERGING,
        待验证=True,
        description="Fourth spectral moment − 3."))
    register(MetricSpec(
        key="AlphaRatio", category="Acoustic", label="Alpha Ratio",
        vmin=-30.0, vmax=30.0, unit="dB",
        cmap=PALETTE_DIVERGING,
        待验证=True,
        description="10·log10(E[50-1000Hz] / E[1-5kHz])."))
    register(MetricSpec(
        key="HammarbergIndex", category="Acoustic", label="Hammarberg Index",
        vmin=-30.0, vmax=30.0, unit="dB",
        cmap=PALETTE_DIVERGING,
        待验证=True,
        description="max(0-2 kHz dB) − max(2-5 kHz dB)."))

    # MFCC 1-13 are intentionally absent from the registry: 13 entries
    # without clinical actionability would clutter the metric menu.
    # The analyzer still computes the columns and writes them to CSV
    # for power users; they are just hidden from the GUI metric
    # selector.

    # ── Singing — Formant bandwidths / dispersion / SPR / Vibrato Jitter ──
    register(MetricSpec(
        key="B1", category="Singing", label="B1 - 1st formant bandwidth",
        vmin=0.0, vmax=400.0, unit="Hz",
        cmap="viridis",
        待验证=True,
        description="LPC root bandwidth = -ln|z|·Fs/π."))
    register(MetricSpec(
        key="B2", category="Singing", label="B2 - 2nd formant bandwidth",
        vmin=0.0, vmax=400.0, unit="Hz",
        cmap="viridis",
        待验证=True,
        description="LPC root bandwidth for F2."))
    register(MetricSpec(
        key="B3", category="Singing", label="B3 - 3rd formant bandwidth",
        vmin=0.0, vmax=600.0, unit="Hz",
        cmap="viridis",
        待验证=True,
        description="LPC root bandwidth for F3."))
    register(MetricSpec(
        key="FormantDispersion", category="Singing", label="Formant Dispersion",
        vmin=0.0, vmax=2000.0, unit="Hz",
        cmap="viridis",
        待验证=True,
        description="(F3 − F1) / 2 — vocal-tract length proxy."))
    register(MetricSpec(
        key="SPR", category="Singing", label="Singing Power Ratio",
        vmin=-30.0, vmax=10.0, unit="dB",
        cmap="viridis",
        待验证=True,
        description="10·log10(E[2-4kHz] / E[0-2kHz])."))
    register(MetricSpec(
        key="VibratoJitter", category="Singing", label="Vibrato Jitter",
        vmin=0.0, vmax=20.0, unit="%",
        cmap="viridis",
        待验证=True,
        description="CV (%) of vibrato cycle period in sliding window."))

    # ── Acoustic — GNE-like (待验证, simplified) ──
    register(MetricSpec(
        key="GNE", category="Acoustic", label="GNE-like (simplified)",
        vmin=0.0, vmax=1.0, unit="",
        cmap="viridis",
        待验证=True,
        description="Simplified Glottal-to-Noise Excitation proxy."))

    # ── Density / Integrative (whole-recording broadcast) ──
    register(MetricSpec(
        key="MPT", category="Density", label="Maximum Phonation Time",
        vmin=0.0, vmax=30.0, unit="s",
        cmap=_plt.get_cmap("viridis"),
        待验证=True,
        description="Longest contiguous voiced run in seconds."))
    register(MetricSpec(
        key="VoicingRatio", category="Density", label="Voicing Ratio",
        vmin=0.0, vmax=1.0, unit="",
        cmap=_plt.get_cmap("viridis"),
        待验证=True,
        description="Voiced cycles / total cycles."))
    register(MetricSpec(
        key="DUV", category="Density", label="Degree of Unvoiced",
        vmin=0.0, vmax=100.0, unit="%",
        cmap=_plt.get_cmap("magma"),
        待验证=True,
        description="100 − VoicingRatio·100."))


# Display order for `categories(order=…)` callers.
DEFAULT_CATEGORY_ORDER = (
    "Acoustic", "EGG", "Singing", "Cluster", "Density"
)


# Eager populate so anyone importing this module immediately gets the
# 40 builtin specs available.
_populate_builtins()
_populate_m1_addons()
