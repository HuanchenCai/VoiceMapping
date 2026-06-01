# -*- coding: utf-8 -*-
"""Theme tokens — colors, fonts, and metric-grouping data.

Centralised here so every other ``voicemap.gui.*`` module imports its
visual constants from one place. Changing a color here propagates
everywhere; **never hard-code a #xxxxxx in widget code**.

Palette follows option C (Studio, dark slate + amber) from
``docs/UI_DESIGN.md`` §1. Both the short legacy names (BG / PANEL /
ACCENT / …) and the more descriptive aliases (BG_APP / BG_PANEL /
BG_ELEVATED / TEXT_SEC / TEXT_MUTED / ACCENT_HOVER) refer to the same
values; widget code may use either spelling.
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
TEXT_MUTED    = "#8a8a8a"     # disabled / placeholder; 4.55:1 against
                              # PANEL — passes WCAG AA contrast.
TEXT_INVERSE  = "#0a0a0a"     # text on accent
ACCENT_HOVER  = ACCENT_HI
ACCENT_PRESS  = "#d97706"     # amber-600
SUCCESS       = OK
WARNING       = WARN
ERROR         = ERR
INFO          = "#3b82f6"
BG_DISABLED   = BORDER_STRONG    # disabled button / muted-control bg
BG_CODE       = "#0b1117"        # log / monospace text widget bg

# ── Plot palette (matplotlib axes / overlays) ──────────────────────────
# Separate from GUI tokens because charts have their own visual idiom
# (white plot area + dark grid) while the GUI shell is dark + amber.
# Centralising here so tweaks (e.g. swap chart bg) are one-line edits.
PLOT_FG          = "#1a1a1a"     # axis text / spines on white plot bg
PLOT_FG_SPINE    = "#444444"     # plot spine medium grey
PLOT_FG_DIM      = "#777777"     # category tag / muted plot text
PLOT_GRID        = "#cccccc"     # major gridlines
PLOT_GRID_LIGHT  = "#e6e6e6"     # minor gridlines / placeholder grid
PLOT_BG_EMPTY    = "#f2f2f2"     # masked/empty heatmap cells
PLOT_BG_AX       = "#ffffff"     # plot axes background
PLOT_OVERLAY_FIT = "#ff3e88"     # fit-curve overlay (pink)
PLOT_OVERLAY_2   = "#00d9ff"     # secondary overlay (cyan)
PLACEHOLDER_DIM  = "#888888"     # placeholder canvas tick / subtitle
PLACEHOLDER_TXT  = "#444444"     # placeholder canvas main message
READOUT_BG       = "#fef3c7"     # inline readout fill — pale-amber tint of ACCENT

# ── Fonts ───────────────────────────────────────────────────────────────
# Microsoft YaHei UI is Windows-native, has dedicated glyphs for both
# Latin and Han, and avoids the "some chars look bold, others don't"
# fallback artefact that Segoe UI exhibits when mixing Chinese.
#
# Typography scale (consistent across the app):
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
FONT_BTN_INFO = ("Microsoft YaHei UI", 14)            # ⓘ glyph next to Inspector metric name
FONT_INSPECTOR_NAME = ("Microsoft YaHei UI", 19, "bold")  # Inspector metric title (ACCENT, no overflow at 420 px)
FONT_ABOUT_TITLE = ("Microsoft YaHei UI", 16, "bold")     # AboutDialog 中文全称标题
FONT_TOOLTIP = ("Microsoft YaHei UI", 10)                 # HoverTooltip body
# Header app title — 14pt bold keeps the title legible at Windows
# 100% DPI while preserving visual hierarchy (Inspector metric name
# 19 > header 14 > body 11).
FONT_TITLE   = ("Microsoft YaHei UI", 14, "bold")
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
        "RMS", "F0_Hz",
        "SpectralCentroid", "SpectralBandwidth", "SpectralRolloff85",
        "SpectralFlatness", "SpectralSlope",
        "SpectralSkewness", "SpectralKurtosis",
        "AlphaRatio", "HammarbergIndex", "GNE",
        # MFCC 1-13 removed from menu per UI spec — analyzer still
        # writes the CSV columns but the metric selector hides them.
    ]),
    ("EGG · 电声门图", [
        "Qcontact", "dEGGmax", "HRFegg",
        "OQ", "SPQ", "CIQ",
        # Icontact removed from menu — derived metric (log·Qcontact) without
        # standalone clinical use; dEGGmax + Qcontact together convey same
        # info more transparently. CSV column still written by the analyzer.
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
    ("密度 · Density", ["Total", "VoicingRatio", "DUV"]),
]
_DEFAULT_METRIC_CHAIN = ["CPP", "Clarity", "SpecBal", "Crest"]
