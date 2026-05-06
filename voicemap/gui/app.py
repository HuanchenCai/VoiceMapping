#!/usr/bin/env python3
"""VoiceMap — 极简两栏 GUI：拖入 .wav → 自动分析 → 右侧嵌入 voice map，下拉切换 metric。"""

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

_HERE = Path(__file__).resolve().parent.parent  # voicemap/

from voicemap.config import DEFAULT_CONFIG, VoiceMapConfig
from voicemap.logger import setup_logger
from voicemap.plotter import draw_vrp_on_ax, METRIC_CFG, _SKIP_ZERO_METRICS

# Theme tokens, custom widgets, dialogs — extracted to gui/ subpackage in A0-2.
from voicemap.gui.theme import (
    BG, PANEL, PANEL_HI, BORDER, TEXT, MUTED, ACCENT, ACCENT_HI,
    OK, WARN, ERR,
    FONT_UI, FONT_UI_B, FONT_TITLE, FONT_SUB, FONT_DROP, FONT_MONO,
    _METRIC_SECTIONS, _DEFAULT_METRIC_CHAIN,
)
from voicemap.gui.widgets import MetricPopup, QueueHandler
from voicemap.gui.dialogs import (
    SettingsDialog, CompareDialog, ProgressDialog, AboutDialog,
)

# 可选的原生拖拽
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _TkBase, _DND_OK = TkinterDnD.Tk, True
except Exception:
    _TkBase, _DND_OK = tk.Tk, False
    DND_FILES = None  # type: ignore



