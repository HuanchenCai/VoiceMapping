"""
Render the 4 UI design options as 1200x720 PNG mockups.
Real fonts, real-ish heatmap, real spacing — the user can see what each
option actually looks like instead of reading ASCII art.

Usage:
    python docs/mockups/render_mockups.py
"""
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, Rectangle
import matplotlib as mpl

mpl.rcParams["font.family"] = ["Microsoft YaHei", "Segoe UI", "DejaVu Sans"]
mpl.rcParams["font.size"] = 10

OUT = os.path.dirname(os.path.abspath(__file__))


def fake_vrp_grid():
    """Generate a plausible-looking VRP heatmap (MIDI x SPL)."""
    midi = np.arange(30, 96)
    spl = np.arange(40, 120)
    grid = np.full((len(spl), len(midi)), np.nan)
    rng = np.random.default_rng(42)
    # Singer's range: midi 48-72, spl 60-95, peak around 60/80
    for cx, cy, sx, sy, amp in [
        (60, 80, 14, 18, 16),
        (54, 75, 8, 10, 12),
        (66, 88, 10, 12, 13),
    ]:
        for i, m in enumerate(midi):
            for j, s in enumerate(spl):
                d = ((m - cx) / sx) ** 2 + ((s - cy) / sy) ** 2
                if d < 1:
                    val = amp * (1 - d) + rng.normal(0, 1.5)
                    if np.isnan(grid[j, i]) or grid[j, i] < val:
                        grid[j, i] = val
    return grid, midi, spl


# ── helpers ───────────────────────────────────────────────────────────────
def panel(ax, x, y, w, h, fill, edge=None, lw=0.8, radius=0):
    if radius > 0:
        rect = FancyBboxPatch((x, y), w, h,
                               boxstyle=f"round,pad=0,rounding_size={radius}",
                               linewidth=lw, edgecolor=edge or fill, facecolor=fill,
                               transform=ax.transAxes, zorder=1)
    else:
        rect = Rectangle((x, y), w, h,
                          linewidth=lw, edgecolor=edge or fill, facecolor=fill,
                          transform=ax.transAxes, zorder=1)
    ax.add_patch(rect)
    return rect


def text(ax, x, y, s, **kw):
    kw.setdefault("transform", ax.transAxes)
    kw.setdefault("zorder", 5)
    return ax.text(x, y, s, **kw)


def heatmap_in(ax, fig, region, theme):
    """Draw a small VRP heatmap at the given (x0, y0, w, h) in FIGURE coords."""
    grid, midi, spl = fake_vrp_grid()
    fx, fy, fw, fh = region
    sub = fig.add_axes([fx, fy, fw, fh], zorder=10)
    sub.set_facecolor(theme["heatmap_bg"])
    cmap = plt.cm.viridis if theme.get("dark") else plt.cm.RdYlBu_r
    im = sub.imshow(grid, origin="lower", aspect="auto",
                     extent=[midi[0], midi[-1], spl[0], spl[-1]],
                     cmap=cmap, vmin=0, vmax=18)
    sub.set_xticks([30, 48, 60, 72, 84, 96])
    sub.set_yticks([40, 60, 80, 100, 120])
    for spine in sub.spines.values():
        spine.set_color(theme["border"])
    sub.tick_params(colors=theme["text_muted"], labelsize=7, length=2)
    sub.set_xlabel("MIDI", color=theme["text_muted"], fontsize=8)
    sub.set_ylabel("SPL (dB)", color=theme["text_muted"], fontsize=8)
    sub.set_title("CPP [dB]", color=theme["text_primary"],
                   fontsize=10, fontweight="bold", pad=4)


