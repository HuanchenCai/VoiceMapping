# -*- coding: utf-8 -*-
"""Theme tokens — colors, fonts, and metric-grouping data.

Centralised here so every other ``voicemap.gui.*`` module imports its
visual constants from one place. Changing a color here propagates
everywhere; **never hard-code a #xxxxxx in widget code**.

TODO: A0-3 / A0-4 swap this palette to the option-C amber theme spec'd
in ``docs/UI_DESIGN.md``. The current values preserve the dark-cyan
look that was in place before A0-2 to keep the structural refactor
visually identical to the previous gui.py.
"""

# ── Colors ──────────────────────────────────────────────────────────────
BG        = "#0f1419"   # window base
PANEL     = "#162029"   # primary panel cards
PANEL_HI  = "#1e2a36"   # selected row / hover
BORDER    = "#243141"   # default subtle separator
TEXT      = "#e6edf3"   # primary text, headings
MUTED     = "#7d8590"   # secondary text, placeholders
ACCENT    = "#00d9ff"   # brand color (cyan)
ACCENT_HI = "#4de6ff"   # accent hover / pressed
OK        = "#3fb950"   # success / "good"
WARN      = "#d29922"   # warning / "watch"
ERR       = "#f85149"   # error / "abnormal"

# ── Fonts ───────────────────────────────────────────────────────────────
# Microsoft YaHei UI is Windows-native, has dedicated glyphs for both
# Latin and Han, and avoids the "some chars look bold, others don't"
# fallback artefact that Segoe UI exhibits when mixing Chinese.
FONT_UI    = ("Microsoft YaHei UI", 10)
FONT_UI_B  = ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 16, "bold")
FONT_SUB   = ("Microsoft YaHei UI", 10)
FONT_DROP  = ("Microsoft YaHei UI", 13, "bold")
FONT_MONO  = ("Consolas", 9)


# ── Metric grouping (cascade dropdown / menubar order) ─────────────────
# Each section becomes one cascade in the metric menu. Future metrics
# slot into the section that matches their conceptual category.
_METRIC_SECTIONS: list = [
    ("声学 · Acoustic", [
        "Clarity", "CPP", "CPPS", "SpecBal", "Crest", "Entropy",
        "Jitter", "JitterRAP", "JitterPPQ5",
        "Shimmer", "ShimmerDB",
        "ShimmerAPQ3", "ShimmerAPQ5", "ShimmerAPQ11",
        "HNR", "NHR",
        "PPE", "ZCR",
        # M1 add-on
        "RMS", "F0_Hz",
        "SpectralCentroid", "SpectralBandwidth", "SpectralRolloff85",
        "SpectralFlatness", "SpectralSlope",
        "SpectralSkewness", "SpectralKurtosis",
        "AlphaRatio", "HammarbergIndex", "GNE",
        *(f"MFCC{i+1}" for i in range(13)),
    ]),
    ("EGG · 电声门图", [
        "Qcontact", "Icontact", "dEGGmax", "HRFegg",
        "OQ", "SPQ", "CIQ",
    ]),
    ("唱歌特异性 · Singing-specific", [
        "VibratoRate", "VibratoExtent", "VibratoJitter",
        "F1", "F2", "F3", "SingersFormant",
        "B1", "B2", "B3", "FormantDispersion", "SPR",
        "H1H2", "H1H3",
    ]),
    ("聚类 · Cluster / cPhon", [
        "maxCluster", "Cluster 1", "Cluster 2", "Cluster 3", "Cluster 4", "Cluster 5",
        "maxCPhon",   "cPhon 1",   "cPhon 2",   "cPhon 3",   "cPhon 4",   "cPhon 5",
    ]),
    ("密度 · Density", ["Total", "MPT", "VoicingRatio", "DUV"]),
]
_DEFAULT_METRIC_CHAIN = ["CPP", "Clarity", "SpecBal", "Crest"]
