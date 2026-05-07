# -*- coding: utf-8 -*-
"""Theme tokens — colors, fonts, and metric-grouping data.

Centralised here so every other ``voicemap.gui.*`` module imports its
visual constants from one place. Changing a color here propagates
everywhere; **never hard-code a #xxxxxx in widget code**.

A0-3 swap: palette is now option C (Studio, dark slate + amber) per
``docs/UI_DESIGN.md`` §1. Pre-A0-3 it was option A (dark cyan). The
old constant *names* are preserved (BG / PANEL / ACCENT / …) so
existing widget code using them keeps working — only the *values*
changed. New code may also use the more descriptive aliases (BG_APP /
BG_PANEL / BG_ELEVATED / TEXT_SEC / TEXT_MUTED / ACCENT_HOVER) which
match the spec verbatim.
"""

# ── Colors (option C — Studio, dark + amber) ────────────────────────────
BG        = "#0a0a0a"   # window base (BG_APP)
PANEL     = "#1a1a1a"   # primary panel cards (BG_PANEL)
PANEL_HI  = "#2a2a2a"   # selected row / hover (BG_ELEVATED)
BORDER    = "#3a3a3a"   # default subtle separator
TEXT      = "#f5f5f5"   # primary text, headings
MUTED     = "#a3a3a3"   # secondary text (TEXT_SEC); TEXT_MUTED below for placeholders
ACCENT    = "#f59e0b"   # brand color (amber-500)
ACCENT_HI = "#fbbf24"   # accent hover / pressed (amber-400)
OK        = "#84cc16"   # success / "good" (lime-500)
WARN      = "#f59e0b"   # warning / "watch" — shares amber w/ ACCENT (per spec)
ERR       = "#ef4444"   # error / "abnormal" (red-500)

# Spec-verbatim aliases for new code; old names above stay for back-compat.
BG_APP        = BG
BG_PANEL      = PANEL
BG_ELEVATED   = PANEL_HI
BORDER_STRONG = "#525252"
TEXT_SEC      = MUTED
TEXT_MUTED    = "#737373"     # disabled / placeholder
TEXT_INVERSE  = "#0a0a0a"     # text on accent
ACCENT_HOVER  = ACCENT_HI
ACCENT_PRESS  = "#d97706"     # amber-600
SUCCESS       = OK
WARNING       = WARN
ERROR         = ERR
INFO          = "#3b82f6"

# ── Fonts ───────────────────────────────────────────────────────────────
# Microsoft YaHei UI is Windows-native, has dedicated glyphs for both
# Latin and Han, and avoids the "some chars look bold, others don't"
# fallback artefact that Segoe UI exhibits when mixing Chinese.
#
# A0-4 typography scale (consistent across the app):
#   Caption  9pt   tiny / unit hints
#   Small   10pt   row metadata, status bar
#   Body    11pt   default UI body, buttons
#   BodyB   11pt bold       section labels (Tracks / Metric / etc.)
#   Sub     12pt   header status pill
#   Drop    13pt bold       drop-zone main hint
#   H2      15pt bold       Inspector value pill / metric-bar emphasis
#   Title   18pt bold       window header (嗓音声学品质多维分析图谱)
#   Display 22pt bold       Inspector metric name + value big number
FONT_CAPTION = ("Microsoft YaHei UI",  9)
FONT_SMALL   = ("Microsoft YaHei UI", 10)
FONT_UI      = ("Microsoft YaHei UI", 11)
FONT_UI_B    = ("Microsoft YaHei UI", 11, "bold")
FONT_SUB     = ("Microsoft YaHei UI", 12)
FONT_DROP    = ("Microsoft YaHei UI", 13, "bold")
FONT_H2      = ("Microsoft YaHei UI", 15, "bold")
FONT_TITLE   = ("Microsoft YaHei UI", 18, "bold")
FONT_DISPLAY = ("Microsoft YaHei UI", 22, "bold")
FONT_MONO    = ("Consolas", 10)
FONT_MONO_B  = ("Consolas", 22, "bold")     # large numerics on value pill


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
        # MFCC 1-13 removed from menu per UI spec — analyzer still
        # writes the CSV columns but the metric selector hides them.
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