# ── option A: Modern Dashboard ────────────────────────────────────────────
def render_option_a():
    theme = {
        "bg_app":      "#0a0e13",
        "bg_panel":    "#131922",
        "bg_elev":     "#1a212d",
        "border":      "#2a3340",
        "text_primary":"#e4eaf2",
        "text_sec":    "#94a3b8",
        "text_muted":  "#64748b",
        "accent":      "#00d9ff",
        "success":     "#4ade80",
        "warning":     "#fbbf24",
        "heatmap_bg":  "#131922",
        "dark": True,
    }
    fig = plt.figure(figsize=(12, 7.2), dpi=110, facecolor=theme["bg_app"])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.set_facecolor(theme["bg_app"])

    # App bar
    panel(ax, 0, 0.93, 1, 0.07, theme["bg_panel"])
    text(ax, 0.015, 0.965, "VoiceMap", color=theme["text_primary"],
         fontsize=14, fontweight="bold", va="center")
    text(ax, 0.11, 0.965, "✓", color=theme["success"], fontsize=12, va="center")
    text(ax, 0.13, 0.965, "test_Voice_EGG.wav", color=theme["text_sec"],
         fontsize=11, va="center")
    text(ax, 0.86, 0.965, "中文 ⚙ ? ─", color=theme["text_sec"], fontsize=11, va="center")

    # Sidebar
    panel(ax, 0, 0.04, 0.18, 0.89, theme["bg_panel"])
    text(ax, 0.013, 0.90, "FILES", color=theme["text_muted"],
         fontsize=9, fontweight="bold", va="center")
    text(ax, 0.16, 0.90, "+", color=theme["accent"], fontsize=14, va="center", ha="right")

    # File item — selected
    panel(ax, 0.012, 0.84, 0.156, 0.045, theme["bg_elev"], radius=0.005)
    panel(ax, 0.012, 0.84, 0.003, 0.045, theme["accent"])  # accent left bar
    text(ax, 0.022, 0.872, "✓ test_Voice_EGG.wav", color=theme["text_primary"],
         fontsize=9, va="center")
    text(ax, 0.022, 0.852, "44.1 kHz · 8.2s · 12,525 cells",
         color=theme["text_muted"], fontsize=8, va="center")

    # File items — unanalyzed
    for i, (status, name) in enumerate([("○", "recording_2.wav"),
                                          ("○", "recording_3.wav")]):
        y = 0.79 - i * 0.05
        text(ax, 0.022, y, f"{status} {name}", color=theme["text_muted"],
             fontsize=9, va="center")

    # Inspector
    panel(ax, 0.78, 0.04, 0.22, 0.89, theme["bg_panel"])
    text(ax, 0.79, 0.90, "ⓘ 详情", color=theme["text_muted"],
         fontsize=9, fontweight="bold", va="center")

    panel(ax, 0.79, 0.78, 0.20, 0.10, theme["bg_elev"], radius=0.005)
    text(ax, 0.80, 0.855, "当前指标", color=theme["text_muted"], fontsize=9, va="center")
    text(ax, 0.80, 0.825, "CPP", color=theme["text_primary"],
         fontsize=15, fontweight="bold", va="center")
    text(ax, 0.80, 0.800, "倒谱峰显著度", color=theme["text_sec"], fontsize=9, va="center")

    panel(ax, 0.79, 0.55, 0.20, 0.21, theme["bg_elev"], radius=0.005)
    text(ax, 0.80, 0.730, "临床范围 (dB)", color=theme["text_muted"],
         fontsize=9, fontweight="bold", va="center")
    rows = [("≥ 14   良好", theme["success"]),
            ("10-14  正常", theme["text_sec"]),
            ("6-10   关注", theme["warning"]),
            ("< 6    异常", "#f87171")]
    for i, (s, c) in enumerate(rows):
        text(ax, 0.80, 0.700 - i * 0.025, s, color=c, fontsize=9, va="center")
    text(ax, 0.80, 0.580, "本次值", color=theme["text_muted"],
         fontsize=9, fontweight="bold", va="center")
    text(ax, 0.80, 0.560, "16.79 dB ✓", color=theme["success"],
         fontsize=14, fontweight="bold", va="center")

    # Actions card
    panel(ax, 0.79, 0.10, 0.20, 0.42, theme["bg_elev"], radius=0.005)
    text(ax, 0.80, 0.495, "操作", color=theme["text_muted"],
         fontsize=9, fontweight="bold", va="center")
    for i, (label, primary) in enumerate([("导出 Excel", False),
                                            ("生成报告", False),
                                            ("比对 2 段录音", False)]):
        y = 0.45 - i * 0.05
        bg = theme["accent"] if primary else theme["bg_panel"]
        fg = theme["bg_app"] if primary else theme["text_primary"]
        panel(ax, 0.80, y, 0.18, 0.035, bg, edge=theme["border"], radius=0.005)
        text(ax, 0.89, y + 0.0175, label, color=fg, fontsize=9,
             va="center", ha="center")

    # Canvas area (between sidebar and inspector)
    panel(ax, 0.18, 0.04, 0.60, 0.89, theme["bg_app"])

    # Metric tabs
    tab_y = 0.86
    tabs = [("声学", True), ("EGG", False), ("唱歌", False),
             ("聚类", False), ("更多 ▾", False)]
    x = 0.20
    for label, active in tabs:
        w = 0.075 if "更多" in label else 0.07
        bg = theme["accent"] if active else theme["bg_panel"]
        fg = theme["bg_app"] if active else theme["text_sec"]
        panel(ax, x, tab_y, w, 0.04, bg, edge=theme["border"], radius=0.005)
        text(ax, x + w/2, tab_y + 0.02, label, color=fg, fontsize=10,
             va="center", ha="center", fontweight="bold" if active else "normal")
        x += w + 0.01

    # Heatmap card
    panel(ax, 0.20, 0.20, 0.56, 0.62, "#ffffff", edge=theme["border"], radius=0.012)
    heatmap_in(ax, fig, (0.235, 0.245, 0.51, 0.55), {**theme, "heatmap_bg": "#ffffff"})

    # Floating nav arrows (semi-transparent)
    text(ax, 0.205, 0.51, "◀", color=theme["accent"], fontsize=22,
         alpha=0.7, va="center", ha="center")
    text(ax, 0.755, 0.51, "▶", color=theme["accent"], fontsize=22,
         alpha=0.7, va="center", ha="center")

    # Plot toolbar
    tb_y = 0.13
    panel(ax, 0.20, tb_y, 0.56, 0.045, theme["bg_panel"], radius=0.005)
    tools = ["拟合 ▾", "标注", "复位", "复制图片", "保存 ▾"]
    x = 0.215
    for t in tools:
        text(ax, x, tb_y + 0.022, t, color=theme["text_sec"], fontsize=9, va="center")
        x += 0.10

    # Status bar
    panel(ax, 0, 0, 1, 0.04, theme["bg_panel"])
    text(ax, 0.013, 0.02, "✓ 12,525 cells  ·  Clarity ≥ 0.97  ·  3,420 cycles  ·  12.6s",
         color=theme["text_muted"], fontsize=9, va="center")

    # Title (annotation)
    text(ax, 0.5, 0.998, "方案 A — Modern Dashboard (深色 + cyan)",
         color=theme["accent"], fontsize=11, fontweight="bold",
         va="top", ha="center")

    out = os.path.join(OUT, "option_A_modern.png")
    fig.savefig(out, dpi=110, facecolor=theme["bg_app"], edgecolor="none")
    plt.close(fig)
    print("wrote", out)


