#!/usr/bin/env python3
"""FonaDyn — 极简两栏 GUI：拖入 .wav → 自动分析 → 右侧嵌入 voice map，下拉切换 metric。"""

import os
import sys
import queue
import logging
import threading
import traceback
import subprocess
from pathlib import Path

# ── Windows 高 DPI：必须在任何 Tk/matplotlib 初始化之前声明 ──
if sys.platform.startswith("win"):
    try:
        from ctypes import windll
        # PROCESS_PER_MONITOR_DPI_AWARE = 2, PROCESS_SYSTEM_DPI_AWARE = 1
        try:
            windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import tkinter as tk
from tkinter import ttk, filedialog

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "src"))

from config import DEFAULT_CONFIG, VoiceMapConfig  # noqa: E402
from logger import setup_logger                     # noqa: E402
from plotter import draw_vrp_on_ax, METRIC_CFG, _SKIP_ZERO_METRICS  # noqa: E402

# 可选的原生拖拽
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _TkBase, _DND_OK = TkinterDnD.Tk, True
except Exception:
    _TkBase, _DND_OK = tk.Tk, False
    DND_FILES = None  # type: ignore

# ─── 主题 ─────────────────────────────────────────────────────────────────────
BG        = "#0f1419"
PANEL     = "#162029"
PANEL_HI  = "#1e2a36"
BORDER    = "#243141"
TEXT      = "#e6edf3"
MUTED     = "#7d8590"
ACCENT    = "#00d9ff"
ACCENT_HI = "#4de6ff"
OK        = "#3fb950"
WARN      = "#d29922"
ERR       = "#f85149"

# Fonts. 用 Microsoft YaHei UI 作为主字体 —— Windows 自带，汉字与西文
# 均有专门字形，不会出现 Segoe UI 为汉字回落到别的字体导致的"某些字看
# 起来像加粗、某些不像"视觉不一致。
FONT_UI    = ("Microsoft YaHei UI", 10)
FONT_UI_B  = ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 16, "bold")
FONT_SUB   = ("Microsoft YaHei UI", 10)
FONT_DROP  = ("Microsoft YaHei UI", 13, "bold")
FONT_MONO  = ("Consolas", 9)

# Metric 分类。下拉按这个顺序分段显示，每段一个禁用的标题；
# 节与节之间 ttk Menu 画分隔线。未来新指标按功能塞进对应的 section。
_METRIC_SECTIONS: list = [
    ("声学 · Acoustic", [
        "Clarity", "CPP", "CPPS", "SpecBal", "Crest", "Entropy",
        "Jitter", "JitterRAP", "JitterPPQ5",
        "Shimmer", "ShimmerDB",
        "ShimmerAPQ3", "ShimmerAPQ5", "ShimmerAPQ11",
        "HNR", "NHR",
        "PPE", "ZCR",
    ]),
    ("EGG · 电声门图", [
        "Qcontact", "Icontact", "dEGGmax", "HRFegg",
        "OQ", "SPQ", "CIQ",
    ]),
    ("唱歌特异性 · Singing-specific", [
        "VibratoRate", "VibratoExtent",
        "F1", "F2", "F3", "SingersFormant",
        "H1H2", "H1H3",
    ]),
    ("聚类 · Cluster / cPhon", [
        "maxCluster", "Cluster 1", "Cluster 2", "Cluster 3", "Cluster 4", "Cluster 5",
        "maxCPhon",   "cPhon 1",   "cPhon 2",   "cPhon 3",   "cPhon 4",   "cPhon 5",
    ]),
    ("密度 · Density", ["Total"]),
]
_DEFAULT_METRIC_CHAIN = ["CPP", "Clarity", "SpecBal", "Crest"]


