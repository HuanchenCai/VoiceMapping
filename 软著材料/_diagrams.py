# -*- coding: utf-8 -*-
"""设计说明书附图生成器。

产物：
  docs/架构图.png        —— 6 层分层架构（GUI / 入口 / 编排 / 计算 / IO / 基础设施）

后续可以在这里追加更多附图（数据流、模块依赖等）。
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

matplotlib.rcParams["font.family"] = [
    "Microsoft YaHei", "SimSun", "Segoe UI",
]
matplotlib.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)


# ── 颜色 token（与 voicemap/gui/theme.py 保持视觉风格一致） ───────────────
ACCENT       = "#f59e0b"      # amber 强调色
BG_DARK      = "#1a1a1a"      # 深色面板
TEXT_LIGHT   = "#f5f5f5"
TEXT_DIM     = "#a3a3a3"
LAYER_BG = [                  # 自顶向下 6 层底色（cool → warm 渐变）
    "#1e3a5f",                # GUI 层（蓝）
    "#2a4a6f",                # 入口
    "#3a5a7f",                # 编排
    "#4a6a8f",                # 计算
    "#5a4a3f",                # 输出（暖色）
    "#3a3a3a",                # 基础设施（中性深灰）
]


def build_architecture_diagram(dst: Path) -> None:
    """6 层堆叠分层图，每层右侧标注职责。"""
    layers = [
        ("GUI 层（voicemap.gui.*）",
         "用户交互",
         "app.py · theme.py · widgets.py · dialogs.py · modern_menu.py"),
        ("入口层",
         "CLI / 主窗口启动",
         "cli.py · main.py"),
        ("分析编排",
         "主流程编排",
         "analyzer.py"),
        ("参数计算",
         "20+ 个 calculator 类",
         "metrics.py · metrics_registry.py"),
        ("I/O & 输出",
         "落盘 / 渲染 / 报告",
         "csv_writer.py · plotter.py · plot_overlay.py · excel_export.py · report.py"),
        ("基础设施",
         "配置 / 日志 / 多语言 / 版本",
         "config.py · logger.py · i18n.py · __version__.py"),
    ]

    fig_w, fig_h = 9.5, 6.0
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, len(layers))
    ax.set_axis_off()
    fig.patch.set_facecolor("white")

    # 每层一个圆角矩形
    layer_h = 0.92
    for i, (title, role, modules) in enumerate(layers):
        y = len(layers) - 1 - i        # 顶层在最上
        bg = LAYER_BG[i]
        box = FancyBboxPatch(
            (0.2, y + 0.04), 9.6, layer_h,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            linewidth=1.2, edgecolor=ACCENT, facecolor=bg)
        ax.add_patch(box)

        # 标题（白色粗体，左对齐）
        ax.text(0.45, y + 0.62, title,
                fontsize=12.5, fontweight="bold",
                color=TEXT_LIGHT, va="center", ha="left")
        # 职责描述（amber，标题右侧）
        ax.text(0.45, y + 0.30, role,
                fontsize=10, color=ACCENT, va="center", ha="left",
                fontstyle="italic")
        # 模块列表（右侧 dim 文字）
        ax.text(9.55, y + 0.46, modules,
                fontsize=8.2, color=TEXT_DIM, va="center", ha="right",
                family="Consolas")

    # 顶部标题
    fig.suptitle("VoiceMap 分层架构",
                 fontsize=14, fontweight="bold", y=0.98, color=BG_DARK)
    # 底部注脚
    fig.text(0.5, 0.02,
             "自顶向下：用户交互 → 业务逻辑 → 基础设施。每层只依赖下方层级，无循环依赖。",
             ha="center", fontsize=9, color=TEXT_DIM, style="italic")

    plt.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.06)
    fig.savefig(dst, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  wrote {dst.relative_to(ROOT)}")


def main():
    build_architecture_diagram(DOCS / "架构图.png")


if __name__ == "__main__":
    main()