# ── option B: Clinical Workstation ────────────────────────────────────────
def render_option_b():
    theme = {
        "bg_app":      "#f8fafc",
        "bg_panel":    "#ffffff",
        "bg_elev":     "#f1f5f9",
        "border":      "#cbd5e1",
        "border_sub":  "#e2e8f0",
        "text_primary":"#0f172a",
        "text_sec":    "#475569",
        "text_muted":  "#64748b",
        "accent":      "#0891b2",
        "success":     "#059669",
        "warning":     "#d97706",
        "error":       "#dc2626",
        "heatmap_bg":  "#ffffff",
        "dark": False,
    }
    fig = plt.figure(figsize=(12, 7.2), dpi=110, facecolor=theme["bg_app"])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    # Title bar
    panel(ax, 0, 0.95, 1, 0.05, theme["accent"])
    text(ax, 0.015, 0.975, "VoiceMap V1.0 — 嗓音声学品质多维分析图谱",
         color="white", fontsize=11, fontweight="bold", va="center")

    # Menubar
    panel(ax, 0, 0.92, 1, 0.03, theme["bg_panel"], edge=theme["border_sub"])
    menus = ["文件(F)", "编辑(E)", "视图(V)", "分析(A)", "工具(T)", "帮助(H)"]
    x = 0.012
    for m in menus:
        text(ax, x, 0.935, m, color=theme["text_primary"], fontsize=10, va="center")
        x += 0.06

    # Sidebar
    panel(ax, 0, 0.04, 0.16, 0.88, theme["bg_panel"], edge=theme["border_sub"])
    text(ax, 0.012, 0.895, "文件列表", color=theme["text_sec"],
         fontsize=9, fontweight="bold", va="center")

    panel(ax, 0.005, 0.85, 0.15, 0.035, theme["bg_elev"])
    panel(ax, 0.005, 0.85, 0.0025, 0.035, theme["accent"])
    text(ax, 0.012, 0.875, "✓ test_Voice_EGG.wav", color=theme["text_primary"],
         fontsize=9, fontweight="bold", va="center")
    text(ax, 0.012, 0.860, "8.2s · 12,525 cells",
         color=theme["text_muted"], fontsize=8, va="center")

    text(ax, 0.012, 0.815, "○ recording_2.wav",
         color=theme["text_muted"], fontsize=9, va="center")
    text(ax, 0.012, 0.795, "○ recording_3.wav",
         color=theme["text_muted"], fontsize=9, va="center")

    # File metadata header
    panel(ax, 0.16, 0.86, 0.84, 0.06, theme["bg_panel"], edge=theme["border_sub"])
    text(ax, 0.17, 0.895, "文件: test_Voice_EGG.wav", color=theme["text_primary"],
         fontsize=10, fontweight="bold", va="center")
    text(ax, 0.36, 0.895, "│ 采样率 44,100 Hz │ 时长 8.2 s │ 通道 2 (Mic + EGG)",
         color=theme["text_sec"], fontsize=9, va="center")
    text(ax, 0.17, 0.875, "状态: ✓ 已分析", color=theme["success"],
         fontsize=9, fontweight="bold", va="center")
    text(ax, 0.27, 0.875, "│ 周期 3,420 │ 分析耗时 12.6s │ Clarity 阈值 0.97 │ k = 5",
         color=theme["text_sec"], fontsize=9, va="center")

    # Metric table (left of canvas)
    panel(ax, 0.16, 0.30, 0.30, 0.55, theme["bg_panel"], edge=theme["border_sub"])
    text(ax, 0.17, 0.835, "指标 (Metric)                 数值      范围      状态",
         color=theme["text_sec"], fontsize=9, fontweight="bold", va="center",
         family=["Consolas", "Cascadia Code"])
    metrics = [
        ("Clarity",          "0.997",  "良好", theme["success"], "✓"),
        ("CPP [dB]",         "16.79",  "良好", theme["success"], "✓"),
        ("CPPS [dB]",        "16.79",  "良好", theme["success"], "✓"),
        ("HNR [dB]",         "30.30",  "良好", theme["success"], "✓"),
        ("Jitter [%]",       " 0.79",  "关注", theme["warning"], "!"),
        ("Shimmer [%]",      " 1.27",  "正常", theme["text_sec"], "·"),
        ("Qcontact",         " 0.42",  "正常", theme["text_sec"], "·"),
        ("OQ",               " 0.56",  "正常", theme["text_sec"], "·"),
        ("CIQ",              "-0.03",  "正常", theme["text_sec"], "·"),
        ("dEGGmax",          " 5.78",  "正常", theme["text_sec"], "·"),
        ("F1 [Hz]",          " 485.1", "—",    theme["text_muted"], "—"),
        ("F2 [Hz]",          " 972.4", "—",    theme["text_muted"], "—"),
        ("F3 [Hz]",          "1990.4", "—",    theme["text_muted"], "—"),
        ("VibratoRate [Hz]", " 5.20",  "良好", theme["success"], "✓"),
        ("VibratoExtent",    "45.51",  "正常", theme["text_sec"], "·"),
    ]
    for i, (name, val, rng_label, color, mark) in enumerate(metrics):
        y = 0.815 - i * 0.026
        if i % 2 == 0:
            panel(ax, 0.165, y - 0.011, 0.29, 0.024, theme["bg_elev"])
        text(ax, 0.17, y, f"{name:<22}", color=theme["text_primary"], fontsize=8,
             va="center", family=["Consolas", "Cascadia Code"])
        text(ax, 0.32, y, val, color=theme["text_primary"], fontsize=8,
             va="center", family=["Consolas", "Cascadia Code"])
        text(ax, 0.39, y, rng_label, color=color, fontsize=8, va="center")
        text(ax, 0.44, y, mark, color=color, fontsize=10, va="center", fontweight="bold")

    # Heatmap card (right side)
    panel(ax, 0.47, 0.30, 0.52, 0.55, theme["bg_panel"], edge=theme["border"])
    heatmap_in(ax, fig, (0.495, 0.335, 0.475, 0.49), theme)

    # Compact toolbar below heatmap
    panel(ax, 0.16, 0.25, 0.83, 0.04, theme["bg_panel"], edge=theme["border_sub"])
    tools = ["拟合 ▾", "标注", "复位", "复制图片", "保存 ▾", "│", "导出 Excel", "生成报告", "对比 2 段"]
    x = 0.17
    for t in tools:
        if t == "│":
            text(ax, x, 0.27, t, color=theme["border"], fontsize=12, va="center")
            x += 0.012
        else:
            text(ax, x, 0.27, t, color=theme["text_primary"], fontsize=9, va="center")
            x += 0.075

    # Reference panel
    panel(ax, 0.16, 0.04, 0.83, 0.20, theme["bg_panel"], edge=theme["border_sub"])
    text(ax, 0.17, 0.225, "当前指标 · CPP — Cepstral Peak Prominence",
         color=theme["text_primary"], fontsize=10, fontweight="bold", va="center")
    text(ax, 0.17, 0.205, "倒谱峰显著度 · 单位 dB",
         color=theme["text_sec"], fontsize=9, va="center")
    text(ax, 0.17, 0.175, "临床参考范围",
         color=theme["text_sec"], fontsize=9, fontweight="bold", va="center")
    rows = [("≥ 14",   "良好",  theme["success"]),
            ("10–14", "正常",  theme["text_sec"]),
            ("6–10",  "关注",  theme["warning"]),
            ("< 6",    "异常",  theme["error"])]
    x = 0.17
    for rng_v, label, color in rows:
        text(ax, x, 0.150, rng_v, color=theme["text_primary"], fontsize=9,
             va="center", family=["Consolas", "Cascadia Code"])
        text(ax, x, 0.130, label, color=color, fontsize=9, fontweight="bold", va="center")
        x += 0.10
    text(ax, 0.17, 0.090, "本次值", color=theme["text_sec"],
         fontsize=9, fontweight="bold", va="center")
    text(ax, 0.17, 0.065, "16.79 dB",
         color=theme["success"], fontsize=14, fontweight="bold", va="center",
         family=["Consolas", "Cascadia Code"])
    text(ax, 0.27, 0.067, "✓ 良好", color=theme["success"], fontsize=10,
         va="center", fontweight="bold")
    text(ax, 0.50, 0.07,
          "n = 12,525   · 范围内: 12,140 (96.9%)  · 关注及以下: 385",
          color=theme["text_sec"], fontsize=9, va="center")

    # Status bar
    panel(ax, 0, 0, 1, 0.04, theme["bg_elev"], edge=theme["border_sub"])
    text(ax, 0.013, 0.02, "就绪  ·  Clarity 阈值 = 0.97  ·  k = 5  ·  n_harm = 10",
         color=theme["text_sec"], fontsize=9, va="center")
    text(ax, 0.99, 0.02, "© 2026 蔡寰宸  ·  V1.0", color=theme["text_muted"],
         fontsize=9, va="center", ha="right")

    # Title
    text(ax, 0.5, 0.998, "方案 B — Clinical Workstation (浅色 + navy/teal)",
         color=theme["accent"], fontsize=11, fontweight="bold",
         va="top", ha="center")

    out = os.path.join(OUT, "option_B_clinical.png")
    fig.savefig(out, dpi=110, facecolor=theme["bg_app"], edgecolor="none")
    plt.close(fig)
    print("wrote", out)