# ─── 设置对话框 ──────────────────────────────────────────────────────────────
class SettingsDialog(tk.Toplevel):
    """所有分析/输出相关的可配置项都在这里。现在只有 Clarity 阈值和输出目录，
    随着新 metric（clustering / jitter / formants 等）加进来会继续扩展。"""

    def __init__(self, app: "FonaDynApp"):
        super().__init__(app)
        self.app = app
        self.transient(app)
        self.title("设置")
        self.configure(bg=PANEL)
        self.resizable(False, False)

        pad = tk.Frame(self, bg=PANEL)
        pad.pack(padx=24, pady=20)

        # ─ 分析参数 ─
        tk.Label(pad, text="分析参数", bg=PANEL, fg=ACCENT, font=FONT_UI_B
                 ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        tk.Label(pad, text="Clarity 阈值", bg=PANEL, fg=TEXT, font=FONT_UI
                 ).grid(row=1, column=0, sticky="w", pady=3)
        wrap = tk.Frame(pad, bg=PANEL)
        wrap.grid(row=1, column=1, sticky="w", padx=(18, 0), pady=3)
        ttk.Spinbox(wrap, from_=0.80, to=1.00, increment=0.01,
                    textvariable=app.clarity_var,
                    format="%.2f", width=8, font=FONT_UI,
                    ).pack(side="left")
        tk.Label(wrap, text="(0.80 – 1.00)", bg=PANEL, fg=MUTED,
                 font=FONT_UI).pack(side="left", padx=(8, 0))
        # 兼容 update_clarity_label 调用；没有单独的数字显示了，做成 no-op
        self.clarity_lbl = None

        # ─ 聚类（下次分析生效） ─
        tk.Label(pad, text="聚类  (下次分析生效)", bg=PANEL, fg=ACCENT, font=FONT_UI_B
                 ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(18, 6))

        tk.Label(pad, text="簇数 k", bg=PANEL, fg=TEXT, font=FONT_UI
                 ).grid(row=3, column=0, sticky="w", pady=3)
        ttk.Spinbox(pad, from_=2, to=10, textvariable=app.cluster_k_var,
                    width=6).grid(row=3, column=1, sticky="w", padx=(18, 0), pady=3)

        tk.Label(pad, text="谐波数 n", bg=PANEL, fg=TEXT, font=FONT_UI
                 ).grid(row=4, column=0, sticky="w", pady=3)
        ttk.Spinbox(pad, from_=3, to=20, textvariable=app.cluster_nharm_var,
                    width=6).grid(row=4, column=1, sticky="w", padx=(18, 0), pady=3)

        # ─ 输出 ─
        tk.Label(pad, text="输出", bg=PANEL, fg=ACCENT, font=FONT_UI_B
                 ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(18, 6))

        tk.Label(pad, text="目录", bg=PANEL, fg=TEXT, font=FONT_UI
                 ).grid(row=6, column=0, sticky="w", pady=3)
        out_row = tk.Frame(pad, bg=PANEL)
        out_row.grid(row=6, column=1, sticky="ew", padx=(18, 0), pady=3)
        ttk.Entry(out_row, textvariable=app.output_dir_var, width=32
                  ).pack(side="left")
        ttk.Button(out_row, text="…", style="Ghost.TButton",
                   command=app._pick_output_dir, width=3
                   ).pack(side="left", padx=(6, 0))

        # 自动导出 PNG 开关
        tk.Label(pad, text="自动导出 PNG", bg=PANEL, fg=TEXT, font=FONT_UI
                 ).grid(row=7, column=0, sticky="w", pady=3)
        exp_row = tk.Frame(pad, bg=PANEL)
        exp_row.grid(row=7, column=1, sticky="w", padx=(18, 0), pady=3)
        ttk.Checkbutton(exp_row, variable=app.export_plots_var,
                        text="分析完成后输出到 plots/").pack(anchor="w")
        layout_row = tk.Frame(exp_row, bg=PANEL)
        layout_row.pack(anchor="w", pady=(4, 0))
        ttk.Radiobutton(layout_row, variable=app.plot_layout_var,
                        value="per-metric", text="每 metric 一张图"
                        ).pack(side="left")
        ttk.Radiobutton(layout_row, variable=app.plot_layout_var,
                        value="combined", text="合并为一张总览"
                        ).pack(side="left", padx=(12, 0))

        # ─ 关闭 ─
        btn_row = tk.Frame(pad, bg=PANEL)
        btn_row.grid(row=8, column=0, columnspan=2, sticky="e", pady=(22, 0))
        ttk.Button(btn_row, text="完成", style="Accent.TButton",
                   command=self.destroy).pack()

        # 居中到父窗口
        self.update_idletasks()
        try:
            px, py = app.winfo_rootx(), app.winfo_rooty()
            pw, ph = app.winfo_width(), app.winfo_height()
            ww, wh = self.winfo_width(), self.winfo_height()
            self.geometry(f"+{px + (pw - ww)//2}+{py + (ph - wh)//2}")
        except Exception:
            pass

    def update_clarity_label(self):
        """No-op now that clarity is a Spinbox bound to clarity_var directly.
        Kept for API compatibility — callers don't need to know."""
        return


# ─── 对比对话框 ──────────────────────────────────────────────────────────────
class CompareDialog(tk.Toplevel):
    """Load two VRP CSVs, pick a metric, see A | B | A-B."""

    def __init__(self, app: "FonaDynApp"):
        super().__init__(app)
        self.app = app
        self.transient(app)
        self.title("对比 2 段录音 · Voice Map diff")
        self.configure(bg=PANEL)
        self.geometry("1300x560")

        # File pickers (top bar)
        bar = tk.Frame(self, bg=PANEL)
        bar.pack(fill="x", padx=12, pady=(10, 4))

        self.csv_a = tk.StringVar(value="")
        self.csv_b = tk.StringVar(value="")
        self._df_a = None
        self._df_b = None

        for label, var, slot in (("A", self.csv_a, "a"), ("B", self.csv_b, "b")):
            f = tk.Frame(bar, bg=PANEL)
            f.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(f, text=label, bg=PANEL, fg=ACCENT,
                     font=FONT_UI_B, width=2).pack(side="left")
            ttk.Entry(f, textvariable=var).pack(side="left", fill="x", expand=True)
            ttk.Button(f, text="…", style="Ghost.TButton", width=3,
                       command=lambda s=slot: self._pick_csv(s)).pack(side="left", padx=(4, 0))

        # Metric + render controls
        ctrl = tk.Frame(self, bg=PANEL)
        ctrl.pack(fill="x", padx=12, pady=(4, 8))
        tk.Label(ctrl, text="Metric:", bg=PANEL, fg=MUTED, font=FONT_UI).pack(side="left")
        self.metric = tk.StringVar(value="CPP")
        self.metric_combo = ttk.Combobox(ctrl, textvariable=self.metric,
                                          state="readonly", width=18, font=FONT_UI,
                                          values=["CPP"])
        self.metric_combo.pack(side="left", padx=(6, 0))
        self.metric_combo.bind("<<ComboboxSelected>>", lambda _e: self._render())
        ttk.Button(ctrl, text="刷新绘图", style="Accent.TButton",
                   command=self._render).pack(side="left", padx=(12, 0))
        ttk.Button(ctrl, text="导出 PNG", style="Ghost.TButton",
                   command=self._save_png).pack(side="left", padx=(6, 0))

        # Canvas
        self._fig = Figure(figsize=(14, 4.5), dpi=110, facecolor=PANEL)
        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        cw = self._canvas.get_tk_widget()
        cw.configure(bg=PANEL, highlightthickness=0, bd=0)
        cw.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._show_msg("加载 A 和 B 的 VRP CSV")

    def _show_msg(self, msg: str):
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        ax.set_facecolor(PANEL)
        ax.text(0.5, 0.5, msg, ha="center", va="center", color=MUTED, fontsize=13,
                transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values(): s.set_visible(False)
        self._canvas.draw_idle()

    def _pick_csv(self, slot: str):
        path = filedialog.askopenfilename(
            parent=self, title=f"选 {slot.upper()} 的 VRP CSV",
            filetypes=[("CSV", "*.csv")],
            initialdir=str(Path(self.app.output_dir_var.get())))
        if not path:
            return
        try:
            import pandas as _pd
            df = _pd.read_csv(path, sep=";")
        except Exception as e:  # noqa: BLE001
            self._show_msg(f"读取失败：{e}")
            return
        if slot == "a":
            self.csv_a.set(path); self._df_a = df
        else:
            self.csv_b.set(path); self._df_b = df
        # Update metric dropdown to intersection of both loaded DFs
        if self._df_a is not None and self._df_b is not None:
            common = [c for c in self._df_a.columns
                      if c in self._df_b.columns and c not in ("MIDI", "dB")]
            self.metric_combo.configure(values=common)
            if self.metric.get() not in common and common:
                self.metric.set("CPP" if "CPP" in common else common[0])
            self._render()

    def _render(self):
        if self._df_a is None or self._df_b is None:
            self._show_msg("还没加载两个 CSV")
            return
        from plotter import draw_vrp_comparison
        ok = draw_vrp_comparison(
            self._df_a, self._df_b, self.metric.get(), self._fig,
            label_a=Path(self.csv_a.get()).stem,
            label_b=Path(self.csv_b.get()).stem)
        if not ok:
            self._show_msg(f"{self.metric.get()} 在 A/B 中都为空")
            return
        self._canvas.draw_idle()

    def _save_png(self):
        if self._df_a is None or self._df_b is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="保存对比 PNG",
            defaultextension=".png", filetypes=[("PNG", "*.png")],
            initialfile=f"{Path(self.csv_a.get()).stem}_vs_{Path(self.csv_b.get()).stem}_{self.metric.get()}.png")
        if not path:
            return
        try:
            self._fig.savefig(path, dpi=130, bbox_inches="tight",
                               facecolor=self._fig.get_facecolor())
            self.app._append_log("META", f"✓ 对比图已保存：{path}")
        except Exception as e:  # noqa: BLE001
            self.app._append_log("ERROR", f"保存失败：{e}")


# ─── 分析进度对话框 ──────────────────────────────────────────────────────────
class ProgressDialog(tk.Toplevel):
    """模态小窗：分析进行时显示文件名 + 当前阶段 + 不确定进度条。"""
    def __init__(self, parent: tk.Misc, filename: str):
        super().__init__(parent)
        self.transient(parent)
        self.title("分析进行中")
        self.configure(bg=PANEL)
        self.resizable(False, False)
        # 模态：点不到主窗口（也包括拖放区）
        try:
            self.grab_set()
        except tk.TclError:
            pass
        # 拦截关闭按钮
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        pad = tk.Frame(self, bg=PANEL)
        pad.pack(padx=28, pady=22)

        tk.Label(pad, text="正在分析 · Voice Range Profile",
                 bg=PANEL, fg=ACCENT, font=("Segoe UI Semibold", 13)
                 ).pack(anchor="w")
        tk.Label(pad, text=filename, bg=PANEL, fg=TEXT,
                 font=("Consolas", 10), wraplength=360, justify="left"
                 ).pack(anchor="w", pady=(4, 10))

        # Determinate bar driven by the analyzer's progress_cb.
        # maximum gets set once we know total stages (first callback).
        self._pb = ttk.Progressbar(pad, mode="determinate",
                                   length=360,
                                   style="Accent.Horizontal.TProgressbar",
                                   maximum=1.0)
        self._pb.pack(fill="x")
        # Auxiliary indeterminate animation is disabled — progress now
        # comes from explicit stage advances.

        step_row = tk.Frame(pad, bg=PANEL)
        step_row.pack(fill="x", pady=(8, 0))
        self._step_lbl = tk.Label(step_row, text="—",
                                   bg=PANEL, fg=ACCENT, font=FONT_UI_B)
        self._step_lbl.pack(side="left")
        self._status = tk.Label(step_row, text="准备中…",
                                 bg=PANEL, fg=TEXT, font=FONT_UI,
                                 anchor="w", wraplength=320, justify="left")
        self._status.pack(side="left", padx=(10, 0))

        # 居中到父窗口
        self.update_idletasks()
        try:
            px = parent.winfo_rootx(); py = parent.winfo_rooty()
            pw = parent.winfo_width(); ph = parent.winfo_height()
            ww = self.winfo_width();   wh = self.winfo_height()
            self.geometry(f"+{px + (pw - ww)//2}+{py + (ph - wh)//2}")
        except Exception:
            pass

    def set_status(self, text: str):
        # Free-form log line tail; secondary info shown next to step counter.
        try:
            self._status.configure(text=text)
        except tk.TclError:
            pass

    def set_progress(self, step: int, total: int, label: str):
        """Update the determinate bar + stage counter + description."""
        try:
            if total > 0:
                self._pb.configure(maximum=total, value=step)
            self._step_lbl.configure(text=f"[{step}/{total}]")
            self._status.configure(text=label)
        except tk.TclError:
            pass

    def close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


# ─── 日志桥接 ─────────────────────────────────────────────────────────────────
class QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q

    def emit(self, record):
        try:
            self.q.put(("log", record.levelname, self.format(record)))
        except Exception:
            pass


# ─── 主应用 ──────────────────────────────────────────────────────────────────
class FonaDynApp(_TkBase):
    def __init__(self):
        super().__init__()
        dnd_hint = "" if _DND_OK else "（未安装 tkinterdnd2，拖放已降级为点击）"
        self.title(f"Voice Mapping {dnd_hint}".strip())
        self.geometry("1200x720")
        self.minsize(1000, 600)
        self.configure(bg=BG)

        self.output_dir_var = tk.StringVar(value=str(_HERE / DEFAULT_CONFIG.output_dir))
        self.clarity_var    = tk.DoubleVar(value=DEFAULT_CONFIG.clarity_threshold)
        # clarity 值变化 → 同步到设置对话框 + 防抖后重绘 voice map
        self.clarity_var.trace_add("write", self._on_clarity_var_changed)
        # 聚类参数（下次分析生效）
        self.cluster_k_var    = tk.IntVar(value=5)
        self.cluster_nharm_var = tk.IntVar(value=10)
        # PNG 导出：默认关（GUI 自己渲染，不需要存盘），开启时用哪种布局
        self.export_plots_var = tk.BooleanVar(value=False)
        self.plot_layout_var  = tk.StringVar(value="per-metric")  # or "combined"
        self.metric_var     = tk.StringVar(value="")
        self.csv_path_var   = tk.StringVar(value="—")

        self.audio_path: Path | None = None
        self.last_csv:   str | None  = None
        self._last_df                = None   # pd.DataFrame 或 None（含所有分析时 clarity>=cfg 的 cell）
        self._analysis_clarity       = float(DEFAULT_CONFIG.clarity_threshold)
        self._worker: threading.Thread | None = None
        self._msg_q:  queue.Queue = queue.Queue()
        self._log_count = 0
        self._clarity_render_after: str | None = None  # clarity 滑动防抖句柄
        self._showing_placeholder = True   # 当前是否在显示占位图（resize 时会重绘）
        self._progress_dialog = None       # 分析进行时的模态对话框
        self._settings_dialog = None       # 设置对话框（单例）
        self._last_analyzer = None         # 上次分析用的 VoiceMapAnalyzer（保存 centroids 用）
        self._loaded_centroids = None      # 预加载的 EGG centroid 数组（跨录音一致标签）
        self._loaded_centroids_path = None

        # 高 DPI 下让 Tk 按物理像素缩放，而不是走老式位图放大
        try:
            dpi = self.winfo_fpixels("1i")  # 96 在 100% 缩放下
            self.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            pass

        # 统一所有 Tk 默认字体为一套（中文 + 英文同一家族，不再漂移）
        try:
            import tkinter.font as tkfont
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                          "TkCaptionFont", "TkHeadingFont",
                          "TkTooltipFont", "TkIconFont", "TkSmallCaptionFont"):
                try:
                    tkfont.nametofont(name).configure(
                        family="Microsoft YaHei UI", size=10)
                except tk.TclError:
                    pass
            tkfont.nametofont("TkFixedFont").configure(
                family="Consolas", size=9)
        except Exception:
            pass

        # 菜单颜色也走 option DB，值必须是字符串；字体直接用已经
        # configure 过的 TkMenuFont 命名字体（不要传 Python 元组，option
        # database 会把 ("Microsoft YaHei UI", 10) 存成字面量字符串，
        # Tcl 解析不了就回退到系统字体，和我们自己画的字叠在一起就出
        # "幻影"）。
        self.option_add("*Menu.background",       PANEL_HI)
        self.option_add("*Menu.foreground",       TEXT)
        self.option_add("*Menu.activeBackground", ACCENT)
        self.option_add("*Menu.activeForeground", BG)

        self._init_style()
        self._build_ui()
        self._init_logging()
        self._register_dnd()
        self._bind_global_keys()

        # 延迟到 Tk 完成首次几何布局后再画占位。配合下方 canvas 的
        # <Configure> add="+" 绑定，matplotlib 自己的 resize handler 能正常跑，
        # figure 尺寸会自动同步到 widget，占位文字稳稳居中。
        self.after(200, self._show_placeholder)

        self.after(80, self._drain_queue)

        self.update_idletasks()
        x = (self.winfo_screenwidth()  - self.winfo_width())  // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    # ── 样式 ──
    def _init_style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass

        s.configure("TFrame", background=BG)
        s.configure("Panel.TFrame", background=PANEL)

        s.configure("TLabel",        background=BG,    foreground=TEXT, font=FONT_UI)
        s.configure("Panel.TLabel",  background=PANEL, foreground=TEXT, font=FONT_UI)
        s.configure("Muted.TLabel",  background=PANEL, foreground=MUTED, font=FONT_UI)
        s.configure("Title.TLabel",  background=BG,    foreground=TEXT, font=FONT_TITLE)
        s.configure("Accent.TLabel", background=PANEL, foreground=ACCENT, font=FONT_UI_B)

        s.configure("TEntry",
                    fieldbackground=PANEL_HI, foreground=TEXT,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    insertcolor=TEXT)
        s.map("TEntry",
              bordercolor=[("focus", ACCENT)],
              lightcolor=[("focus", ACCENT)],
              darkcolor=[("focus", ACCENT)])

        # Spinbox with dark fill, accent arrows, accent-bordered focus
        s.configure("TSpinbox",
                    fieldbackground=PANEL_HI, background=PANEL_HI,
                    foreground=TEXT,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    arrowcolor=ACCENT, arrowsize=13,
                    insertcolor=TEXT, padding=(6, 3))
        s.map("TSpinbox",
              fieldbackground=[("readonly", PANEL_HI), ("disabled", PANEL)],
              foreground=[("disabled", MUTED)],
              bordercolor=[("focus", ACCENT)],
              lightcolor=[("focus", ACCENT)],
              darkcolor=[("focus", ACCENT)],
              arrowcolor=[("active", ACCENT_HI), ("disabled", MUTED)])

        # Checkbutton: hollow indicator box filled with accent when on
        s.configure("TCheckbutton",
                    background=PANEL, foreground=TEXT,
                    focuscolor=PANEL, padding=(2, 2),
                    indicatorbackground=PANEL_HI,
                    indicatorforeground=ACCENT)
        s.map("TCheckbutton",
              background=[("active", PANEL)],
              indicatorbackground=[("selected", ACCENT),
                                   ("!selected", PANEL_HI)])

        # Radiobutton: same treatment
        s.configure("TRadiobutton",
                    background=PANEL, foreground=TEXT,
                    focuscolor=PANEL, padding=(2, 2),
                    indicatorbackground=PANEL_HI,
                    indicatorforeground=ACCENT)
        s.map("TRadiobutton",
              background=[("active", PANEL)],
              indicatorbackground=[("selected", ACCENT),
                                   ("!selected", PANEL_HI)])

        s.configure("TCombobox",
                    fieldbackground=PANEL_HI, foreground=TEXT,
                    background=PANEL_HI, bordercolor=BORDER,
                    arrowcolor=ACCENT, lightcolor=BORDER, darkcolor=BORDER)
        s.map("TCombobox",
              fieldbackground=[("readonly", PANEL_HI)],
              foreground=[("readonly", TEXT)])
        # 下拉列表外观
        self.option_add("*TCombobox*Listbox*Background", PANEL_HI)
        self.option_add("*TCombobox*Listbox*Foreground", TEXT)
        self.option_add("*TCombobox*Listbox*selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox*selectForeground", BG)
        self.option_add("*TCombobox*Listbox*Font", FONT_UI)

        s.configure("Accent.Horizontal.TProgressbar",
                    troughcolor=PANEL_HI, background=ACCENT,
                    bordercolor=PANEL_HI, lightcolor=ACCENT, darkcolor=ACCENT,
                    thickness=8)
        s.configure("Horizontal.TScale", background=PANEL, troughcolor=PANEL_HI)
        s.map("Horizontal.TScale", background=[("active", PANEL)])

        s.configure("Accent.TButton",
                    background=ACCENT, foreground=BG,
                    font=FONT_UI_B, borderwidth=0, padding=(10, 6))
        s.map("Accent.TButton",
              background=[("active", ACCENT_HI), ("disabled", "#2a3340")],
              foreground=[("disabled", MUTED)])
        s.configure("Ghost.TButton",
                    background=PANEL_HI, foreground=TEXT,
                    font=FONT_UI, borderwidth=0, padding=(8, 4))
        s.map("Ghost.TButton",
              background=[("active", BORDER), ("disabled", PANEL)],
              foreground=[("disabled", MUTED)])

        s.configure("Metric.TMenubutton",
                    background=PANEL_HI, foreground=TEXT,
                    font=FONT_UI, borderwidth=0, padding=(10, 4),
                    arrowcolor=ACCENT)
        s.map("Metric.TMenubutton",
              background=[("active", BORDER), ("disabled", PANEL)],
              foreground=[("disabled", MUTED)])

    # ── 布局 ──
    def _build_ui(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=14)

        self._build_header(outer)
        self._build_top_bar(outer)

        paned = ttk.PanedWindow(outer, orient="horizontal")
        paned.pack(fill="both", expand=True, pady=(10, 0))

        self.left = tk.Frame(paned, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        self.right = tk.Frame(paned, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        paned.add(self.left, weight=0)
        paned.add(self.right, weight=1)
        # sash 初始位置
        self.after(0, lambda: paned.sashpos(0, 320))

        self._build_left_panel(self.left)
        self._build_right_panel(self.right)

    def _build_header(self, parent):
        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x", pady=(0, 8))
        tk.Label(head, text="Voice Mapping",
                 bg=BG, fg=TEXT, font=FONT_TITLE).pack(side="left")
        self.status_dot = tk.Label(head, text="●", bg=BG, fg=MUTED, font=("Segoe UI", 12))
        self.status_dot.pack(side="right", padx=(0, 4))
        self.status_lbl = tk.Label(head, text="就绪", bg=BG, fg=MUTED, font=FONT_SUB)
        self.status_lbl.pack(side="right")

    def _build_top_bar(self, parent):
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x")

        # 大拖放区
        self.drop_zone = tk.Frame(bar, bg=PANEL_HI,
                                  highlightthickness=2, highlightbackground=BORDER,
                                  highlightcolor=ACCENT, cursor="hand2")
        self.drop_zone.pack(side="left", fill="x", expand=True)

        inner = tk.Frame(self.drop_zone, bg=PANEL_HI)
        inner.pack(fill="x", padx=18, pady=14)
        hint = "拖入 .wav 文件  /  点击浏览" if _DND_OK else "点击浏览（安装 tkinterdnd2 可启用拖拽）"
        self.drop_label = tk.Label(inner, text=hint, bg=PANEL_HI, fg=TEXT, font=FONT_DROP)
        self.drop_label.pack(anchor="w")
        self.drop_sub = tk.Label(inner,
                                 text="立体声 WAV · 通道 1 = 麦克风   通道 2 = EGG",
                                 bg=PANEL_HI, fg=MUTED, font=FONT_UI)
        self.drop_sub.pack(anchor="w")

        for w in (self.drop_zone, inner, self.drop_label, self.drop_sub):
            w.bind("<Button-1>", lambda _e: self._pick_audio())
            w.bind("<Enter>",    lambda _e: self.drop_zone.config(highlightbackground=ACCENT))
            w.bind("<Leave>",    lambda _e: self.drop_zone.config(highlightbackground=BORDER))

        # Metric 按钮 + 分类菜单（组合框没有原生节分隔，改用 Menubutton）
        side = tk.Frame(bar, bg=BG)
        side.pack(side="right", padx=(14, 0))
        tk.Label(side, text="Metric", bg=BG, fg=MUTED, font=FONT_UI).pack(anchor="w")
        self.metric_btn = ttk.Menubutton(side, textvariable=self.metric_var,
                                          style="Metric.TMenubutton", width=18)
        self.metric_btn.pack()
        # 用字符串 "TkMenuFont" 引用已经 configure 过的命名字体。
        # 传 Python 元组 ("Microsoft YaHei UI", 10) 看似能工作但实际上
        # Tk 会为每个 Menu 创建一个匿名字体对象，加上菜单本身的默认
        # 字体，两层字形叠加就产生视觉上的 "幻影"。
        self.metric_menu = tk.Menu(self.metric_btn, tearoff=0,
                                    bg=PANEL_HI, fg=TEXT,
                                    activebackground=ACCENT, activeforeground=BG,
                                    font="TkMenuFont", bd=0)
        self.metric_btn["menu"] = self.metric_menu
        self.metric_btn.state(["disabled"])
        # metric_var 的变化 = 菜单里点击 or 键盘方向键触发 → 自动重绘
        self.metric_var.trace_add("write", self._on_metric_change)

    def _build_left_panel(self, parent):
        pad = tk.Frame(parent, bg=PANEL)
        pad.pack(fill="both", expand=True, padx=14, pady=14)

        # 设置入口（Clarity 阈值 / 输出目录 等都在对话框里）
        ttk.Button(pad, text="⚙  设置", style="Ghost.TButton",
                   command=self._open_settings).pack(fill="x", pady=(0, 14))

        # CSV 结果
        tk.Label(pad, text="最新 CSV", bg=PANEL, fg=ACCENT, font=FONT_UI_B).pack(anchor="w")
        self.csv_lbl = tk.Label(pad, textvariable=self.csv_path_var,
                                bg=PANEL, fg=MUTED, font=FONT_MONO,
                                wraplength=280, justify="left", anchor="w")
        self.csv_lbl.pack(fill="x", pady=(4, 6))

        btn_row = tk.Frame(pad, bg=PANEL)
        btn_row.pack(fill="x", pady=(0, 12))
        self.open_csv_btn = ttk.Button(btn_row, text="打开 CSV", style="Ghost.TButton",
                                       command=self._open_csv)
        self.open_csv_btn.pack(side="left")
        self.open_csv_btn.state(["disabled"])
        self.open_plots_btn = ttk.Button(btn_row, text="打开输出目录", style="Ghost.TButton",
                                         command=self._open_output_dir)
        self.open_plots_btn.pack(side="left", padx=(6, 0))

        btn_row2 = tk.Frame(pad, bg=PANEL)
        btn_row2.pack(fill="x", pady=(0, 12))
        self.excel_btn = ttk.Button(btn_row2, text="导出 Excel", style="Ghost.TButton",
                                     command=self._export_excel)
        self.excel_btn.pack(side="left")
        self.excel_btn.state(["disabled"])
        ttk.Button(btn_row2, text="对比 2 段录音…", style="Ghost.TButton",
                   command=self._open_compare_dialog
                   ).pack(side="left", padx=(6, 0))

        # 进度条
        self.progress = ttk.Progressbar(pad, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 12))

        # 日志
        tk.Label(pad, text="日志", bg=PANEL, fg=ACCENT, font=FONT_UI_B).pack(anchor="w")
        log_wrap = tk.Frame(pad, bg=PANEL)
        log_wrap.pack(fill="both", expand=True, pady=(4, 0))
        self.log_text = tk.Text(log_wrap, bg="#0b1117", fg=TEXT, font=FONT_MONO,
                                bd=0, highlightthickness=1, highlightbackground=BORDER,
                                insertbackground=TEXT, wrap="word",
                                padx=8, pady=6, state="disabled",
                                height=10, width=30)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(log_wrap, command=self.log_text.yview)
        sb.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=sb.set)

        self.log_text.tag_configure("INFO",    foreground=TEXT)
        self.log_text.tag_configure("DEBUG",   foreground=MUTED)
        self.log_text.tag_configure("WARNING", foreground=WARN)
        self.log_text.tag_configure("ERROR",   foreground=ERR)
        self.log_text.tag_configure("OK",      foreground=OK)
        self.log_text.tag_configure("META",    foreground=ACCENT)

    def _build_right_panel(self, parent):
        # 顶栏：放和当前 voice map 强相关的工具（centroid 加载/保存 + 状态）。
        # 跟绘图放一起，用户看图时能顺手操作；分析参数才留在 Settings 里。
        toolbar = tk.Frame(parent, bg=PANEL, height=34)
        toolbar.pack(side="top", fill="x", padx=8, pady=(6, 0))
        toolbar.pack_propagate(False)

        tk.Label(toolbar, text="Centroid", bg=PANEL, fg=MUTED, font=FONT_UI
                 ).pack(side="left")
        ttk.Button(toolbar, text="加载", style="Ghost.TButton",
                   command=self._load_centroids).pack(side="left", padx=(8, 0))
        self.cent_save_btn = ttk.Button(toolbar, text="保存当前",
                                        style="Ghost.TButton",
                                        command=self._save_centroids)
        self.cent_save_btn.pack(side="left", padx=(6, 0))
        self.cent_save_btn.state(["disabled"])   # 没分析过时禁用
        ttk.Button(toolbar, text="多 wav 联合训练…", style="Ghost.TButton",
                   command=self._train_centroids_from_many
                   ).pack(side="left", padx=(6, 0))
        self.cent_status_lbl = tk.Label(toolbar,
                                         text=self._centroid_status_text(),
                                         bg=PANEL, fg=MUTED, font=FONT_UI)
        self.cent_status_lbl.pack(side="left", padx=(12, 0))

        # Middle: nav_left + canvas + nav_right
        middle = tk.Frame(parent, bg=PANEL)
        middle.pack(side="top", fill="both", expand=True)

        self.nav_left = tk.Frame(middle, bg=PANEL, width=42)
        self.nav_left.pack(side="left", fill="y")
        self.nav_left.pack_propagate(False)

        self.nav_right = tk.Frame(middle, bg=PANEL, width=42)
        self.nav_right.pack(side="right", fill="y")
        self.nav_right.pack_propagate(False)

        self._fig = Figure(figsize=(7, 5), dpi=120, facecolor=PANEL)
        self._canvas = FigureCanvasTkAgg(self._fig, master=middle)
        cw = self._canvas.get_tk_widget()
        cw.configure(bg=PANEL, highlightthickness=0, bd=0)
        cw.pack(side="left", fill="both", expand=True, pady=6)
        # 占位期间窗口缩放/首次布局完成时重画（防止文字跑到右下角）。
        # 关键：add="+" 追加，不能覆盖 matplotlib 自己的 resize handler，
        # 否则 figure 不会跟着 widget 缩放，第一次绘制就错位。
        cw.bind("<Configure>", self._on_canvas_configure, add="+")

        # 大号纯字体箭头，放在导航带正中；hover 有强对比
        self.prev_btn = tk.Label(self.nav_left, text="◀",
                                 bg=PANEL, fg=ACCENT,
                                 font=("Segoe UI", 24, "bold"),
                                 cursor="hand2")
        self.next_btn = tk.Label(self.nav_right, text="▶",
                                 bg=PANEL, fg=ACCENT,
                                 font=("Segoe UI", 24, "bold"),
                                 cursor="hand2")
        self.prev_btn.bind("<Button-1>", lambda _e: self._cycle_metric(-1))
        self.next_btn.bind("<Button-1>", lambda _e: self._cycle_metric(+1))
        for b in (self.prev_btn, self.next_btn):
            b.bind("<Enter>", lambda e, w=b: w.configure(bg=PANEL_HI, fg=ACCENT_HI))
            b.bind("<Leave>", lambda e, w=b: w.configure(bg=PANEL, fg=ACCENT))
        # 默认隐藏按钮（条仍保留宽度，视觉上像左右留白），下拉可用时再显示
        self._set_nav_visible(False)

    # ── Metric 导航（键盘 + 侧边按钮） ──
    def _set_nav_visible(self, visible: bool):
        # 两条 nav 条始终保留（充当图像两侧的留白）；只控制箭头字符的显隐
        if visible:
            self.prev_btn.place(relx=0.5, rely=0.5, anchor="center")
            self.next_btn.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self.prev_btn.place_forget()
            self.next_btn.place_forget()

    def _cycle_metric(self, delta: int):
        vals = getattr(self, "_metric_flat", None) or []
        if not vals:
            return
        cur = self.metric_var.get()
        try:
            i = vals.index(cur)
        except ValueError:
            i = 0
        self.metric_var.set(vals[(i + delta) % len(vals)])
        # trace on metric_var fires _on_metric_change automatically

    def _bind_global_keys(self):
        def on_key(event):
            # 在 Entry / 文本区等输入控件里时不抢键
            cls = event.widget.winfo_class()
            if cls in ("Entry", "Text", "TEntry", "Spinbox", "TSpinbox"):
                return
            if event.keysym == "Left":
                self._cycle_metric(-1)
            elif event.keysym == "Right":
                self._cycle_metric(+1)
        self.bind("<Key-Left>",  on_key)
        self.bind("<Key-Right>", on_key)

        # 鼠标滚轮在 Metric 按钮上循环切换 metric。
        # Windows/macOS 用 <MouseWheel> (event.delta ±120),
        # Linux X11 用 <Button-4> / <Button-5>。
        def on_wheel(event):
            delta = 0
            if getattr(event, "num", 0) == 4:      delta = -1
            elif getattr(event, "num", 0) == 5:    delta = +1
            elif getattr(event, "delta", 0) > 0:   delta = -1
            elif getattr(event, "delta", 0) < 0:   delta = +1
            if delta:
                self._cycle_metric(delta)
            return "break"
        for target in (self.metric_btn, self.nav_left, self.nav_right):
            target.bind("<MouseWheel>", on_wheel)
            target.bind("<Button-4>",  on_wheel)
            target.bind("<Button-5>",  on_wheel)

    # ── 拖放 ──
    def _register_dnd(self):
        if not _DND_OK:
            return
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self._on_drop)
        except Exception as e:  # noqa: BLE001
            self._append_log("WARNING", f"拖放未就绪：{e}")

    def _on_drop(self, event):
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]

        wav = next((p for p in paths if str(p).lower().endswith(".wav")), None)
        if not wav:
            self._append_log("WARNING", "忽略：非 .wav 文件")
            return

        if self._worker and self._worker.is_alive():
            self._append_log("WARNING", "分析进行中，已忽略新文件")
            return

        self._start_analysis(str(wav))

    def _on_canvas_configure(self, event):
        # 只在"正在显示占位"时重画；渲染 voice map 时不触，避免 flicker
        if not self._showing_placeholder:
            return
        # 防抖 60ms，避免连续 resize 反复重画
        try:
            if getattr(self, "_resize_after_id", None):
                self.after_cancel(self._resize_after_id)
        except Exception:
            pass
        self._resize_after_id = self.after(60, self._show_placeholder)

    def _sync_fig_to_widget(self):
        """
        把 figure 的 size_inches 强制对齐到当前 Tk canvas widget 的像素尺寸。
        matplotlib 虽然会在 <Configure> 时自己做一次，但首次绘制时可能它的
        handler 还没跑，figure 还停留在创建时的 figsize=(7,5)，画出来的内容
        就会偏到右下角。每次 draw 前显式同步一次，彻底消除 race。
        """
        cw = self._canvas.get_tk_widget()
        try:
            cw.update_idletasks()
        except tk.TclError:
            return
        w = cw.winfo_width()
        h = cw.winfo_height()
        if w <= 1 or h <= 1:
            return
        dpi = self._fig.get_dpi()
        need_w, need_h = w / dpi, h / dpi
        cur_w, cur_h = self._fig.get_size_inches()
        if abs(cur_w - need_w) > 0.02 or abs(cur_h - need_h) > 0.02:
            self._fig.set_size_inches(need_w, need_h, forward=False)

    # ── 占位画面 ──
    def _show_placeholder(self, msg: str = "拖入 .wav 文件开始"):
        """
        用 figure 级坐标渲染，不依赖 axes 状态。绘制前同步 figure 尺寸到
        widget 物理尺寸，保证所有 figure 坐标（0-1）对应到真实画面中心。
        """
        from matplotlib.patches import FancyBboxPatch
        self._showing_placeholder = True
        self._sync_fig_to_widget()
        self._fig.clear()
        self._fig.patch.set_facecolor(PANEL)

        # 圆角虚线框（figure 坐标）
        self._fig.patches.append(FancyBboxPatch(
            (0.18, 0.22), 0.64, 0.56,
            boxstyle="round,pad=0.01,rounding_size=0.03",
            linewidth=1.2, linestyle=(0, (6, 4)),
            edgecolor=BORDER, facecolor="none",
            transform=self._fig.transFigure))

        # 图标 + 标题 + 副标题（figure 坐标，不经 axes）
        self._fig.text(0.5, 0.62, "♪", ha="center", va="center",
                       color=ACCENT, fontsize=54, weight="bold", alpha=0.85)
        self._fig.text(0.5, 0.45, msg, ha="center", va="center",
                       color=TEXT, fontsize=17, weight="bold")
        self._fig.text(0.5, 0.35,
                       "Stereo WAV  ·  Ch 1 = Microphone  ·  Ch 2 = EGG",
                       ha="center", va="center",
                       color=MUTED, fontsize=10)

        self._canvas.draw_idle()

    # ── 分析 ──
    def _pick_audio(self):
        if self._worker and self._worker.is_alive():
            return
        path = filedialog.askopenfilename(
            title="选择音频文件",
            filetypes=[("WAV 文件", "*.wav"), ("所有文件", "*.*")])
        if path:
            self._start_analysis(path)

    def _pick_output_dir(self):
        path = filedialog.askdirectory(title="选择输出目录",
                                       initialdir=self.output_dir_var.get())
        if path:
            self.output_dir_var.set(path)

    def _start_analysis(self, audio_path: str):
        if self._worker and self._worker.is_alive():
            return

        p = Path(audio_path)
        if not p.exists():
            self._append_log("ERROR", f"文件不存在：{audio_path}")
            return

        out_dir = self.output_dir_var.get().strip()
        if not out_dir:
            self._append_log("ERROR", "请先指定输出目录")
            return
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        # 清日志
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._log_count = 0

        self.audio_path = p
        self.drop_label.configure(text=p.name, fg=ACCENT)
        self.drop_sub.configure(text=str(p.parent))

        self.metric_btn.state(["disabled"])
        self.open_csv_btn.state(["disabled"])
        self.progress.start(12)
        self._set_status("分析中…", ACCENT)
        self._show_placeholder("分析中…")

        # 弹出分析进度对话框（模态，关不掉，分析结束自动关）
        try:
            if self._progress_dialog is not None:
                self._progress_dialog.close()
        except Exception:
            pass
        self._progress_dialog = ProgressDialog(self, p.name)

        self._analysis_clarity = float(self.clarity_var.get())
        cfg = VoiceMapConfig(
            clarity_threshold=self._analysis_clarity,
            output_dir=out_dir,
        )
        audio = str(p)

        # Snapshot cluster params + loaded centroids for the worker
        k_snap      = int(self.cluster_k_var.get())
        nharm_snap  = int(self.cluster_nharm_var.get())
        cent_snap   = self._loaded_centroids
        # 用户可选的导出模式：不导出 / 每个 metric 一张 / 合并为一张
        if not self.export_plots_var.get():
            plot_mode_snap = "none"
        elif self.plot_layout_var.get() == "combined":
            plot_mode_snap = "combined"
        else:
            plot_mode_snap = "per-metric"

        def work():
            try:
                from analyzer import VoiceMapAnalyzer
                analyzer = VoiceMapAnalyzer(cfg)
                # Apply user-chosen cluster params
                analyzer.cluster_calculator.n_clusters  = k_snap
                analyzer.cluster_calculator.n_harmonics = nharm_snap
                analyzer.phon_calculator.n_clusters     = k_snap
                if cent_snap is not None:
                    analyzer.cluster_calculator.centroids_ = cent_snap

                def prog(step, total, label):
                    self._msg_q.put(("progress", step, total, label))

                data, out_file, grouped = analyzer.analyze_and_output_vrp(
                    audio, return_df=True, plot_mode=plot_mode_snap,
                    progress_cb=prog)
                self._msg_q.put(("done", True, {
                    "df": grouped,
                    "csv": out_file,
                    "points": len(data["midi"]),
                    "analyzer": analyzer,
                }))
            except Exception:  # noqa: BLE001
                self._msg_q.put(("done", False, {"error": traceback.format_exc()}))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _on_worker_done(self, ok: bool, payload: dict):
        self.progress.stop()
        # 关掉进度对话框
        if self._progress_dialog is not None:
            try:
                self._progress_dialog.close()
            except Exception:
                pass
            self._progress_dialog = None

        if ok:
            self._last_df = payload["df"]
            self.last_csv = payload["csv"]
            self._last_analyzer = payload.get("analyzer")
            self.csv_path_var.set(payload["csv"])
            self.open_csv_btn.state(["!disabled"])
            try:
                self.excel_btn.state(["!disabled"])
            except (AttributeError, tk.TclError):
                pass
            # 有了 analyzer 就能保存 centroid
            try:
                self.cent_save_btn.state(["!disabled"])
            except (AttributeError, tk.TclError):
                pass
            self._set_status(f"完成 · {payload['points']:,} 点", OK)
            self._append_log("META", f"✓ {payload['csv']}")
            self._refresh_metric_dropdown()
        else:
            self._set_status("失败", ERR)
            self._append_log("ERROR", payload["error"])
            self._show_placeholder("分析失败 — 查看日志")

    # ── Metric 切换 ──
    def _refresh_metric_dropdown(self):
        """重建分类菜单。每节只保留 df 里非全零的 metric；空节整节隐藏。"""
        if self._last_df is None:
            return
        df = self._last_df

        # 对聚类 share 列（Cluster 1..N / cPhon 1..N）放宽过滤：哪怕本次
        # K-means 碰巧把某个簇跑空（所有点被更近的其它中心抢光），下拉里
        # 也要保留全部 k 个条目，让用户看到 "这个簇这次为空"，而不是
        # 神秘地少一个。maxCluster / maxCPhon 保留常规过滤。
        import re as _re
        _cluster_share_re = _re.compile(r"^(Cluster|cPhon)\s+\d+$")

        def _has_data(col):
            if col not in df.columns:
                return False
            if _cluster_share_re.match(col):
                return True    # always present for k=current
            try:
                return float(df[col].abs().sum()) > 0
            except Exception:
                return True

        # 清空菜单
        self.metric_menu.delete(0, "end")
        flat = []   # 用于键盘 ← → 和 ◀ ▶ 按钮的扁平列表
        first_section = True
        for section_title, cols in _METRIC_SECTIONS:
            avail = [c for c in cols if _has_data(c)]
            if not avail:
                continue
            if not first_section:
                self.metric_menu.add_separator()
            first_section = False
            # 节标题：不要 state="disabled"，否则 Windows 原生菜单会给
            # 一层 emboss 的灰色底字 + 我们的 disabledforeground 叠起来
            # 产生 "幻影"。改成可点击但 command 为 no-op 的普通 item，
            # 通过 foreground / activebackground 全显式指定颜色，hover
            # 时保持不高亮（activebackground 与底色相同）。
            self.metric_menu.add_command(
                label=f"  {section_title}",
                foreground=ACCENT,
                background=PANEL_HI,
                activeforeground=ACCENT,
                activebackground=PANEL_HI,
                command=lambda: None)
            for m in avail:
                self.metric_menu.add_command(
                    label=f"      {m}",
                    command=lambda x=m: self.metric_var.set(x))
                flat.append(m)

        self._metric_flat = flat

        if not flat:
            self.metric_btn.state(["disabled"])
            self._set_nav_visible(False)
            self._show_placeholder("无可用 metric")
            return

        self.metric_btn.state(["!disabled"])
        self._set_nav_visible(len(flat) > 1)
        default = next((m for m in _DEFAULT_METRIC_CHAIN if m in flat), flat[0])
        self.metric_var.set(default)   # trace → _on_metric_change → _render

    def _on_metric_change(self, *_):
        col = self.metric_var.get()
        if col and self._last_df is not None and col in self._last_df.columns:
            self._render_metric(col)

    def _render_metric(self, col: str):
        if self._last_df is None or col not in self._last_df.columns:
            return

        # Clarity 阈值作为展示层过滤：只保留 grouped Clarity ≥ threshold 的 cell。
        # 分析时用过的阈值是下限；滑条拉低到它之下也不会让新 cell 冒出来，会提示。
        thr = float(self.clarity_var.get())
        df = self._last_df
        if "Clarity" in df.columns:
            df = df[df["Clarity"] >= thr]
            if len(df) == 0:
                self._show_placeholder(f"Clarity ≥ {thr:.2f} · 无 cell")
                return

        self._showing_placeholder = False
        self._sync_fig_to_widget()
        self._fig.clear()
        # Voice map 白底 — 导出截图和在面板里展示同一套配色，一致且
        # 直接可用于文章/幻灯（不用再做反色处理）。占位保留深色。
        self._fig.patch.set_facecolor("white")
        # 固定边距（而不是 tight_layout）保证切 metric 时绘图区位置不跳。
        # bottom=0.16 给 x 刻度 + "MIDI" 下标签留足空间（0.13 在 dpi=120
        # 下会被 MIDI 文字截掉底部几像素）；top=0.90 给加了分类前缀的标题。
        self._fig.subplots_adjust(left=0.13, right=0.90, top=0.90, bottom=0.16)
        ax = self._fig.add_subplot(111)
        ok = draw_vrp_on_ax(ax, self._fig, df, col)
        if not ok:
            self._show_placeholder(f"{col} · 无数据")
            return
        self._canvas.draw_idle()

    # ── 日志 ──
    def _init_logging(self):
        setup_logger("voicemap", level=logging.INFO)
        handler = QueueHandler(self._msg_q)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.setLevel(logging.INFO)
        for name in ("voicemap", "analyzer", "plotter", "metrics", "__main__"):
            logging.getLogger(name).addHandler(handler)
        logging.getLogger().addHandler(handler)

    def _append_log(self, level: str, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n", level)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self._log_count += 1

    def _drain_queue(self):
        try:
            while True:
                kind, *rest = self._msg_q.get_nowait()
                if kind == "log":
                    level, text = rest
                    self._append_log(level, text)
                    # 把有意义的状态行同步到进度对话框（跳过 "===" 分隔 / DEBUG）
                    if (self._progress_dialog is not None
                            and level in ("INFO", "OK", "META")
                            and text and not text.startswith("=")):
                        self._progress_dialog.set_status(text)
                elif kind == "progress":
                    step, total, label = rest
                    if self._progress_dialog is not None:
                        try:
                            self._progress_dialog.set_progress(step, total, label)
                        except Exception:
                            pass
                elif kind == "done":
                    ok, payload = rest
                    self._on_worker_done(ok, payload)
                elif kind == "train_done":
                    ok, payload = rest
                    self._on_train_done(ok, payload)
        except queue.Empty:
            pass
        self.after(80, self._drain_queue)

    # ── Centroid CSV ──
    def _centroid_status_text(self) -> str:
        if self._loaded_centroids_path:
            name = Path(self._loaded_centroids_path).name
            k = self._loaded_centroids.shape[0] if self._loaded_centroids is not None else "?"
            return f"已加载 {name} (k={k})"
        return "（未加载，将从头训练）"

    def _load_centroids(self):
        path = filedialog.askopenfilename(
            title="加载 centroid CSV",
            filetypes=[("CSV", "*.csv"), ("所有", "*.*")])
        if not path:
            return
        try:
            # Parse directly so we don't need an analyzer instance yet.
            import re as _re
            header_n = None
            rows = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s:
                        continue
                    if s.startswith("#"):
                        m = _re.search(r"n_harm\s*=\s*(\d+)", s)
                        if m:
                            header_n = int(m.group(1))
                        continue
                    parts = s.split(";")
                    if parts[0].lower().startswith("cluster"):
                        continue
                    rows.append([float(x) for x in parts[1:]])
            if not rows:
                raise ValueError("文件里没有 centroid 行")
            import numpy as _np
            cent = _np.asarray(rows, dtype=_np.float64)
            self._loaded_centroids = cent
            self._loaded_centroids_path = path
            # 同步 k / n_harm
            self.cluster_k_var.set(cent.shape[0])
            if header_n:
                self.cluster_nharm_var.set(header_n)
            self._append_log("META", f"✓ centroids 加载：{Path(path).name} k={cent.shape[0]}")
            self._refresh_centroid_status()
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", f"centroid 加载失败：{e}")

    def _train_centroids_from_many(self):
        """Pick multiple wavs → pool EGG features → one K-means → save CSV.
        Produces centroids that yield consistent cluster labels across all
        recordings analysed against them (cross-subject studies)."""
        if self._worker and self._worker.is_alive():
            self._append_log("WARNING", "分析进行中，训练已忽略")
            return
        paths = filedialog.askopenfilenames(
            title="选择多个 .wav 做联合 centroid 训练",
            filetypes=[("WAV", "*.wav"), ("所有", "*.*")])
        if not paths:
            return
        paths = [str(Path(p)) for p in paths if str(p).lower().endswith(".wav")]
        if not paths:
            self._append_log("WARNING", "没有选到 .wav")
            return
        out_csv = filedialog.asksaveasfilename(
            title="保存联合 centroid 到 CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="cEGG_joint.csv")
        if not out_csv:
            return

        # Modal progress dialog (reuse ProgressDialog shell)
        dlg = ProgressDialog(self, f"{len(paths)} 个 wav")
        self._progress_dialog = dlg
        dlg.set_status("准备训练…")

        k_snap     = int(self.cluster_k_var.get())
        nharm_snap = int(self.cluster_nharm_var.get())

        def work():
            try:
                from analyzer import VoiceMapAnalyzer
                from config import VoiceMapConfig
                cfg = VoiceMapConfig(
                    clarity_threshold=float(self.clarity_var.get()),
                    output_dir=self.output_dir_var.get())
                a = VoiceMapAnalyzer(cfg)
                a.cluster_calculator.n_clusters  = k_snap
                a.cluster_calculator.n_harmonics = nharm_snap

                def cb(step, total, msg):
                    self._msg_q.put(("log", "INFO", f"[{step}/{total}] {msg}"))

                a.train_cluster_centroids(paths, progress_cb=cb)
                a.save_centroids(out_csv)
                self._msg_q.put(("train_done", True, {
                    "csv": out_csv, "n_wavs": len(paths), "analyzer": a}))
            except Exception:  # noqa: BLE001
                self._msg_q.put(("train_done", False, {"error": traceback.format_exc()}))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _on_train_done(self, ok: bool, payload: dict):
        if self._progress_dialog is not None:
            try: self._progress_dialog.close()
            except Exception: pass
            self._progress_dialog = None
        if ok:
            self._loaded_centroids      = payload["analyzer"].cluster_calculator.centroids_
            self._loaded_centroids_path = payload["csv"]
            self._last_analyzer         = payload["analyzer"]
            self.cent_save_btn.state(["!disabled"])
            self._refresh_centroid_status()
            self._append_log("META",
                             f"✓ 联合训练完成：{payload['n_wavs']} 个 wav → "
                             f"{Path(payload['csv']).name}")
            self._append_log("INFO", "已自动加载新 centroid；下一次拖 wav 分析会用它")
        else:
            self._append_log("ERROR", payload["error"])

    def _save_centroids(self):
        if self._last_analyzer is None:
            self._append_log("WARNING", "还没分析过，没有 centroid 可保存")
            return
        path = filedialog.asksaveasfilename(
            title="保存 centroid CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="cEGG.csv")
        if not path:
            return
        try:
            self._last_analyzer.save_centroids(path)
            self._append_log("META", f"✓ centroids 保存：{Path(path).name}")
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", f"centroid 保存失败：{e}")

    def _refresh_centroid_status(self):
        # 顶栏状态
        try:
            self.cent_status_lbl.configure(text=self._centroid_status_text())
        except (AttributeError, tk.TclError):
            pass

    # ── 设置对话框 ──
    def _open_settings(self):
        # 单例：已打开就 focus；没打开就 new 一个
        if self._settings_dialog is not None:
            try:
                if self._settings_dialog.winfo_exists():
                    self._settings_dialog.lift()
                    self._settings_dialog.focus_force()
                    return
            except tk.TclError:
                pass
        self._settings_dialog = SettingsDialog(self)
        # 关闭时清引用
        def _on_destroy(_e, _self=self):
            if _e.widget is _self._settings_dialog:
                _self._settings_dialog = None
        self._settings_dialog.bind("<Destroy>", _on_destroy)

    # ── Clarity 变化回调（由 clarity_var.trace_add 触发） ──
    def _on_clarity_var_changed(self, *_):
        # 1) 同步设置对话框里的数值显示
        if self._settings_dialog is not None:
            try:
                if self._settings_dialog.winfo_exists():
                    self._settings_dialog.update_clarity_label()
            except tk.TclError:
                pass
        # 2) 防抖后重绘 voice map（不重跑分析，只改展示层过滤阈值）
        if self._last_df is None:
            return
        if self._clarity_render_after is not None:
            try:
                self.after_cancel(self._clarity_render_after)
            except Exception:
                pass
        col = self.metric_var.get()
        if not col:
            return
        self._clarity_render_after = self.after(80, lambda c=col: self._render_metric(c))

    def _set_status(self, text: str, color: str = MUTED):
        self.status_lbl.configure(text=text, fg=color)
        self.status_dot.configure(fg=color)

    def _open_compare_dialog(self):
        """A | B | A-B comparison on two previously-written VRP CSVs."""
        CompareDialog(self)

    def _export_excel(self):
        """一次分析完成后，可导出 .xlsx：Summary + Grouped + 每 metric 一个 heatmap sheet。"""
        if self._last_df is None or self.last_csv is None:
            self._append_log("WARNING", "还没分析过，无法导出 Excel")
            return
        default = str(Path(self.last_csv).with_suffix(".xlsx"))
        path = filedialog.asksaveasfilename(
            title="导出 Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=Path(default).name,
            initialdir=str(Path(default).parent))
        if not path:
            return
        try:
            from excel_export import export_vrp_xlsx
            export_vrp_xlsx(self._last_df, path)
            self._append_log("META", f"✓ Excel 已导出：{path}")
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", f"Excel 导出失败：{e}")

    def _open_csv(self):
        """用系统默认程序直接打开 CSV 文件（Excel / 记事本等）。"""
        if not self.last_csv:
            return
        p = Path(self.last_csv)
        if not p.exists():
            self._append_log("ERROR", f"CSV 不存在：{p}")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(p))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", f"打开 CSV 失败：{e}")

    def _open_output_dir(self):
        """打开输出目录（文件夹）。"""
        path = Path(self.output_dir_var.get())
        if not path.exists():
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", f"打开目录失败：{e}")


def main():
    app = FonaDynApp()
    app.mainloop()


if __name__ == "__main__":
    main()