# ─── 主应用 ──────────────────────────────────────────────────────────────────
class VoiceMapApp(_TkBase):
    def __init__(self):
        super().__init__()
        dnd_hint = "" if _DND_OK else "（未安装 tkinterdnd2，拖放已降级为点击）"
        # 默认中文软件名；i18n 上线（A0-4）后会按当前语言切换
        self.title(f"嗓音声学品质多维分析图谱 {dnd_hint}".strip())
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
        self._build_menubar()
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

    def _build_menubar(self):
        """Praat 风格顶部菜单栏：每个 metric 分类一个顶级菜单。
        点击 metric 直接 set metric_var → trace 触发重绘。
        分析未完成或某 metric 全零时，对应项 disable。"""
        mb = tk.Menu(self, tearoff=0,
                     bg=PANEL_HI, fg=TEXT,
                     activebackground=ACCENT, activeforeground=BG,
                     borderwidth=0)

        # 文件菜单：常用入口（Open / 设置 / Quit）
        m_file = tk.Menu(mb, tearoff=0,
                          bg=PANEL_HI, fg=TEXT,
                          activebackground=ACCENT, activeforeground=BG,
                          borderwidth=0)
        m_file.add_command(label="打开 WAV...", command=self._pick_audio)
        m_file.add_command(label="打开输出目录", command=self._open_output_dir)
        m_file.add_separator()
        m_file.add_command(label="设置...", command=self._open_settings)
        m_file.add_separator()
        m_file.add_command(label="退出", command=self.destroy)
        mb.add_cascade(label="文件", menu=m_file)

        # 每个 metric 分类一个顶级菜单
        # metric_section_menus: section_title -> (Menu, [(label, end_index), ...])
        # 用来 _refresh_metric_dropdown 时按 section 启用/禁用单个 item。
        self._metric_section_menus = {}
        for section_title, metrics in _METRIC_SECTIONS:
            m = tk.Menu(mb, tearoff=0,
                        bg=PANEL_HI, fg=TEXT,
                        activebackground=ACCENT, activeforeground=BG,
                        selectcolor=ACCENT, borderwidth=0)
            entries = []   # [(metric_name, item_index), ...]
            for name in metrics:
                m.add_radiobutton(label=name,
                                   variable=self.metric_var,
                                   value=name)
                entries.append((name, m.index("end")))
                # 默认全部 disable，等分析完后 _refresh_metric_dropdown 启用可用的
                m.entryconfig(m.index("end"), state="disabled")
            mb.add_cascade(label=section_title.split(" · ", 1)[-1],
                           menu=m)
            self._metric_section_menus[section_title] = (m, entries)

        # 帮助菜单（A0-2 加 About 对话框入口；后续 A0-4 加用户手册 / 快捷键说明）
        m_help = tk.Menu(mb, tearoff=0,
                          bg=PANEL_HI, fg=TEXT,
                          activebackground=ACCENT, activeforeground=BG,
                          borderwidth=0)
        m_help.add_command(label="关于...", command=self._open_about)
        mb.add_cascade(label="帮助", menu=m_help)

        self.config(menu=mb)
        self._menubar = mb

    def _open_about(self):
        """显示关于对话框（版本/作者/版权）。"""
        AboutDialog(self)

    def _build_header(self, parent):
        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x", pady=(0, 8))
        tk.Label(head, text="嗓音声学品质多维分析图谱",
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
        # 当前 metric 的展示标签（不再可点开 popup —— 选 metric 走顶部菜单栏，
        # Praat 风格：每个分类一个顶级 cascade）。保留 widget 名 metric_btn 是
        # 为了让其它地方（_refresh_metric_dropdown / _cycle_metric / 旧代码）
        # 不用大改。它现在就是一个 disabled-look label。
        # 点开 → tk.Menu.tk_popup，最朴素的下拉。Tk 内置的 popup 机制
        # 自己处理定位、键盘焦点、点外面消失，不踩 overrideredirect /
        # 多屏 / withdraw 那一堆坑。同时顶部菜单栏也保留可用，两条路。
        self.metric_btn = tk.Button(side, textvariable=self.metric_var,
                                    bg=PANEL_HI, fg=TEXT,
                                    activebackground=BORDER, activeforeground=TEXT,
                                    disabledforeground=MUTED,
                                    font=FONT_UI, bd=0, relief="flat",
                                    padx=10, pady=4, width=18,
                                    cursor="hand2",
                                    command=self._popup_metric_menu)
        self.metric_btn.pack()
        self.metric_btn.config(state="disabled")
        self._metric_popup = None
        self.metric_menu = None
        # metric_var 的变化 = popup 选中 / 键盘 ← → 触发 → 自动重绘
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
        self.report_btn = ttk.Button(btn_row2, text="生成报告", style="Ghost.TButton",
                                       command=self._export_report)
        self.report_btn.pack(side="left", padx=(6, 0))
        self.report_btn.state(["disabled"])
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

        # ── M2 plot toolbar — fit / annotate / save / copy ────────────────
        plot_tb = tk.Frame(parent, bg=PANEL, height=34)
        plot_tb.pack(side="top", fill="x", padx=8, pady=(4, 0))
        plot_tb.pack_propagate(False)

        tk.Label(plot_tb, text="绘图", bg=PANEL, fg=MUTED, font=FONT_UI
                 ).pack(side="left")

        # Fit dropdown
        self.fit_btn = ttk.Button(plot_tb, text="拟合 ▾", style="Ghost.TButton",
                                   command=self._open_fit_menu)
        self.fit_btn.pack(side="left", padx=(8, 0))

        # Annotation toggle
        self.annot_btn = ttk.Button(plot_tb, text="标注", style="Ghost.TButton",
                                     command=self._toggle_annotation_mode)
        self.annot_btn.pack(side="left", padx=(6, 0))

        # Reset overlays
        ttk.Button(plot_tb, text="复位", style="Ghost.TButton",
                   command=self._clear_overlays).pack(side="left", padx=(6, 0))

        # Save / Copy on the right side
        ttk.Button(plot_tb, text="复制图片", style="Ghost.TButton",
                   command=self._copy_canvas).pack(side="right")
        self.save_btn = ttk.Button(plot_tb, text="保存 ▾", style="Ghost.TButton",
                                    command=self._open_save_menu)
        self.save_btn.pack(side="right", padx=(0, 6))

        # All these need a populated canvas to make sense; disable until first analysis.
        for b in (self.fit_btn, self.annot_btn, self.save_btn):
            b.state(["disabled"])

        # Overlay state
        from voicemap.plot_overlay import OverlayManager
        self._overlay_mgr = OverlayManager()
        self._annot_mode_on = False
        self._annot_canvas_cid = None    # mpl_connect id for click capture

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

        # 鼠标滚轮在画布两侧的 nav 条上 = 切换 metric（与 ◀ ▶ 等价）。
        # **不要**在 metric 按钮上绑定滚轮 —— 按钮的功能是"点开列表"，
        # 滚轮在按钮上不应该改 metric，以免混淆"按钮就是切换器"的预期。
        def on_wheel(event):
            delta = 0
            if getattr(event, "num", 0) == 4:      delta = -1
            elif getattr(event, "num", 0) == 5:    delta = +1
            elif getattr(event, "delta", 0) > 0:   delta = -1
            elif getattr(event, "delta", 0) < 0:   delta = +1
            if delta:
                self._cycle_metric(delta)
            return "break"
        for target in (self.nav_left, self.nav_right):
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
        占位画面跟分析完成后的 voice map 用同一套布局：白底、同样的
        subplots_adjust 边距、MIDI/SPL 轴范围一致。这样从"未分析"
        切到"已分析"画面尺寸/坐标系不会跳，用户体验上是平滑过渡。
        """
        self._showing_placeholder = True
        self._sync_fig_to_widget()
        self._fig.clear()
        # 与 _render_metric 一致的白底 + 边距
        self._fig.patch.set_facecolor("white")
        self._fig.subplots_adjust(left=0.13, right=0.90, top=0.90, bottom=0.16)
        ax = self._fig.add_subplot(111)
        ax.set_facecolor("white")
        ax.set_xlim(DEFAULT_CONFIG.n_min_midi, DEFAULT_CONFIG.n_max_midi)
        ax.set_ylim(DEFAULT_CONFIG.n_min_spl, DEFAULT_CONFIG.n_max_spl)
        ax.set_xlabel("MIDI")
        ax.set_ylabel("SPL (dB)")
        # 浅灰网格，让画面有"准备好接收数据"的感觉
        ax.grid(True, which="both", color="#e0e0e0", linewidth=0.7, zorder=1)
        ax.set_axisbelow(True)
        for spine in ax.spines.values():
            spine.set_color("#cccccc")
            spine.set_linewidth(0.8)
        ax.tick_params(colors="#888888", labelsize=9)
        # 居中提示文字（axes 坐标）
        ax.text(0.5, 0.55, "♪", transform=ax.transAxes,
                ha="center", va="center",
                color=ACCENT, fontsize=44, weight="bold", alpha=0.55)
        ax.text(0.5, 0.40, msg, transform=ax.transAxes,
                ha="center", va="center",
                color="#444444", fontsize=15, weight="bold")
        ax.text(0.5, 0.32,
                "Stereo WAV  ·  Ch 1 = Microphone  ·  Ch 2 = EGG",
                transform=ax.transAxes,
                ha="center", va="center",
                color="#888888", fontsize=9)

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

        self.metric_btn.config(state="disabled")
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
                from voicemap.analyzer import VoiceMapAnalyzer
                analyzer = VoiceMapAnalyzer(cfg)
                # Apply user-chosen cluster params
                analyzer.cluster_calculator.n_clusters  = k_snap
                analyzer.cluster_calculator.n_harmonics = nharm_snap
                analyzer.phon_calculator.n_clusters     = k_snap
                if cent_snap is not None:
                    analyzer.cluster_calculator.centroids_ = cent_snap

                def prog(step, total, label):
                    self._msg_q.put(("progress", step, total, label))

                def partial(partial_grouped):
                    # Fires roughly halfway — analyzer hands us a partial
                    # grouped DataFrame (just the fast metrics filled,
                    # rest are zero). Main thread renders early heatmap.
                    self._msg_q.put(("partial", partial_grouped))

                data, out_file, grouped = analyzer.analyze_and_output_vrp(
                    audio, return_df=True, plot_mode=plot_mode_snap,
                    progress_cb=prog, partial_cb=partial)
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

    def _on_partial_ready(self, partial_df):
        """Phase A done — show first heatmap with fast metrics. Phase B
        is still running on the worker thread; full df arrives via 'done'."""
        self._last_df = partial_df
        # Refresh dropdown sections to whatever's non-zero in the partial set
        self._refresh_metric_dropdown()
        self._append_log("META",
                          "✓ 第一组指标完成，先出图，剩余指标后台继续…")

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
                self.report_btn.state(["!disabled"])
            except (AttributeError, tk.TclError):
                pass
            # 有了 analyzer 就能保存 centroid
            try:
                self.cent_save_btn.state(["!disabled"])
            except (AttributeError, tk.TclError):
                pass
            # M2 plot toolbar (拟合 / 标注 / 保存 / 复制) — 分析完才能用
            self._enable_plot_toolbar()
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

        # Build per-section availability data
        sections_avail = []   # [(section_title, [metric, ...]), ...]
        flat = []              # for keyboard ← → / ◀ ▶ cycling
        for section_title, cols in _METRIC_SECTIONS:
            avail = [c for c in cols if _has_data(c)]
            if not avail:
                continue
            sections_avail.append((section_title, avail))
            flat.extend(avail)

        self._metric_sections_avail = sections_avail
        self._metric_flat = flat

        # 同步 menubar：每个 section 内逐项设 normal / disabled
        if hasattr(self, "_metric_section_menus"):
            for section_title, (menu, entries) in self._metric_section_menus.items():
                avail_set = set()
                for st, cols in sections_avail:
                    if st == section_title:
                        avail_set = set(cols)
                        break
                for name, idx in entries:
                    menu.entryconfig(
                        idx, state=("normal" if name in avail_set else "disabled"))

        if not flat:
            self.metric_btn.config(state="disabled")
            self._set_nav_visible(False)
            self._show_placeholder("无可用 metric")
            return

        self.metric_btn.config(state="normal")
        self._set_nav_visible(len(flat) > 1)
        default = next((m for m in _DEFAULT_METRIC_CHAIN if m in flat), flat[0])
        self.metric_var.set(default)   # trace → _on_metric_change → _render

    def _on_metric_change(self, *_):
        col = self.metric_var.get()
        if col and self._last_df is not None and col in self._last_df.columns:
            self._render_metric(col)

    def _popup_metric_menu(self):
        """点 metric 按钮 → 弹下拉菜单。
        tk.Menu 本身不支持鼠标滚轮，所以把所有 metric 一坨平铺会显得很长
        且没法滚。改成 cascade：顶层只列分类（5 个），鼠标 hover 自动展开
        子菜单看具体 metric。每个子菜单最长 ~43 项，竖向能放下。"""
        if str(self.metric_btn.cget("state")) == "disabled":
            return
        sa = getattr(self, "_metric_sections_avail", None)
        if not sa:
            return

        m = tk.Menu(self, tearoff=0,
                    bg=PANEL_HI, fg=TEXT,
                    activebackground=ACCENT, activeforeground=BG,
                    selectcolor=ACCENT, borderwidth=0)
        # 持有 cascade 子菜单的引用 —— Tk 的 add_cascade 不会持有 menu
        # 对象的 Python 引用，函数返回后 sub 被 GC，下拉就空了。
        self._popup_submenus = []
        for section_title, cols in sa:
            sub = tk.Menu(m, tearoff=0,
                          bg=PANEL_HI, fg=TEXT,
                          activebackground=ACCENT, activeforeground=BG,
                          selectcolor=ACCENT, borderwidth=0)
            for c in cols:
                sub.add_radiobutton(label=c,
                                     variable=self.metric_var,
                                     value=c)
            m.add_cascade(label=section_title, menu=sub)
            self._popup_submenus.append(sub)

        # 在按钮正下方弹出。tk_popup 自己处理屏幕边界裁剪。
        x = self.metric_btn.winfo_rootx()
        y = self.metric_btn.winfo_rooty() + self.metric_btn.winfo_height()
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

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
        # Drop overlay artists from previous metric; fig.clear() below
        # would orphan them and the OverlayManager would lose its handles
        # (calling .remove() later would error). Clear bookkeeping now.
        if hasattr(self, "_overlay_mgr"):
            self._overlay_mgr.clear()
        # If user was in annotation mode, exit it (cursor + binding) so
        # the next click on a fresh heatmap doesn't trigger a stale prompt.
        if getattr(self, "_annot_mode_on", False):
            self._toggle_annotation_mode()
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
                elif kind == "partial":
                    (partial_df,) = rest
                    self._on_partial_ready(partial_df)
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
                from voicemap.analyzer import VoiceMapAnalyzer
                from voicemap.config import VoiceMapConfig
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

    # ── M2 plot toolbar handlers ────────────────────────────────────────
    def _enable_plot_toolbar(self):
        """Called after first successful analysis."""
        try:
            for b in (self.fit_btn, self.annot_btn, self.save_btn):
                b.state(["!disabled"])
        except (AttributeError, tk.TclError):
            pass

    def _clear_overlays(self):
        """Remove fits / annotations from the current heatmap, redraw."""
        if hasattr(self, "_overlay_mgr"):
            self._overlay_mgr.clear()
            try:
                self._canvas.draw_idle()
            except Exception:
                pass

    def _open_fit_menu(self):
        """Popup with fit method choices; clicking applies and draws."""
        if self._last_df is None:
            return
        m = tk.Menu(self, tearoff=0,
                    bg=PANEL_HI, fg=TEXT,
                    activebackground=ACCENT, activeforeground=BG,
                    font="TkMenuFont", bd=0)
        m.add_command(label="  在图上叠加：", state="disabled",
                      foreground=ACCENT)
        m.add_separator()
        m.add_command(label="  音域中心线 (linear)",
                      command=lambda: self._apply_fit("center", "linear"))
        m.add_command(label="  音域中心线 (polynomial deg=3)",
                      command=lambda: self._apply_fit("center", "polynomial"))
        m.add_command(label="  音域中心线 (spline)",
                      command=lambda: self._apply_fit("center", "spline"))
        m.add_command(label="  音域中心线 (lowess)",
                      command=lambda: self._apply_fit("center", "lowess"))
        m.add_separator()
        m.add_command(label="  当前 metric 趋势 (twin axis, polynomial)",
                      command=lambda: self._apply_fit("trend", "polynomial"))
        m.add_command(label="  当前 metric 趋势 (twin axis, lowess)",
                      command=lambda: self._apply_fit("trend", "lowess"))
        m.add_separator()
        m.add_command(label="  清除叠加",
                      command=self._clear_overlays)
        try:
            x = self.fit_btn.winfo_rootx()
            y = self.fit_btn.winfo_rooty() + self.fit_btn.winfo_height()
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def _apply_fit(self, kind: str, method: str):
        if self._last_df is None or self._showing_placeholder:
            return
        from voicemap.plot_overlay import fit_voice_center, fit_metric_trend
        ax = self._fig.axes[0] if self._fig.axes else None
        if ax is None:
            return
        if kind == "center":
            artists = fit_voice_center(self._last_df, ax,
                                        method=method, color="#ff3e88")
        else:   # "trend"
            col = self.metric_var.get()
            artists = fit_metric_trend(self._last_df, col, ax,
                                        method=method, color="#00d9ff")
        self._overlay_mgr.add(artists)
        self._canvas.draw_idle()
        self._append_log("META", f"叠加 {kind}/{method}")

    def _toggle_annotation_mode(self):
        """Click toggle: next canvas click captures (x, y) and prompts text."""
        if self._last_df is None:
            return
        cw = self._canvas.get_tk_widget()
        if self._annot_mode_on:
            # Turn off
            try:
                if self._annot_canvas_cid is not None:
                    self._canvas.mpl_disconnect(self._annot_canvas_cid)
            except Exception:
                pass
            self._annot_canvas_cid = None
            self._annot_mode_on = False
            self.annot_btn.configure(text="标注")
            cw.configure(cursor="")
        else:
            # Turn on — next plot click prompts for text
            self._annot_mode_on = True
            self.annot_btn.configure(text="标注 ◉")
            cw.configure(cursor="cross")
            self._annot_canvas_cid = self._canvas.mpl_connect(
                "button_press_event", self._on_canvas_click_for_annotation)

    def _on_canvas_click_for_annotation(self, event):
        if not self._annot_mode_on:
            return
        if event.xdata is None or event.ydata is None:
            return  # outside axes
        # Round to integer (MIDI, dB) since the heatmap is on those grids
        x_data = float(event.xdata)
        y_data = float(event.ydata)
        # Prompt for text
        from tkinter import simpledialog
        text = simpledialog.askstring(
            "标注", f"在 (MIDI={x_data:.1f}, SPL={y_data:.1f}) 处的标注文本：",
            parent=self)
        if not text:
            return
        from voicemap.plot_overlay import add_annotation
        ax = event.inaxes
        artists = add_annotation(ax, x_data, y_data, text)
        self._overlay_mgr.add(artists)
        self._canvas.draw_idle()
        self._append_log("META", f"标注 ({x_data:.1f}, {y_data:.1f}): {text}")
        # One-shot: turn off mode after each annotation so cursor returns to normal
        self._toggle_annotation_mode()

    def _open_save_menu(self):
        """Popup of formats; click → file dialog with that format."""
        if self._last_df is None:
            return
        from voicemap.plot_overlay import SAVE_FORMATS
        m = tk.Menu(self, tearoff=0,
                    bg=PANEL_HI, fg=TEXT,
                    activebackground=ACCENT, activeforeground=BG,
                    font="TkMenuFont", bd=0)
        m.add_command(label="  保存当前画布为：", state="disabled",
                      foreground=ACCENT)
        m.add_separator()
        for desc, ext in SAVE_FORMATS:
            m.add_command(label=f"  {desc} (.{ext})",
                          command=lambda e=ext, d=desc: self._save_canvas(e, d))
        try:
            x = self.save_btn.winfo_rootx()
            y = self.save_btn.winfo_rooty() + self.save_btn.winfo_height()
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def _save_canvas(self, fmt: str, desc: str = ""):
        col = self.metric_var.get() or "voice_map"
        from voicemap.plot_overlay import save_figure
        from tkinter import filedialog
        default = f"{Path(self.last_csv).stem if self.last_csv else 'voice_map'}_{col}.{fmt}"
        path = filedialog.asksaveasfilename(
            title=f"保存为 {desc}",
            defaultextension=f".{fmt}",
            filetypes=[(desc, f"*.{fmt}")],
            initialfile=default,
            initialdir=str(Path(self.output_dir_var.get())))
        if not path:
            return
        try:
            save_figure(self._fig, path, fmt=fmt, dpi=300)
            self._append_log("META", f"✓ 已保存: {path}")
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", f"保存失败: {e}")

    def _copy_canvas(self):
        from voicemap.plot_overlay import copy_figure_to_clipboard
        if self._last_df is None or self._showing_placeholder:
            return
        ok = copy_figure_to_clipboard(self._fig)
        if ok:
            self._append_log("META", "✓ 已复制到剪贴板")
        else:
            self._append_log("ERROR",
                              "复制失败 — 检查 pywin32 (Win) 或 xclip/wl-copy (Linux)")

    # ────────────────────────────────────────────────────────────────────
    def _open_compare_dialog(self):
        """A | B | A-B comparison on two previously-written VRP CSVs."""
        CompareDialog(self)

    def _export_report(self):
        """生成中文嗓音分析报告 (.md)：每项指标按临床阈值自动分级。"""
        if self._last_df is None or self.last_csv is None:
            self._append_log("WARNING", "还没分析过，无法生成报告")
            return
        default = str(Path(self.last_csv).with_suffix(".report.md"))
        path = filedialog.asksaveasfilename(
            title="导出嗓音分析报告",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt")],
            initialfile=Path(default).name,
            initialdir=str(Path(default).parent))
        if not path:
            return
        try:
            from voicemap.report import generate_report
            audio_name = self.audio_path.name if self.audio_path else "(unknown)"
            generate_report(self._last_df, path, audio_name=audio_name)
            self._append_log("META", f"✓ 报告已导出：{path}")
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", f"报告生成失败：{e}")

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
            from voicemap.excel_export import export_vrp_xlsx
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
    app = VoiceMapApp()
    app.mainloop()


if __name__ == "__main__":
    main()