# ── option C: Studio (locked-in choice; rendered in both zh and en) ───────
C_STRINGS = {
    "zh": {
        "title":         "嗓音声学品质多维分析图谱",
        "title_short":   "嗓音声学品质多维分析图谱",
        "tracks_label":  "录音轨",
        "metric_label":  "指标",
        "nav_hint":      "│  上一个 ←   下一个 →",
        "lang_toggle":   "EN",
        "settings":      "设置",
        "help":          "帮助",
        "minimize":      "─",
        "metric_full":   "倒谱峰显著度",
        "metric_unit":   "单位 dB",
        "clinical":      "临床参考范围",
        "current":       "本次值",
        "good":          "良好",
        "normal":        "正常",
        "watch":         "关注",
        "abnorm":        "异常",
        "good_marked":   "✓ 良好",
        "btn_excel":     "导出 Excel",
        "btn_report":    "生成报告",
        "btn_compare":   "对比录音",
        "tool_fit":      "拟合 ▾",
        "tool_note":     "标注",
        "tool_reset":    "复位",
        "tool_copy":     "复制图片",
        "tool_save":     "保存 ▾",
        "status_prefix": "● 文件 01  ·  12,525 网格  ·  k = 5  ·  3,420 个周期  ·  耗时 12.6 秒",
        "subtitle":      "方案 C 中文版 — 工作站布局（深灰 + amber）",
        "cells":         "网格",
    },
    "en": {
        "title":         "VoiceMap",
        "title_short":   "VoiceMap",
        "tracks_label":  "TRACKS",
        "metric_label":  "METRIC",
        "nav_hint":      "│  Prev ←   Next →",
        "lang_toggle":   "中",
        "settings":      "Settings",
        "help":          "Help",
        "minimize":      "─",
        "metric_full":   "Cepstral Peak Prominence",
        "metric_unit":   "Unit: dB",
        "clinical":      "CLINICAL",
        "current":       "CURRENT",
        "good":          "GOOD",
        "normal":        "NORMAL",
        "watch":         "WATCH",
        "abnorm":        "ABNORM",
        "good_marked":   "✓ GOOD",
        "btn_excel":     "EXPORT XLSX",
        "btn_report":    "GEN REPORT",
        "btn_compare":   "COMPARE",
        "tool_fit":      "FIT ▾",
        "tool_note":     "NOTE",
        "tool_reset":    "RESET",
        "tool_copy":     "COPY",
        "tool_save":     "SAVE ▾",
        "status_prefix": "● File 01  ·  12,525 cells  ·  k = 5  ·  3,420 cycles  ·  12.6s",
        "subtitle":      "Option C — Studio (dark + amber, English)",
        "cells":         "cells",
    },
}


def render_option_c(lang="zh"):
    s = C_STRINGS[lang]
    theme = {
        "bg_app":      "#0a0a0a",
        "bg_panel":    "#1a1a1a",
        "bg_elev":     "#2a2a2a",
        "border":      "#3a3a3a",
        "text_primary":"#f5f5f5",
        "text_sec":    "#a3a3a3",
        "text_muted":  "#737373",
        "accent":      "#f59e0b",
        "accent_hi":   "#fbbf24",
        "success":     "#84cc16",
        "warning":     "#f59e0b",
        "heatmap_bg":  "#1a1a1a",
        "dark": True,
    }
    fig = plt.figure(figsize=(12, 7.2), dpi=110, facecolor=theme["bg_app"])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    # App bar
    panel(ax, 0, 0.93, 1, 0.07, theme["bg_panel"])
    title_size = 13 if lang == "zh" else 14
    text(ax, 0.015, 0.965, s["title"], color=theme["accent"],
         fontsize=title_size, fontweight="bold", va="center")
    # Current file (no decorative transport glyphs — keep app-bar clean)
    title_w = 0.21 if lang == "zh" else 0.13
    text(ax, title_w, 0.965, "✓", color=theme["success"], fontsize=12, va="center")
    text(ax, title_w + 0.015, 0.965, "test_Voice_EGG.wav",
         color=theme["text_sec"], fontsize=11, va="center")
    # top-right: lang toggle + settings/help/minimize
    text(ax, 0.86, 0.965, s["lang_toggle"], color=theme["text_sec"],
         fontsize=11, va="center")
    text(ax, 0.91, 0.965, "⚙", color=theme["text_sec"], fontsize=14, va="center")
    text(ax, 0.94, 0.965, "?", color=theme["text_sec"], fontsize=12, va="center")
    text(ax, 0.97, 0.965, "─", color=theme["text_sec"], fontsize=12, va="center")

    # Files (top track strip)
    panel(ax, 0, 0.78, 1, 0.15, theme["bg_panel"])
    text(ax, 0.013, 0.91, s["tracks_label"], color=theme["accent"],
         fontsize=10, fontweight="bold", va="center")

    tracks = [("01", "✓", "test_Voice_EGG.wav", "44.1k", "8.2s", "12,525", True),
              ("02", "○", "recording_2.wav",     "44.1k", "5.1s", "—",      False),
              ("03", "○", "recording_3.wav",     "44.1k", "6.7s", "—",      False)]
    for i, (idx, st, name, sr, dur, cells, active) in enumerate(tracks):
        y = 0.86 - i * 0.04
        bg = theme["bg_elev"] if active else theme["bg_panel"]
        panel(ax, 0.012, y - 0.018, 0.97, 0.034, bg)
        if active:
            panel(ax, 0.012, y - 0.018, 0.005, 0.034, theme["accent"])
        text(ax, 0.022, y, idx, color=theme["text_muted"], fontsize=9, va="center",
             family=["Consolas", "Cascadia Code"])
        c = theme["success"] if st == "✓" else theme["text_muted"]
        text(ax, 0.040, y, st, color=c, fontsize=11, va="center", fontweight="bold")
        text(ax, 0.060, y, name, color=theme["text_primary"], fontsize=10, va="center")
        if cells == "—":
            extra = "未分析" if lang == "zh" else "not analyzed"
            track_meta = f"{sr} Hz · {dur} · {extra}"
        else:
            track_meta = f"{sr} Hz · {dur} · {cells} {s['cells']}"
        text(ax, 0.30, y, track_meta,
             color=theme["text_sec"], fontsize=9, va="center")
        # mock waveform stripe
        rng = np.random.default_rng(i + 1)
        wave = np.abs(rng.normal(0, 0.5, 100))
        wax = fig.add_axes([0.55, (0.95 - 0.078 - i * 0.0432) - 0.005,
                            0.42, 0.030], zorder=10)
        wax.bar(np.arange(100), wave, color=theme["accent"] if active else theme["text_muted"],
                width=1.0, alpha=0.6 if active else 0.3)
        wax.set_xticks([]); wax.set_yticks([])
        wax.set_facecolor(theme["bg_app"])
        for sp in wax.spines.values(): sp.set_visible(False)

    # Metric selector
    panel(ax, 0, 0.73, 1, 0.05, theme["bg_panel"])
    text(ax, 0.015, 0.755, s["metric_label"], color=theme["accent"],
         fontsize=10, fontweight="bold", va="center")
    panel(ax, 0.07, 0.738, 0.10, 0.034, theme["bg_elev"], edge=theme["border"])
    text(ax, 0.12, 0.755, "CPP ▾", color=theme["text_primary"], fontsize=10,
         va="center", ha="center", fontweight="bold")
    text(ax, 0.20, 0.755, s["nav_hint"], color=theme["text_muted"],
         fontsize=9, va="center")

    # Canvas (heatmap left + inspector right)
    panel(ax, 0, 0.04, 0.72, 0.69, theme["bg_app"])
    panel(ax, 0.02, 0.10, 0.68, 0.61, "white", edge=theme["border"])
    heatmap_in(ax, fig, (0.05, 0.13, 0.62, 0.55), {**theme, "heatmap_bg": "white"})

    # Inspector
    panel(ax, 0.72, 0.04, 0.28, 0.69, theme["bg_panel"])
    text(ax, 0.74, 0.70, "CPP", color=theme["accent"],
         fontsize=22, fontweight="bold", va="center")
    text(ax, 0.74, 0.673, s["metric_full"],
         color=theme["text_sec"], fontsize=9, va="center")
    text(ax, 0.74, 0.650, s["metric_unit"],
         color=theme["text_muted"], fontsize=9, va="center")

    panel(ax, 0.74, 0.45, 0.24, 0.18, theme["bg_elev"])
    text(ax, 0.75, 0.605, s["clinical"], color=theme["accent"],
         fontsize=9, fontweight="bold", va="center")
    rows = [("≥ 14",  s["good"],   theme["success"]),
            ("10-14", s["normal"], theme["text_sec"]),
            ("6-10",  s["watch"],  theme["warning"]),
            ("< 6",   s["abnorm"], "#ef4444")]
    for i, (rng_v, lab, c) in enumerate(rows):
        y = 0.575 - i * 0.026
        text(ax, 0.75, y, rng_v, color=theme["text_primary"], fontsize=9,
             va="center", family=["Consolas", "Cascadia Code"])
        text(ax, 0.83, y, lab, color=c, fontsize=9, va="center", fontweight="bold")

    panel(ax, 0.74, 0.30, 0.24, 0.13, theme["bg_elev"])
    text(ax, 0.75, 0.410, s["current"], color=theme["accent"],
         fontsize=9, fontweight="bold", va="center")
    text(ax, 0.75, 0.375, "16.79", color=theme["accent_hi"],
         fontsize=24, fontweight="bold", va="center",
         family=["Consolas", "Cascadia Code"])
    text(ax, 0.92, 0.385, "dB", color=theme["text_muted"], fontsize=10, va="center")
    text(ax, 0.75, 0.335, s["good_marked"], color=theme["success"],
         fontsize=11, fontweight="bold", va="center")

    # Action buttons
    actions = [s["btn_excel"], s["btn_report"], s["btn_compare"]]
    for i, lab in enumerate(actions):
        y = 0.24 - i * 0.05
        panel(ax, 0.74, y, 0.24, 0.038, theme["bg_elev"], edge=theme["accent"])
        text(ax, 0.86, y + 0.019, lab, color=theme["accent"], fontsize=9,
             va="center", ha="center", fontweight="bold")

    # Toolbar
    panel(ax, 0, 0.04, 0.72, 0.05, theme["bg_panel"])
    tools = [s["tool_fit"], s["tool_note"], s["tool_reset"],
             s["tool_copy"], s["tool_save"]]
    x = 0.02
    for t in tools:
        panel(ax, x, 0.05, 0.07, 0.034, theme["bg_elev"], edge=theme["border"])
        text(ax, x + 0.035, 0.067, t, color=theme["text_primary"], fontsize=9,
             va="center", ha="center", fontweight="bold")
        x += 0.08

    # Status bar
    panel(ax, 0, 0, 1, 0.04, theme["bg_panel"])
    text(ax, 0.013, 0.02, s["status_prefix"],
         color=theme["text_muted"], fontsize=9, va="center")

    text(ax, 0.5, 0.998, s["subtitle"],
         color=theme["accent"], fontsize=11, fontweight="bold",
         va="top", ha="center")

    suffix = "_zh" if lang == "zh" else "_en"
    out = os.path.join(OUT, f"option_C_studio{suffix}.png")
    fig.savefig(out, dpi=110, facecolor=theme["bg_app"], edgecolor="none")
    plt.close(fig)
    print("wrote", out)


# ── option D: Academic — used as the EXPORTED REPORT template (zh/en) ─────
D_STRINGS = {
    "zh": {
        "title_zh":      "嗓音声学品质多维分析图谱",
        "subtitle":      "VoiceMap V1.0",
        "section_file":  "音频文件",
        "section_metric":"分析指标",
        "metric_full":   "▸ CPP — 倒谱峰显著度",
        "caption":       "图 1.   CPP 在 MIDI × SPL 网格上的 Voice Range Profile 热图",
        "section_stats": "统计摘要",
        "stats_labels":  ["均值", "标准差", "最小值", "最大值", "样本数"],
        "section_clinical":"临床参考范围",
        "good":          "良好",
        "normal":        "正常",
        "watch":         "关注",
        "abnorm":        "异常",
        "result_label":  "本次结果:",
        "result_status": "✓ 良好",
        "footer_left":   "嗓音声学品质多维分析图谱  V1.0  ·  © 2026 蔡寰宸  ·  huanchen.se@gmail.com",
        "footer_right":  "导出于  2026-05-06",
        "page_title":    "方案 D — 报告导出模板（中文）",
    },
    "en": {
        "title_zh":      "VoiceMap",
        "subtitle":      "Multi-dimensional Voice Acoustic Quality Analysis · V1.0",
        "section_file":  "File",
        "section_metric":"Metric",
        "metric_full":   "▸ CPP — Cepstral Peak Prominence",
        "caption":       "Figure 1.   Voice Range Profile heatmap of CPP across MIDI × SPL grid.",
        "section_stats": "Statistics",
        "stats_labels":  ["Mean", "Std", "Min", "Max", "n"],
        "section_clinical":"Clinical reference",
        "good":          "Good",
        "normal":        "Normal",
        "watch":         "Watch",
        "abnorm":        "Abnorm",
        "result_label":  "Result:",
        "result_status": "✓ Good",
        "footer_left":   "VoiceMap V1.0  ·  © 2026 Huanchen Cai  ·  huanchen.se@gmail.com",
        "footer_right":  "Generated  2026-05-06",
        "page_title":    "Option D — Report export template (English)",
    },
}


def render_option_d(lang="zh"):
    s = D_STRINGS[lang]
    theme = {
        "bg_app":      "#ffffff",
        "bg_panel":    "#ffffff",
        "bg_elev":     "#fafafa",
        "border":      "#e5e5e5",
        "border_strong":"#a3a3a3",
        "text_primary":"#1a1a1a",
        "text_sec":    "#525252",
        "text_muted":  "#737373",
        "accent":      "#1e3a5f",
        "success":     "#15803d",
        "warning":     "#a16207",
        "error":       "#991b1b",
        "heatmap_bg":  "#ffffff",
        "dark": False,
    }
    fig = plt.figure(figsize=(12, 7.2), dpi=110, facecolor=theme["bg_app"])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    # Title (no app bar — just text)
    text(ax, 0.5, 0.95, s["title_zh"],
         color=theme["text_primary"], fontsize=22, fontweight="bold",
         va="center", ha="center", family=["SimSun", "Times New Roman"])
    text(ax, 0.5, 0.91, s["subtitle"],
         color=theme["text_sec"], fontsize=11, va="center", ha="center",
         family=["SimSun", "Times New Roman"])
    # Subtle line
    ax.plot([0.18, 0.82], [0.885, 0.885], color=theme["border_strong"],
            lw=0.8, transform=ax.transAxes)

    # File header
    text(ax, 0.18, 0.85, s["section_file"],
         color=theme["text_muted"], fontsize=9, fontweight="bold", va="center")
    text(ax, 0.18, 0.825, "test_Voice_EGG.wav   ·   44,100 Hz   ·   8.2 s   ·   2 ch (Mic + EGG)",
         color=theme["text_primary"], fontsize=10, va="center",
         family=["Consolas", "Cascadia Code"])

    # Metric heading
    text(ax, 0.18, 0.78, s["section_metric"],
         color=theme["text_muted"], fontsize=9, fontweight="bold", va="center")
    text(ax, 0.18, 0.755, s["metric_full"],
         color=theme["text_primary"], fontsize=12, fontweight="bold", va="center")

    # Heatmap as a paper figure
    panel(ax, 0.20, 0.30, 0.60, 0.42, "white", edge=theme["border_strong"], lw=1.0)
    heatmap_in(ax, fig, (0.225, 0.325, 0.55, 0.37), theme)
    # Caption underneath
    text(ax, 0.5, 0.27, s["caption"],
          color=theme["text_sec"], fontsize=9, va="center", ha="center", style="italic",
          family=["SimSun", "Times New Roman"])

    # Statistics
    text(ax, 0.18, 0.22, s["section_stats"],
         color=theme["text_muted"], fontsize=9, fontweight="bold", va="center")
    stats = list(zip(s["stats_labels"],
                     ["16.79 dB", "3.21", " 8.04", "28.92", "12,525"]))
    x = 0.18
    for label, val in stats:
        text(ax, x, 0.195, label, color=theme["text_muted"], fontsize=9,
             va="center")
        text(ax, x, 0.170, val, color=theme["text_primary"], fontsize=12,
             fontweight="bold", va="center",
             family=["Consolas", "Cascadia Code"])
        x += 0.13

    # Clinical reference
    text(ax, 0.18, 0.125, s["section_clinical"],
         color=theme["text_muted"], fontsize=9, fontweight="bold", va="center")
    rows_ = [(s["good"],   "≥ 14",   theme["success"]),
             (s["normal"], "10–14",  theme["text_sec"]),
             (s["watch"],  "6–10",   theme["warning"]),
             (s["abnorm"], "< 6",    theme["error"])]
    x = 0.18
    for label, rng_v, c in rows_:
        text(ax, x, 0.100, label,
             color=c, fontsize=10, va="center", fontweight="bold")
        text(ax, x, 0.078, rng_v, color=theme["text_primary"], fontsize=9,
             va="center", family=["Consolas", "Cascadia Code"])
        x += 0.09

    # Result row — split so Chinese label stays in Chinese-capable font and
    # only the numeric "16.79 dB" sits in monospace.
    text(ax, 0.62, 0.085, s["result_label"],
         color=theme["success"], fontsize=12, fontweight="bold", va="center")
    text(ax, 0.71, 0.085, "16.79 dB",
         color=theme["success"], fontsize=12, fontweight="bold", va="center",
         family=["Consolas", "Cascadia Code"])
    text(ax, 0.81, 0.085, s["result_status"],
         color=theme["success"], fontsize=12, fontweight="bold", va="center")

    # Footer
    ax.plot([0.18, 0.82], [0.04, 0.04], color=theme["border_strong"],
            lw=0.5, transform=ax.transAxes)
    text(ax, 0.18, 0.025, s["footer_left"],
          color=theme["text_muted"], fontsize=9, va="center",
          family=["SimSun", "Times New Roman"])
    # Footer right may contain Chinese (导出于) — don't force monospace.
    text(ax, 0.82, 0.025, s["footer_right"],
         color=theme["text_muted"], fontsize=9, va="center", ha="right")

    text(ax, 0.5, 0.998, s["page_title"],
         color=theme["accent"], fontsize=11, fontweight="bold",
         va="top", ha="center")

    suffix = "_zh" if lang == "zh" else "_en"
    out = os.path.join(OUT, f"option_D_report{suffix}.png")
    fig.savefig(out, dpi=110, facecolor=theme["bg_app"], edgecolor="none")
    plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    # Decision: GUI = Option C (Studio, dark + amber).  Render zh + en.
    # Decision: Report exports use Option D layout. Render zh + en.
    # Options A and B kept for reference / comparison.
    render_option_a()
    render_option_b()
    render_option_c(lang="zh")
    render_option_c(lang="en")
    render_option_d(lang="zh")
    render_option_d(lang="en")
    print("\nAll mockups written to:", OUT)
