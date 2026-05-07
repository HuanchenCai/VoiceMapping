#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
    TEXT_SEC, TEXT_MUTED,
    FONT_UI, FONT_UI_B, FONT_TITLE, FONT_SUB, FONT_DROP, FONT_MONO,
    FONT_CAPTION, FONT_SMALL, FONT_H2, FONT_DISPLAY, FONT_MONO_B,
    _METRIC_SECTIONS, _DEFAULT_METRIC_CHAIN,
)
from voicemap.gui.widgets import MetricPopup, QueueHandler, HoverTooltip
from voicemap.gui.dialogs import (
    SettingsDialog, CompareDialog, ProgressDialog, AboutDialog, LogWindow,
)
from voicemap.gui.modern_menu import ModernMenubar, ModernPopup
from voicemap.i18n import tr, set_language, get_language, subscribe as i18n_subscribe

# 可选的原生拖拽
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _TkBase, _DND_OK = TkinterDnD.Tk, True
except Exception:
    _TkBase, _DND_OK = tk.Tk, False
    DND_FILES = None  # type: ignore


class TrackEntry:
    """One audio track in the Tracks Panel. Holds its source path,
    metadata read from the wav header (no full decode), and post-analysis
    cached state (df / cycles count / wall time)."""
    __slots__ = ("path", "sr", "duration", "channels",
                 "df", "cells", "cycles", "dt", "state",
                 "csv", "analyzer", "_waveform_cache")

    def __init__(self, path: Path):
        self.path = path
        self.sr: int = 0
        self.duration: float = 0.0
        self.channels: int = 0
        # Pre-analysis: pull header-only info via soundfile.info — cheap.
        try:
            import soundfile as sf
            info = sf.info(str(path))
            self.sr = int(info.samplerate)
            self.duration = float(info.frames) / max(1, info.samplerate)
            self.channels = int(info.channels)
        except Exception:
            pass
        self.df = None       # pandas.DataFrame after analysis
        self.cells: int = 0
        self.cycles: int = 0
        self.dt: float = 0.0
        self.state: str = "queued"   # queued / analyzing / analyzed / failed
        self.csv: str = ""
        self.analyzer = None
        self._waveform_cache = None    # populated lazily by row builder



# ─── 主应用 ──────────────────────────────────────────────────────────────────
class VoiceMapApp(_TkBase):
    def __init__(self):
        super().__init__()
        # Window title 干净，只放软件名；tkinterdnd2 缺失的提示由 drop zone
        # 的 "drop.title_no_dnd" 文案承担（已 i18n 化，标题栏不再混入双语字串）。
        self.title(tr('app.title'))
        # Subscribe to i18n language changes so the title + menubar
        # rebuild when the user switches language at runtime.
        i18n_subscribe(self._on_language_changed)
        # Default 1500×1180 picked empirically so the Inspector's
        # worst-case content fits at default size with no clipping:
        #   chrome (menubar/header/tracks/metric-bar/status) ≈ 383 px
        #   inspector content for 5-band metric (e.g. VibratoRate):
        #     pad (name + desc + unit + 5 cards) reqh 422 px
        #     pinned value pill ≈ 176 px
        #     actions + sep + paddings ≈ 200 px
        #   inspector total: ≈ 800 px → window ≥ 1180 px
        # 1500×1180 gives ~30 px of breathing room. Fits most modern
        # monitors (1440p+); on 1080p the user gets auto-hide taskbar
        # or has to drag the window taller. Per user spec: "标准的尺寸,
        # 可以大一点, 但是任何信息都不能被裁掉".
        # Min 1280×900 covers the realistic ≤4-band metrics plus
        # pinned value pill + actions; rare 5-band overflow at min size
        # is the failure floor we accept.
        self.geometry("1600x1180")
        self.minsize(1380, 900)
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
        # Multi-file Tracks support — list of TrackEntry; _active_track is
        # an index into _tracks (-1 if none). audio_path / _last_df above
        # mirror the active entry's data so the existing single-file
        # rendering paths keep working.
        self._tracks: list[TrackEntry] = []
        self._active_track: int = -1
        self._track_row_widgets: list[tk.Frame] = []   # one per track row
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
        # Anti-chrome attempts. None of these reach the OS-drawn 1 px
        # outline around tk.Menu popups on Windows 11 (DWM uses classic
        # Win32 USER menu API for Tk, not the Fluent/WinUI compositor
        # that Explorer / Office menus use). Documented in CLAUDE.md
        # §8.4.1. Kept here so the option DB is at least consistent.
        self.option_add("*Menu.borderwidth",        0)
        self.option_add("*Menu.relief",             "flat")
        self.option_add("*Menu.activeBorderWidth",  0)
        self.option_add("*Menu.highlightThickness", 0)
        # Star-star wildcard reaches inner Tk-drawn elements (margins).
        self.option_add("*Menu*Background",         PANEL_HI)
        self.option_add("*Menu*Foreground",         TEXT)

        # Sun Valley Win11-Fluent ttk theme — applies to all ttk widgets
        # (Button / Entry / Spinbox / Combobox / Scrollbar / Progressbar
        # …). MUST come before _init_style so our Accent.TButton /
        # Ghost.TButton overrides layer on top of the theme defaults.
        try:
            import sv_ttk
            sv_ttk.set_theme("dark")
        except Exception:
            pass
        self._init_style()
        self._build_menubar()
        self._build_ui()
        self._init_logging()
        self._register_dnd()
        self._bind_global_keys()

        # Close any open menu popup when the main window is moved/resized.
        # overrideredirect popups use absolute screen coords, so they
        # don't follow the parent — without this, dragging the window
        # leaves popups orphaned at their original location until the
        # user clicks. _last_window_geom suppresses the spurious
        # <Configure> events Tk fires during initial mapping.
        self._last_window_geom = ""
        self.bind("<Configure>", self._on_window_configure, add="+")

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
        # If sv_ttk applied "sun-valley-dark", keep it. Only fall back to
        # "clam" when the modern theme didn't load. clam is hideous on
        # Win11; check before clobbering.
        try:
            current = s.theme_use()
            if "sun-valley" not in current and "vista" not in current:
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
        """Option-C layout (per docs/UI_DESIGN.md):

            ┌─────────────────────────────────────────────────────┐
            │ Menubar  ──── 1px BORDER divider ────                │
            │ Header (PANEL, full-width, app title)                │
            ├─────────────────────────────────────────────────────┤
            │ Tracks Panel (drop zone / file list)                 │
            ├─────────────────────────────────────────────────────┤
            │ Metric Bar (label + current metric)                  │
            ├──────────────────────────────────────┬──────────────┤
            │  ◀  Canvas (matplotlib heatmap)  ▶  │  Inspector    │
            │                                      │  360px fixed │
            ├──────────────────────────────────────┴──────────────┤
            │ Status Bar (file meta + copyright)                   │
            └─────────────────────────────────────────────────────┘
        """
        # Status bar packs first with side="bottom" so it claims the
        # last horizontal strip; everything else fills above it.
        self._build_status_bar(self)

        # Header (full-width PANEL strip). Already integrated with the
        # menubar above via matching bg.
        self._build_header(self)
        self._build_tracks_panel(self)
        self._build_metric_bar(self)

        # Main split: canvas (left, expand) + inspector (right, 420 fixed).
        # Inspector was 360 (per docs/UI_DESIGN.md) but ZH labels in
        # clinical bands ("开商正常 (0.4-0.7, 模态)" etc.) overflow at 360.
        # 420 gives ~85 px more for the band-label column without
        # squeezing the heatmap (canvas still > 1100 px wide).
        # padx=16 matches the rest of the chrome's left/right margin.
        # pady at top is 8 px — enough breath after metric bar without
        # surfacing a BG stripe.
        self._outer = outer = tk.Frame(self, bg=BG)
        outer.pack(side="top", fill="both", expand=True,
                   padx=16, pady=(8, 8))

        self.inspector = tk.Frame(outer, bg=PANEL, width=420,
                                   highlightthickness=1,
                                   highlightbackground=BORDER,
                                   highlightcolor=BORDER)
        self.inspector.pack(side="right", fill="y")
        self.inspector.pack_propagate(False)
        self._build_inspector(self.inspector)

        canvas_frame = tk.Frame(outer, bg=PANEL,
                                 highlightthickness=1,
                                 highlightbackground=BORDER,
                                 highlightcolor=BORDER)
        canvas_frame.pack(side="left", fill="both", expand=True,
                          padx=(0, 8))
        self._build_canvas_area(canvas_frame)

        # Removed widgets — left panel + drop zone redesigned. Set to
        # None so old call sites (.state(...) etc.) can be guarded.
        self.open_csv_btn   = None
        self.open_plots_btn = None
        self.excel_btn      = None
        self.report_btn     = None
        self.progress       = None
        # left/right kept as alias to maintain compatibility with any
        # external code using them (none currently).
        self.left = None
        self.right = canvas_frame

    def _build_menubar(self):
        """5-段顶部菜单栏：文件 / 编辑 / 参数 / 视图 / 帮助。

        A0-3 改为自画 ModernMenubar + ModernPopup（``voicemap.gui.modern_menu``）
        以躲开 tk.Menu 在 Win11 上的老 Win32 USER 菜单白边（CLAUDE.md §8.4.1）。
        A0-4 改为读 ``tr(...)`` —— 切语言时整个 menubar 重建。

        每个顶级菜单的 popup 是 lambda 工厂，每次点开重建，所以 popup
        item 的 label 在每次弹出时都按当前语言实时取。
        """
        # 旧的 menubar 还在就先销毁（语言切换时会走这里第二次）
        old = getattr(self, "_menubar", None)
        if old is not None:
            try:
                old.destroy()
            except tk.TclError:
                pass
        old_sep = getattr(self, "_menubar_sep", None)
        if old_sep is not None:
            try:
                old_sep.destroy()
            except tk.TclError:
                pass

        bar = ModernMenubar(self, bg=PANEL, height=32)
        # On first build _outer doesn't exist yet → just pack at top.
        # On rebuild (language switch) _outer is already packed → place
        # the new bar BEFORE it so the bar stays above the content.
        outer = getattr(self, "_outer", None)
        if outer is not None and outer.winfo_exists():
            bar.pack(side="top", fill="x", before=outer)
        else:
            bar.pack(side="top", fill="x")
        # Thin BORDER divider just below the menubar so the eye reads
        # 'menubar | content' as a clean boundary instead of seeing
        # the BG-coloured pady gap as a stray dark stripe.
        sep = tk.Frame(self, bg=BORDER, height=1)
        if outer is not None and outer.winfo_exists():
            sep.pack(side="top", fill="x", before=outer)
        else:
            sep.pack(side="top", fill="x")
        self._menubar_sep = sep

        bar.add_menu(tr("menu.file"),   self._popup_file)
        bar.add_menu(tr("menu.edit"),   self._popup_edit)
        bar.add_menu(tr("menu.metric"), self._popup_metric)
        bar.add_menu(tr("menu.view"),   self._popup_view)
        bar.add_menu(tr("menu.help"),   self._popup_help)

        self._menubar = bar
        self._metric_section_menus = {}     # 兼容旧接口（不再使用）

    def _on_window_configure(self, event):
        """When the user moves/resizes the main window, close any open
        menubar popup (overrideredirect popups don't follow the parent).

        Filter out the noisy <Configure> events Tk fires during initial
        widget mapping by comparing the geometry string — only react
        when geometry actually changed.
        """
        # Only react to events on the main window itself, not children
        if event.widget is not self:
            return
        try:
            geom = self.geometry()
        except tk.TclError:
            return
        if geom == self._last_window_geom:
            return
        self._last_window_geom = geom
        if self._menubar is not None:
            try:
                self._menubar._close_open_popup()
            except Exception:
                pass

    def _on_language_changed(self):
        """Subscriber: redraw window title and rebuild the menubar so the
        new language takes effect without restart. popup factories will
        auto-pick up the new tr() values on the next open.

        Defensive: also close any open menubar popup before rebuilding.
        ``_switch_language`` already does this on the click path, but if
        a third party calls ``set_language()`` directly (e.g. a future
        keyboard shortcut), we must not leave orphaned popups behind."""
        if self._menubar is not None:
            try:
                self._menubar._close_open_popup()
            except Exception:
                pass
        try:
            self.title(tr("app.title"))
        except tk.TclError:
            pass
        try:
            self._build_menubar()
        except tk.TclError:
            pass
        # Update persistent widgets created in _build_header / _build_top_bar /
        # _build_left_panel. Each is wrapped in a guard so a missing widget
        # (e.g. mid-init reorder) doesn't tank the whole switch.
        def _safe_text(attr_name: str, key: str, **kw):
            w = getattr(self, attr_name, None)
            if w is None:
                return
            try:
                w.configure(text=tr(key, **kw))
            except tk.TclError:
                pass

        _safe_text("_header_title",   "app.title")
        # status_lbl: re-render under the current status_key/kwargs
        if hasattr(self, "status_lbl") and hasattr(self, "_status_key"):
            try:
                self.status_lbl.configure(
                    text=tr(self._status_key, **(self._status_kwargs or {})))
            except tk.TclError:
                pass
        # drop zone — pick the right key based on whether DnD is active
        try:
            if self.drop_label.cget("text"):  # only if not analyzed yet
                # If a wav was loaded the label shows the filename; don't clobber.
                txt = self.drop_label.cget("text")
                if txt in (tr("drop.title"), tr("drop.title_no_dnd")) or \
                   txt in ("拖入 .wav 文件  /  点击浏览",
                           "Drop a .wav file  /  click to browse",
                           "点击浏览（安装 tkinterdnd2 可启用拖拽）",
                           "Click to browse (install tkinterdnd2 to enable drag-drop)"):
                    self.drop_label.configure(
                        text=tr("drop.title" if _DND_OK else "drop.title_no_dnd"))
        except tk.TclError:
            pass
        _safe_text("drop_sub",        "drop.subtitle")
        _safe_text("_metric_label",   "header.metric")
        _safe_text("_settings_btn",   "left.settings")
        _safe_text("_latest_csv_lbl", "left.latest_csv")
        _safe_text("open_csv_btn",    "left.open_csv")
        _safe_text("open_plots_btn",  "left.open_outdir")
        _safe_text("excel_btn",       "left.export_excel")
        _safe_text("report_btn",      "left.gen_report")
        _safe_text("_compare_btn",    "left.compare")
        _safe_text("_log_lbl",        "left.log")    # may be None; _safe_text guards
        # Inspector action buttons (option-C bottom)
        _safe_text("_inspect_btn_excel",   "inspector.btn.excel")
        _safe_text("_inspect_btn_report",  "inspector.btn.report")
        _safe_text("_inspect_btn_compare", "inspector.btn.compare")
        _safe_text("_metric_nav_hint",     "metric_bar.nav_hint")
        # Re-render Inspector (so metric description / unit / clinical
        # band labels follow the new language).
        try:
            self._update_inspector()
        except Exception:
            pass
        # Status bar (no_file / file_meta strings switch language too)
        try:
            self._update_statusbar()
        except Exception:
            pass
        # Status bar right side (copyright string, version-formatted)
        try:
            from voicemap.__version__ import __version__
            self._statusbar_right.configure(
                text=tr("statusbar.copyright", ver=__version__))
        except Exception:
            pass
        # Tracks Panel rows (label / state strings localised)
        try:
            self._tracks_render()
        except Exception:
            pass

    # ── popup factories（每次点开新建一个 ModernPopup） ──────────────────
    def _popup_file(self) -> "ModernPopup":
        p = ModernPopup(self)
        p.add_command(tr("file.open_wav"),    command=self._pick_audio,     accelerator="Ctrl+O")
        p.add_command(tr("file.open_outdir"), command=self._open_output_dir)
        p.add_separator()
        p.add_command(tr("file.export_excel"), command=self._export_excel)
        p.add_command(tr("file.gen_report"),   command=self._export_report)
        p.add_command(tr("file.compare"),      command=self._open_compare_dialog)
        p.add_separator()
        p.add_command(tr("file.settings"),    command=self._open_settings, accelerator="Ctrl+,")
        p.add_separator()
        p.add_command(tr("file.quit"),        command=self.destroy)
        return p

    def _popup_edit(self) -> "ModernPopup":
        p = ModernPopup(self)
        annot_label = (tr("edit.annotate_active")
                       if getattr(self, "_annot_mode_on", False)
                       else tr("edit.annotate"))
        p.add_command(annot_label,            command=self._toggle_annotation_mode)
        p.add_command(tr("edit.reset_annotate"), command=self._clear_overlays)
        p.add_separator()
        p.add_command(tr("edit.copy_image"),  command=self._copy_canvas,    accelerator="Ctrl+C")
        p.add_command(tr("edit.save_image"),  command=self._open_save_menu, accelerator="Ctrl+S")
        return p

    def _popup_metric(self) -> "ModernPopup":
        p = ModernPopup(self)
        p.add_command(tr("metric.prev"), command=lambda: self._cycle_metric(-1))
        p.add_command(tr("metric.next"), command=lambda: self._cycle_metric(+1))
        p.add_separator()
        # 5 个分类 cascade — 每个的工厂闭包绑定 section
        avail_set = self._available_metric_columns()
        # Map _METRIC_SECTIONS' Chinese-only labels to i18n keys.
        # _METRIC_SECTIONS still holds the canonical zh names because
        # they're also keys into self._metric_section_menus and the
        # avail_set lookup. Translate just the *display* label here.
        section_label_keys = ["metric.acoustic", "metric.egg",
                              "metric.singing", "metric.cluster",
                              "metric.density"]
        for (section_title, metrics), key in zip(_METRIC_SECTIONS,
                                                  section_label_keys):
            p.add_cascade(tr(key),
                          popup_factory=lambda m=metrics, av=avail_set:
                              self._popup_metric_section(m, av))
        p.add_separator()
        p.add_cascade(tr("metric.centroid"), popup_factory=self._popup_centroid)
        return p

    def _popup_metric_section(self, metrics, avail_set) -> "ModernPopup":
        p = ModernPopup(self)
        for name in metrics:
            fg = TEXT if name in avail_set else MUTED
            p.add_radiobutton(name,
                              variable=self.metric_var,
                              value=name,
                              foreground=fg)
        return p

    def _popup_centroid(self) -> "ModernPopup":
        p = ModernPopup(self)
        p.add_command(tr("metric.centroid.load"),  command=self._load_centroids)
        p.add_command(tr("metric.centroid.save"),  command=self._save_centroids)
        p.add_command(tr("metric.centroid.train"), command=self._train_centroids_from_many)
        return p

    def _popup_view(self) -> "ModernPopup":
        p = ModernPopup(self)
        p.add_command(tr("view.fit"), command=self._open_fit_menu)
        p.add_separator()
        p.add_command(tr("view.log"), command=self._open_log_window)
        return p

    def _open_log_window(self):
        """View menu → 日志面板 / Log Console — opens the standalone
        log Toplevel. Singleton; reopening lifts the existing window."""
        LogWindow.show(self)

    def _popup_help(self) -> "ModernPopup":
        p = ModernPopup(self)
        p.add_command(tr("help.about"), command=self._open_about)
        p.add_separator()
        p.add_cascade(tr("help.language"), popup_factory=self._popup_language)
        return p

    def _popup_language(self) -> "ModernPopup":
        """Cascade for switching language. Marks the current one with a ●."""
        p = ModernPopup(self)
        cur = get_language()
        p.add_radiobutton(tr("lang.zh"),
                          variable=tk.StringVar(value=cur), value="zh",
                          foreground=TEXT)
        p.add_radiobutton(tr("lang.en"),
                          variable=tk.StringVar(value=cur), value="en",
                          foreground=TEXT)
        # The tk.StringVars above are throwaway; we wire the actual
        # language change via direct command bindings instead so we can
        # call _switch_language() (which closes the popup chain BEFORE
        # broadcasting, so the menubar rebuild doesn't orphan our parent
        # Help popup).
        for entry in p._items:
            if entry["type"] != "radio":
                continue
            value = entry["value"]
            row = entry["row"]
            for w in (row,) + tuple(row.winfo_children()):
                w.unbind("<Button-1>")
                w.bind("<Button-1>",
                       lambda _e, v=value: self._switch_language(v))
        return p

    def _switch_language(self, lang: str) -> None:
        """Switch language safely from a menu popup.

        The flow is order-sensitive:
          1. Close the menubar's open popup chain. This is the Help
             popup that contains the language cascade — if we leave it
             alive while the menubar rebuilds, its anchor button gets
             destroyed and the popup floats orphaned next to the window.
          2. Call set_language(), which broadcasts → _on_language_changed
             rebuilds the menubar.
        """
        if self._menubar is not None:
            try:
                self._menubar._close_open_popup()
            except Exception:
                pass
        set_language(lang)

    def _available_metric_columns(self) -> set:
        """Set of metric column names that have non-zero data in the
        current analysis. Empty set when no analysis has run yet."""
        sa = getattr(self, "_metric_sections_avail", None)
        if not sa:
            return set()
        out = set()
        for _section, cols in sa:
            out.update(cols)
        return out

    def _open_about(self):
        """显示关于对话框（版本/作者/版权）。"""
        AboutDialog(self)

    def _build_header(self, parent):
        # bg=PANEL (same as the menubar) so the title row reads as a
        # natural continuation of the bar instead of having a BG-coloured
        # gap show as a 'black stripe'. Internal padding gives the title
        # breathing room while staying visually attached to the menubar.
        head = tk.Frame(parent, bg=PANEL)
        head.pack(fill="x")
        # padx=16 matches outer.padx so title aligns with content below
        head_inner = tk.Frame(head, bg=PANEL)
        head_inner.pack(fill="x", padx=16, pady=(6, 8))   # was (8, 12) — slim
        self._header_title = tk.Label(head_inner, text=tr("app.title"),
                                       bg=PANEL, fg=TEXT, font=FONT_TITLE)
        self._header_title.pack(side="left")
        self.status_dot = tk.Label(head_inner, text="●", bg=PANEL, fg=MUTED,
                                    font=("Segoe UI", 12))
        self.status_dot.pack(side="right", padx=(0, 4))
        self.status_lbl = tk.Label(head_inner, text=tr("status.ready"),
                                    bg=PANEL, fg=MUTED, font=FONT_SUB)
        self.status_lbl.pack(side="right")
        # 默认 status 文本是固定 key；_set_status 时会换成具体 key。
        self._status_key = "status.ready"
        self._status_kwargs: dict = {}

    def _build_tracks_panel(self, parent):
        """Multi-file Tracks Panel (option-C spec).

        Renders one row per loaded audio file. Empty state (= no tracks
        yet) shows the drop zone instead. Each row is clickable to
        switch the active track; the active row gets a 4 px ACCENT
        marker on its left edge.

        Layout caps the panel at ~140 px and adds a scrollbar when more
        files are loaded than fit on screen."""
        bar = tk.Frame(parent, bg=PANEL)
        bar.pack(side="top", fill="x")

        inner = tk.Frame(bar, bg=PANEL)
        inner.pack(fill="x", padx=16, pady=(6, 6))   # was 10 — slim chrome

        tk.Label(inner, text=tr("tracks.label"), bg=PANEL, fg=ACCENT,
                 font=FONT_UI_B).pack(anchor="w", pady=(0, 4))

        # Container that holds either the empty-state drop zone or
        # the rows-of-tracks scroll area. We swap children on first
        # file load so empty/loaded transitions are clean.
        self._tracks_body = tk.Frame(inner, bg=PANEL)
        self._tracks_body.pack(fill="x")

        # Empty state — drop zone fills the body initially.
        self.drop_zone = tk.Frame(self._tracks_body, bg=PANEL_HI,
                                   highlightthickness=2,
                                   highlightbackground=BORDER,
                                   highlightcolor=ACCENT, cursor="hand2")
        self.drop_zone.pack(fill="x")
        drop_inner = tk.Frame(self.drop_zone, bg=PANEL_HI)
        drop_inner.pack(fill="x", padx=18, pady=8)   # was 10 — slim chrome
        self.drop_label = tk.Label(
            drop_inner,
            text=tr("drop.title" if _DND_OK else "drop.title_no_dnd"),
            bg=PANEL_HI, fg=TEXT, font=FONT_DROP)
        self.drop_label.pack(anchor="w")
        self.drop_sub = tk.Label(
            drop_inner,
            text=tr("drop.subtitle"),
            bg=PANEL_HI, fg=MUTED, font=FONT_UI)
        self.drop_sub.pack(anchor="w")
        for w in (self.drop_zone, drop_inner, self.drop_label, self.drop_sub):
            w.bind("<Button-1>", lambda _e: self._pick_audio())
            w.bind("<Enter>",    lambda _e: self.drop_zone.config(highlightbackground=ACCENT))
            w.bind("<Leave>",    lambda _e: self.drop_zone.config(highlightbackground=BORDER))

        # Loaded-state container — populated on first track add.
        self._tracks_list_frame: tk.Frame | None = None

    # ── multi-file Tracks Panel: row factory + state transitions ────────
    def _tracks_render(self):
        """Render the Tracks Panel from self._tracks. Switches between
        empty-state drop zone and a scrollable list of track rows."""
        if not self._tracks:
            # Show empty state, hide list
            try:
                if self._tracks_list_frame is not None:
                    self._tracks_list_frame.pack_forget()
                self.drop_zone.pack(fill="x")
            except tk.TclError:
                pass
            return

        # Hide drop zone, show list
        try:
            self.drop_zone.pack_forget()
        except tk.TclError:
            pass

        # (Re)build the list frame
        if self._tracks_list_frame is not None:
            try:
                self._tracks_list_frame.destroy()
            except tk.TclError:
                pass
        self._tracks_list_frame = tk.Frame(self._tracks_body, bg=PANEL)
        self._tracks_list_frame.pack(fill="x")

        self._track_row_widgets = []
        for i, entry in enumerate(self._tracks):
            row = self._build_track_row(self._tracks_list_frame, entry, i)
            row.pack(fill="x", pady=1)
            self._track_row_widgets.append(row)

    def _build_track_row(self, parent, entry: "TrackEntry", idx: int) -> tk.Frame:
        """Single track row in option-C spec format:
            ▌ 01 ✓ test_Voice_EGG.wav     44.1k Hz · 8.2s · 12,525 cells   ▓▓░
        ▌ left strip is ACCENT only on the active row.
        Right side renders a tiny block-character waveform sketch from
        the audio file's amplitude buckets (cheap, no matplotlib)."""
        is_active = (idx == self._active_track)
        bg_row = PANEL_HI if is_active else PANEL

        outer = tk.Frame(parent, bg=bg_row, cursor="hand2")
        marker = tk.Frame(outer,
                          bg=ACCENT if is_active else bg_row,
                          width=4)
        marker.pack(side="left", fill="y")
        # Right-side mini waveform — drawn as a tk.Canvas with vertical
        # bars rather than Unicode block chars (those rendered as sparse
        # dashes when most of the audio was below 1/8 of peak — looked
        # broken). 220×36 px gives enough resolution to show envelope
        # shape and dynamic range of typical 30-180 s recordings.
        wave_amps = self._track_waveform_amps(entry)
        wave_canvas = tk.Canvas(outer, width=220, height=36,
                                bg=bg_row, highlightthickness=0, bd=0)
        wave_canvas.pack(side="right", padx=(0, 12))
        if wave_amps is not None and len(wave_amps) > 0:
            self._draw_waveform_canvas(wave_canvas, wave_amps,
                                        220, 36, ACCENT_HI)

        body = tk.Frame(outer, bg=bg_row)
        body.pack(side="left", fill="x", expand=True, padx=10, pady=6)

        # Row 1: 编号 · 状态 · 文件名
        line1 = tk.Frame(body, bg=bg_row)
        line1.pack(fill="x", anchor="w")
        tk.Label(line1, text=f"{idx + 1:02d}",
                 bg=bg_row, fg=MUTED,
                 font=FONT_MONO, width=3, anchor="w"
                 ).pack(side="left")
        state_icon, state_color = {
            "queued":    ("○", MUTED),
            "analyzing": ("⏵", ACCENT_HI),
            "analyzed":  ("✓", OK),
            "failed":    ("✗", ERR),
        }.get(entry.state, ("○", MUTED))
        tk.Label(line1, text=state_icon,
                 bg=bg_row, fg=state_color,
                 font=FONT_UI_B,
                 width=2, anchor="w"
                 ).pack(side="left", padx=(2, 6))
        tk.Label(line1, text=entry.path.name,
                 bg=bg_row, fg=TEXT,
                 font=FONT_UI_B, anchor="w"
                 ).pack(side="left", fill="x", expand=True)

        # Row 2: 元数据 — 11pt Microsoft YaHei UI for legibility
        line2 = tk.Frame(body, bg=bg_row)
        line2.pack(fill="x", anchor="w")
        tk.Frame(line2, bg=bg_row, width=44).pack(side="left")

        sr_kHz = (entry.sr / 1000.0) if entry.sr else 0.0
        meta_parts = []
        if entry.sr:
            meta_parts.append(f"{sr_kHz:.1f}k Hz")
        if entry.duration:
            meta_parts.append(f"{entry.duration:.1f}s")
        if entry.channels:
            meta_parts.append(f"{entry.channels} ch")
        if entry.state == "analyzed" and entry.cells:
            n_str = (f"{entry.cells:,} 网格" if get_language() == "zh"
                     else f"{entry.cells:,} cells")
            meta_parts.append(n_str)
        elif entry.state == "queued":
            meta_parts.append(tr("tracks.unanalyzed"))
        elif entry.state == "analyzing":
            meta_parts.append(tr("status.analyzing"))
        elif entry.state == "failed":
            meta_parts.append(tr("status.failed"))
        meta_text = "  ·  ".join(meta_parts) if meta_parts else "—"
        tk.Label(line2, text=meta_text,
                 bg=bg_row, fg=MUTED,
                 font=FONT_SMALL, anchor="w"
                 ).pack(side="left", fill="x", expand=True)

        # Whole-row click → switch active track
        def _click(_e=None, i=idx):
            self._tracks_set_active(i)
        for w in (outer, body, line1, line2, marker, wave_canvas,
                  *line1.winfo_children(), *line2.winfo_children()):
            w.bind("<Button-1>", _click)

        return outer

    @staticmethod
    def _track_waveform_amps(entry: "TrackEntry", n_buckets: int = 110):
        """Read the wav, peak-bucket into N normalised amplitudes [0,1].
        Returns a numpy array of length n_buckets, or None on I/O error.
        Cached on the entry object so subsequent re-renders are free.

        n_buckets=110 gives 2 px per bar at 220 px canvas width — dense
        enough to look like a real envelope, sparse enough to avoid
        Tkinter's slow per-rect overhead on long file lists.
        """
        cached_amps = getattr(entry, "_waveform_cache", None)
        if isinstance(cached_amps, tuple) and cached_amps[0] == n_buckets:
            return cached_amps[1]
        try:
            import soundfile as sf
            import numpy as np
            data, _sr = sf.read(str(entry.path), dtype="float32",
                                always_2d=True)
            mono = data[:, 0]
            # Coarse pre-downsample: keep ~3 × n_buckets samples per
            # bucket so the max-abs has something to chew on.
            target = max(3000, n_buckets * 4)
            if len(mono) > target:
                step = max(1, len(mono) // target)
                mono = mono[::step]
            if mono.size == 0:
                amps = None
            else:
                buckets = np.array_split(mono, n_buckets)
                amps = np.array([np.max(np.abs(b)) if len(b) else 0.0
                                  for b in buckets], dtype=np.float32)
                m = float(amps.max())
                if m > 0:
                    amps = amps / m
        except Exception:
            amps = None
        entry._waveform_cache = (n_buckets, amps)
        return amps

    @staticmethod
    def _draw_waveform_canvas(canvas: tk.Canvas, amps,
                              w: int, h: int, color: str) -> None:
        """Render a centered vertical-bar waveform onto an existing
        tk.Canvas. Bars are anti-shrunk to a 1.5 px floor so quiet
        passages are still visible (the Unicode-block version flattened
        them to ▁ which looked broken)."""
        canvas.delete("wave")
        n = len(amps)
        if n == 0 or w <= 0:
            return
        bar_w = max(1, int(w / n))
        gap = 1 if bar_w > 1 else 0
        midline = h / 2
        for i in range(n):
            a = float(amps[i])
            # Floor at 1.5 px so silence still draws a thin line —
            # otherwise the canvas looks empty for low-volume passages.
            half = max(1.0, a * (h / 2 - 1)) if a > 0.02 else 1.0
            x0 = i * bar_w
            x1 = x0 + max(1, bar_w - gap)
            canvas.create_rectangle(x0, midline - half,
                                     x1, midline + half,
                                     fill=color, outline="",
                                     tags="wave")

    # NOTE: the old `_track_waveform_blocks` (Unicode-block sketch) was
    # removed in favour of `_track_waveform_amps` + `_draw_waveform_canvas`
    # — block chars rendered as sparse dashes for any audio with a few
    # peaks and a lot of quiet, which is most voice recordings.

    def _tracks_add(self, path: Path) -> int:
        """Append a new TrackEntry and re-render. Returns its index."""
        entry = TrackEntry(path)
        self._tracks.append(entry)
        idx = len(self._tracks) - 1
        # First file → automatically set active. Subsequent files queue.
        if self._active_track < 0:
            self._active_track = idx
        self._tracks_render()
        return idx

    def _tracks_set_active(self, idx: int) -> None:
        """Switch the displayed file. Two cases:
          - target already analyzed → restore its df + re-render heatmap
          - target queued → kick off analysis on it
        """
        if not (0 <= idx < len(self._tracks)):
            return
        prev = self._active_track
        self._active_track = idx
        entry = self._tracks[idx]

        # Sync 'current view' state into the legacy single-file fields
        # so all the existing render paths see the right data.
        self.audio_path = entry.path
        self._last_df = entry.df
        self._last_csv = entry.csv if entry.csv else None
        self.last_csv = entry.csv if entry.csv else None
        self.csv_path_var.set(entry.csv if entry.csv else "—")
        self._last_analysis_time = entry.dt
        if entry.analyzer is not None:
            self._last_analyzer = entry.analyzer

        # Update visual: marker on new active, off on previous
        self._tracks_render()

        # Refresh heatmap / Inspector / status bar from the new active.
        if entry.state == "analyzed" and entry.df is not None:
            try:
                self._refresh_metric_dropdown()
                col = self.metric_var.get()
                if col and col in entry.df.columns:
                    self._render_metric(col)
                self._update_inspector()
                self._update_statusbar()
            except Exception:
                pass
        elif entry.state == "queued":
            # Start analysis in background
            self._start_analysis(entry.path)
        # 'analyzing' / 'failed' — leave UI in placeholder/error state

    def _track_for_path(self, path: Path) -> TrackEntry | None:
        for e in self._tracks:
            try:
                if e.path == path:
                    return e
            except Exception:
                continue
        return None

    def _build_metric_bar(self, parent):
        """Metric Bar: 显示当前 metric + 切换提示 + 视觉指示。
        实际切换走顶部菜单栏（参数→分类→item）或键盘 ← →。"""
        bar = tk.Frame(parent, bg=PANEL)
        bar.pack(side="top", fill="x")

        inner = tk.Frame(bar, bg=PANEL)
        inner.pack(fill="x", padx=16, pady=6)   # was 8 — slim chrome

        self._metric_label = tk.Label(inner, text=tr("metric_bar.label"),
                                       bg=PANEL, fg=ACCENT, font=FONT_UI_B)
        self._metric_label.pack(side="left", padx=(0, 12))

        # Current-metric pill — flat label-style button. Kept as widget
        # name `metric_btn` for back-compat with existing code paths
        # (_refresh_metric_dropdown / _cycle_metric / popup).
        self.metric_btn = tk.Button(inner, textvariable=self.metric_var,
                                    bg=PANEL_HI, fg=TEXT,
                                    activebackground=BORDER, activeforeground=TEXT,
                                    disabledforeground=MUTED,
                                    font=FONT_UI_B, bd=0, relief="flat",
                                    padx=14, pady=4, width=20,
                                    cursor="hand2",
                                    command=self._popup_metric_menu)
        self.metric_btn.pack(side="left")
        self.metric_btn.config(state="disabled")

        # Nav hint
        self._metric_nav_hint = tk.Label(inner, text=tr("metric_bar.nav_hint"),
                                          bg=PANEL, fg=MUTED, font=FONT_UI)
        self._metric_nav_hint.pack(side="left", padx=(16, 0))

        self._metric_popup = None
        self.metric_menu = None
        self.metric_var.trace_add("write", self._on_metric_change)

    def _build_inspector(self, parent):
        """Inspector right column per docs/UI_DESIGN.md option-C spec.

        Top-to-bottom:
          • SCROLLABLE: metric name + description + unit + clinical bands
          • PINNED:     current value card (hover-driven, always visible)
          • PINNED:     action buttons (导出 Excel / 生成报告 / 对比录音)

        The current-value card is pinned (not in the scroll area) so the
        user always sees the cell readout without scrolling, even at the
        minsize window. Clinical bands above can scroll if they overflow.
        """
        # ── Bottom: action buttons (pinned, packed first with side="bottom") ─
        actions = tk.Frame(parent, bg=PANEL)
        actions.pack(side="bottom", fill="x", padx=14, pady=(8, 14))

        self._inspect_btn_excel = ttk.Button(
            actions, text=tr("inspector.btn.excel"),
            style="Ghost.TButton", command=self._export_excel)
        self._inspect_btn_excel.pack(fill="x", pady=2)
        self._inspect_btn_report = ttk.Button(
            actions, text=tr("inspector.btn.report"),
            style="Ghost.TButton", command=self._export_report)
        self._inspect_btn_report.pack(fill="x", pady=2)
        self._inspect_btn_compare = ttk.Button(
            actions, text=tr("inspector.btn.compare"),
            style="Ghost.TButton", command=self._open_compare_dialog)
        self._inspect_btn_compare.pack(fill="x", pady=2)

        # 1 px BORDER divider above the actions row
        sep_actions = tk.Frame(parent, bg=BORDER, height=1)
        sep_actions.pack(side="bottom", fill="x", padx=8, pady=(0, 0))

        # ── PINNED: Current-value card lives just above actions, NOT in
        # the scroll area, so it's always visible regardless of window
        # size or how far the user has scrolled the clinical bands.
        self._inspector_value_card = tk.Frame(
            parent, bg=PANEL_HI,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=BORDER)
        self._inspector_value_card.pack(side="bottom", fill="x",
                                         padx=14, pady=(0, 8))
        # Per docs/UI_DESIGN.md spec: 大数字 Consolas 24pt bold ACCENT_HOVER +
        # 单位 10pt MUTED + 状态标 11pt bold 语义色. We use FONT_MONO_B (22pt
        # bold) close enough to spec — restoring the visual weight the
        # design called for. Inner padding 8 px gives the pill enough air
        # while keeping total height ≤ ~190 px.
        vc_inner = tk.Frame(self._inspector_value_card, bg=PANEL_HI)
        vc_inner.pack(fill="x", padx=12, pady=8)
        self._inspector_value_header = tk.Label(
            vc_inner, text=tr("inspector.current"),
            bg=PANEL_HI, fg=ACCENT, font=FONT_UI_B)
        self._inspector_value_header.pack(anchor="w", pady=(0, 2))
        self._inspector_value_coords = tk.Label(
            vc_inner, text="—",
            bg=PANEL_HI, fg=MUTED, font=FONT_UI)
        self._inspector_value_coords.pack(anchor="w")
        big = tk.Frame(vc_inner, bg=PANEL_HI)
        big.pack(anchor="w", pady=(2, 0))
        self._inspector_value_num = tk.Label(
            big, text="—",
            bg=PANEL_HI, fg=ACCENT_HI,
            font=FONT_MONO_B)   # 22pt bold — per UI_DESIGN.md FONT_HUGE
        self._inspector_value_num.pack(side="left")
        self._inspector_value_unit = tk.Label(
            big, text="",
            bg=PANEL_HI, fg=MUTED, font=FONT_UI)
        self._inspector_value_unit.pack(side="left", padx=(6, 0), pady=(8, 0))
        self._inspector_value_sev = tk.Label(
            vc_inner, text="",
            bg=PANEL_HI, fg=MUTED, font=FONT_UI_B)
        self._inspector_value_sev.pack(anchor="w", pady=(4, 0))

        # ── Top: metric details (plain pack, no scrollable canvas)
        # `fill="both", expand=True` is critical: pad gets all the
        # vertical room left after the pinned value pill + actions
        # claim their natural height. Without expand=True, pad would
        # only get its reqheight, and any overflow would be clipped
        # invisibly — that's the bug the user hit at 1280x800.
        # With the default window now 1500×1000, a worst-case 5-band
        # metric (~830 px content) fits without clipping.
        pad = tk.Frame(parent, bg=PANEL)
        pad.pack(side="top", fill="both", expand=True, padx=14, pady=14)

        # Metric name (large) + small ⓘ glyph — the glyph is the visible
        # cue that hovering reveals a detailed tooltip. Long names like
        # 'SpectralBandwidth' / 'HammarbergIndex' overflowed at 22pt bold
        # under high-DPI Windows scaling, so we shrink to 19pt bold —
        # keeps the strong visual hierarchy spec called for while
        # leaving headroom for the longest name.
        title_row = tk.Frame(pad, bg=PANEL)
        title_row.pack(anchor="w", fill="x")
        self._inspector_metric_name = tk.Label(
            title_row, text="—",
            bg=PANEL, fg=ACCENT,
            font=("Microsoft YaHei UI", 19, "bold"),
            anchor="w", justify="left",
            cursor="question_arrow")
        self._inspector_metric_name.pack(side="left", fill="x", expand=True)
        # ⓘ next to the title — small, muted; positioned to the right of
        # the metric name so users immediately know "hover for more".
        self._inspector_info_glyph = tk.Label(
            title_row, text="ⓘ",
            bg=PANEL, fg=MUTED,
            font=("Microsoft YaHei UI", 14),
            cursor="question_arrow")
        self._inspector_info_glyph.pack(side="right", padx=(4, 0), pady=(8, 0))

        # Hover tooltip on the metric name — uses metric.tooltip.X (long
        # detailed prose) if present, falls back to metric.desc.X
        # (the short blurb shown right under the name).
        def _metric_tooltip_text() -> str:
            name = self.metric_var.get() if hasattr(self, "metric_var") else ""
            if not name:
                return ""
            tip_key = f"metric.tooltip.{name}"
            tip = tr(tip_key)
            if tip == tip_key:
                short_key = f"metric.desc.{name}"
                tip = tr(short_key)
                if tip == short_key:
                    tip = ""
            return tip
        # Attach tooltip to BOTH the name label and the ⓘ glyph so users
        # can hover either to trigger it.
        self._inspector_metric_tip = HoverTooltip(
            self._inspector_metric_name, _metric_tooltip_text)
        self._inspector_metric_tip.attach()
        self._inspector_info_glyph_tip = HoverTooltip(
            self._inspector_info_glyph, _metric_tooltip_text)
        self._inspector_info_glyph_tip.attach()

        self._inspector_metric_desc = tk.Label(
            pad, text=tr("inspector.no_metric"),
            bg=PANEL, fg=TEXT_SEC, font=FONT_UI,
            wraplength=370, justify="left", anchor="w")   # was 300, inspector now 420 wide
        self._inspector_metric_desc.pack(anchor="w", pady=(2, 0), fill="x")

        # Unit hint (own row, small muted)
        self._inspector_unit_lbl = tk.Label(
            pad, text="",
            bg=PANEL, fg=MUTED, font=FONT_CAPTION,
            anchor="w")
        self._inspector_unit_lbl.pack(anchor="w", pady=(2, 12), fill="x")

        # Clinical reference card — content rebuilt by _inspector_set_clinical
        self._inspector_cards = tk.Frame(pad, bg=PANEL)
        self._inspector_cards.pack(fill="x", pady=(0, 8))

        # ── Hidden log_text widget kept alive for compatibility ──────
        # _append_log writes to it; LogWindow mirrors it. Keeping it
        # parented inside Inspector but never packed avoids breaking
        # all the existing _append_log call sites.
        log_holder = tk.Frame(parent, bg=PANEL, width=0, height=0)
        # Don't pack — invisible.
        self.log_text = tk.Text(log_holder, bg="#0b1117", fg=TEXT,
                                font=FONT_MONO,
                                bd=0, highlightthickness=0,
                                state="disabled", height=1, width=1)
        # log_text has tag config below; no packing means it doesn't
        # render but accepts insertions.
        self.log_text.tag_configure("INFO",    foreground=TEXT)
        self.log_text.tag_configure("DEBUG",   foreground=MUTED)
        self.log_text.tag_configure("WARNING", foreground=WARN)
        self.log_text.tag_configure("ERROR",   foreground=ERR)
        self.log_text.tag_configure("OK",      foreground=OK)
        self.log_text.tag_configure("META",    foreground=ACCENT)
        # _log_lbl is no longer in the UI; set a stub for the
        # _on_language_changed re-render hook.
        self._log_lbl = None

    def _build_status_bar(self, parent):
        """底部 status bar：左 = 当前文件元信息 + 网格数 + 耗时；右 = 版权。
        height=34 (was 28) — at higher-DPI Windows scaling, FONT_UI 11pt
        descenders were getting clipped at the bottom edge of the 28 px
        bar; 34 gives Microsoft YaHei UI's full glyph height + padding."""
        bar = tk.Frame(parent, bg=PANEL, height=34)
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)

        inner = tk.Frame(bar, bg=PANEL)
        inner.pack(fill="x", padx=16, pady=6)

        self._statusbar_left = tk.Label(inner, text=tr("statusbar.no_file"),
                                         bg=PANEL, fg=MUTED, font=FONT_UI)
        self._statusbar_left.pack(side="left")

        from voicemap.__version__ import __version__
        self._statusbar_right = tk.Label(inner,
                                          text=tr("statusbar.copyright", ver=__version__),
                                          bg=PANEL, fg=MUTED, font=FONT_UI)
        self._statusbar_right.pack(side="right")

    def _build_canvas_area(self, parent):
        """中央画布 + 左右 nav 箭头。父容器 (canvas_frame) 已经在
        _build_ui 里设好 PANEL 背景 + 边框。"""
        # Plot toolbar / centroid bar 都搬到顶部菜单栏了，对应 widget
        # 引用全置 None；旧代码里 .state() / .configure() / 位置查询
        # 已加守卫。
        self.cent_save_btn   = None
        self.cent_status_lbl = None
        self.fit_btn         = None
        self.annot_btn       = None
        self.save_btn        = None

        from voicemap.plot_overlay import OverlayManager
        self._overlay_mgr = OverlayManager()
        self._annot_mode_on = False
        self._annot_canvas_cid = None

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
        # Mouse hover over the heatmap → live update Inspector's
        # current-value pill with the cell at (MIDI, SPL).
        self._canvas.mpl_connect("motion_notify_event",
                                  self._on_canvas_motion)
        self._canvas.mpl_connect("axes_leave_event",
                                  lambda _e: self._update_inspector_value(None, None))

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

        # Menu accelerators: the popup labels show these (Ctrl+O / Ctrl+S /
        # Ctrl+C / Ctrl+,) so the bindings should actually work. Use
        # bind_all so they fire regardless of focused widget except when
        # an Entry / Text has focus and would consume the key naturally.
        def _shortcut_guard(action):
            def _wrapped(event):
                cls = event.widget.winfo_class() if event.widget else ""
                if cls in ("Entry", "Text", "TEntry", "Spinbox", "TSpinbox"):
                    return
                action()
                return "break"
            return _wrapped

        self.bind_all("<Control-o>", _shortcut_guard(self._pick_audio))
        self.bind_all("<Control-s>", _shortcut_guard(self._open_save_menu))
        self.bind_all("<Control-c>", _shortcut_guard(self._copy_canvas))
        self.bind_all("<Control-comma>", _shortcut_guard(self._open_settings))
        self.bind_all("<Control-l>", _shortcut_guard(self._open_log_window))

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
            self._append_log("WARNING", tr("log.dnd_failed", e=e))

    def _on_drop(self, event):
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]

        wavs = [p for p in paths if str(p).lower().endswith(".wav")]
        if not wavs:
            self._append_log("WARNING", tr("log.ignored_non_wav"))
            return
        # Multi-file: queue all dropped wavs into Tracks Panel. First
        # one auto-analyses; subsequent ones wait for click.
        for w in wavs:
            self._on_audio_dropped(str(w))

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
    def _show_placeholder(self, msg: str | None = None):
        if msg is None:
            msg = tr("drop.placeholder")
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
        # askopenfilenames (plural) lets the user select 1+ wavs in one go.
        paths = filedialog.askopenfilenames(
            title=tr("fd.pick_audio"),
            filetypes=[(tr("fd.filter.wav"), "*.wav"),
                       (tr("fd.filter.all"), "*.*")])
        if not paths:
            return
        for path in paths:
            self._on_audio_dropped(path)

    def _on_audio_dropped(self, path) -> None:
        """Add a file to the Tracks Panel. First file becomes active and
        gets analyzed automatically; later files are appended in 'queued'
        state and only analyzed when the user clicks them."""
        p = Path(path)
        # If already in tracks, just switch to it
        existing = self._track_for_path(p)
        if existing is not None:
            idx = self._tracks.index(existing)
            self._tracks_set_active(idx)
            return
        idx = self._tracks_add(p)
        # Auto-analyze only when this is the first track loaded
        if len(self._tracks) == 1:
            self._tracks_set_active(idx)

    def _pick_output_dir(self):
        path = filedialog.askdirectory(title=tr("fd.pick_outdir"),
                                       initialdir=self.output_dir_var.get())
        if path:
            self.output_dir_var.set(path)

    def _start_analysis(self, audio_path: str):
        if self._worker and self._worker.is_alive():
            return

        p = Path(audio_path)
        if not p.exists():
            self._append_log("ERROR", tr("log.no_file", path=audio_path))
            return

        out_dir = self.output_dir_var.get().strip()
        if not out_dir:
            self._append_log("ERROR", tr("log.no_outdir"))
            return
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        # 清日志
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._log_count = 0

        self.audio_path = p
        # The drop_zone label updates only matter for the empty-state
        # text — in multi-file mode the active row already shows the
        # filename. Try to update them but don't crash when the drop
        # zone has been hidden.
        try:
            self.drop_label.configure(text=p.name, fg=ACCENT)
            self.drop_sub.configure(text=str(p.parent))
        except tk.TclError:
            pass
        # Mark the matching TrackEntry as analyzing
        entry = self._track_for_path(p)
        if entry is not None:
            entry.state = "analyzing"
            self._tracks_render()
        # Reset analysis-derived state and refresh status bar
        self._last_df = None
        self._last_analysis_time = 0.0
        self._update_statusbar()
        self._update_inspector()

        self.metric_btn.config(state="disabled")
        if self.open_csv_btn is not None: self.open_csv_btn.state(["disabled"])
        if self.progress is not None: self.progress.start(12)
        self._set_status(tr("status.analyzing"), ACCENT, key="status.analyzing")
        self._show_placeholder(tr("status.analyzing"))

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

                import time as _time
                _t0 = _time.perf_counter()
                data, out_file, grouped = analyzer.analyze_and_output_vrp(
                    audio, return_df=True, plot_mode=plot_mode_snap,
                    progress_cb=prog, partial_cb=partial)
                self._msg_q.put(("done", True, {
                    "df": grouped,
                    "csv": out_file,
                    "points": len(data["midi"]),
                    "analyzer": analyzer,
                    "dt": _time.perf_counter() - _t0,
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
        if self.progress is not None: self.progress.stop()
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
            if self.open_csv_btn is not None: self.open_csv_btn.state(["!disabled"])
            try:
                if self.excel_btn is not None: self.excel_btn.state(["!disabled"])
                if self.report_btn is not None: self.report_btn.state(["!disabled"])
            except (AttributeError, tk.TclError):
                pass
            # 有了 analyzer 就能保存 centroid
            try:
                if self.cent_save_btn is not None: self.cent_save_btn.state(["!disabled"])
            except (AttributeError, tk.TclError):
                pass
            # M2 plot toolbar (拟合 / 标注 / 保存 / 复制) — 分析完才能用
            self._enable_plot_toolbar()
            self._set_status(tr("status.done", n=f"{payload['points']:,}"), OK, key="status.done", n=f"{payload['points']:,}")
            self._append_log("META", f"✓ {payload['csv']}")
            # Track analysis time so the status bar can show it.
            self._last_analysis_time = float(payload.get("dt", 0.0))
            # Update the matching TrackEntry with cached results
            entry = self._track_for_path(self.audio_path)
            if entry is not None:
                entry.state = "analyzed"
                entry.df = payload["df"]
                entry.csv = payload["csv"]
                entry.analyzer = payload.get("analyzer")
                entry.dt = self._last_analysis_time
                entry.cells = len(payload["df"])
                try:
                    entry.cycles = int(payload["df"]["Total"].sum())
                except Exception:
                    entry.cycles = 0
                self._tracks_render()
            self._refresh_metric_dropdown()
            self._update_statusbar()
            self._update_inspector()
        else:
            self._set_status(tr("status.failed"), ERR, key="status.failed")
            self._append_log("ERROR", payload["error"])
            self._show_placeholder(tr("placeholder.failed"))
            entry = self._track_for_path(self.audio_path) if self.audio_path else None
            if entry is not None:
                entry.state = "failed"
                self._tracks_render()
            self._update_statusbar()

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

        # 同步 menubar：每个 section 内逐项视觉变亮 / 变灰。
        # 用 foreground 而不是 state="disabled" 是为避开 Windows 浮雕
        # 幻影（见 _build_menubar 注释）。
        if hasattr(self, "_metric_section_menus"):
            for section_title, (menu, entries) in self._metric_section_menus.items():
                avail_set = set()
                for st, cols in sections_avail:
                    if st == section_title:
                        avail_set = set(cols)
                        break
                for name, idx in entries:
                    menu.entryconfig(
                        idx, foreground=(TEXT if name in avail_set else MUTED))

        if not flat:
            self.metric_btn.config(state="disabled")
            self._set_nav_visible(False)
            self._show_placeholder(tr("placeholder.no_metric"))
            return

        self.metric_btn.config(state="normal")
        self._set_nav_visible(len(flat) > 1)
        default = next((m for m in _DEFAULT_METRIC_CHAIN if m in flat), flat[0])
        self.metric_var.set(default)   # trace → _on_metric_change → _render

    def _on_canvas_motion(self, event):
        """matplotlib motion handler — live-update Inspector's
        current-value pill with the cell under the cursor.

        Skip when:
          - mouse is outside the data axes
          - placeholder is showing (no data)
          - in annotation mode (don't fight the annotation cursor)
        """
        if event.inaxes is None:
            return
        if getattr(self, "_showing_placeholder", True):
            return
        if getattr(self, "_annot_mode_on", False):
            return
        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return
        self._update_inspector_value(x, y)

    def _on_metric_change(self, *_):
        col = self.metric_var.get()
        if col and self._last_df is not None and col in self._last_df.columns:
            self._render_metric(col)
        # Always refresh the Inspector so it tracks the metric var even
        # before any data is loaded (just shows name + description).
        self._update_inspector()

    def _update_inspector(self):
        """Refresh the Inspector column to reflect current metric_var.
        Shows static parts: metric name + description + clinical bands.
        Current value pill is updated separately by mouse hover via
        ``_update_inspector_value``. Mean over the whole heatmap is
        meaningless on a 2D voice map, so we don't compute it here.
        """
        name = self.metric_var.get() if hasattr(self, "metric_var") else ""
        if not hasattr(self, "_inspector_metric_name"):
            return    # Inspector not built yet
        if not name:
            self._inspector_metric_name.configure(text="—")
            self._inspector_metric_desc.configure(text=tr("inspector.no_metric"))
            self._inspector_set_clinical(None)
            self._update_inspector_value(None, None)
            return

        try:
            from voicemap.metrics_registry import get as get_spec
            spec = get_spec(name)
        except Exception:
            spec = None
        # tr(f"metric.desc.{name}") looks up the i18n table; if neither
        # zh nor en has the key, tr() returns the bare key — in that case
        # fall back to the registry's English description so an
        # un-translated metric still shows something readable.
        key = f"metric.desc.{name}"
        desc = tr(key)
        if desc == key:                       # no entry in either language
            desc = (spec.description if spec else "") or "—"
        unit = (spec.unit if spec else "") or ""
        self._inspector_metric_name.configure(text=name)
        self._inspector_metric_desc.configure(text=desc)
        # Unit on its own row (per spec mockup)
        if unit:
            self._inspector_unit_lbl.configure(
                text=f"{tr('inspector.unit')}: {unit}")
        else:
            self._inspector_unit_lbl.configure(text="")

        from voicemap.report import _THRESHOLDS
        bands = _THRESHOLDS.get(name)
        self._inspector_set_clinical(bands)
        self._update_inspector_value(None, None)

    # Severity → color mapping
    _SEVERITY_COLORS = {
        "good":     None,      # set in method to OK
        "normal":   None,
        "watch":    None,
        "abnormal": None,
    }

    def _inspector_set_clinical(self, bands):
        """Replace clinical-band rows in self._inspector_cards.
        Static; only re-runs on metric change."""
        if not hasattr(self, "_inspector_cards"):
            return
        for child in self._inspector_cards.winfo_children():
            try:
                child.destroy()
            except tk.TclError:
                pass

        sev_color = {"good": OK, "normal": TEXT, "watch": WARN, "abnormal": ERR}

        if not bands:
            return
        tk.Label(self._inspector_cards, text=tr("inspector.clinical"),
                 bg=PANEL, fg=ACCENT, font=FONT_UI_B
                 ).pack(anchor="w", pady=(8, 4))
        for lo, hi, label, sev in bands:
            row = tk.Frame(self._inspector_cards, bg=PANEL)
            row.pack(fill="x", pady=1)
            if lo <= -1e8:
                rng = f"< {hi:g}"
            elif hi >= 1e8:
                rng = f"≥ {lo:g}"
            else:
                rng = f"{lo:g} – {hi:g}"
            # range column: width=14 (was 10) so values like '0.13 – 0.19'
            # (with U+2013 en-dash) fit without overlapping the next
            # column. Sidebar+padx=14 leaves the label column ~290 px
            # which still fits all _THRESHOLDS labels in zh.
            tk.Label(row, text=rng, bg=PANEL, fg=TEXT,
                     font=("Consolas", 9), width=14, anchor="w"
                     ).pack(side="left")
            # No wraplength — Inspector is 360 px wide, range column eats
            # ~75 px, leaving ~250 px for the label, which is enough for
            # every band label in _THRESHOLDS to render on a single line.
            # wraplength=200 was wrapping unnecessarily (200 < 250) and
            # blowing each row to 2-3 lines = ~66 px each. One line is 36 px,
            # cutting cards reqheight from ~330 px to ~220 px.
            tk.Label(row, text=label, bg=PANEL,
                     fg=sev_color.get(sev, TEXT), font=FONT_UI,
                     anchor="w", justify="left"
                     ).pack(side="left", fill="x", expand=True)

    def _update_inspector_value(self, midi: float | None, spl: float | None):
        """Cheap update of the current-value pill from the cell at
        (midi, spl). Called from the matplotlib motion handler at high
        rate, so it just .configure()s existing widgets — no destroy
        / recreate. Pass (None, None) to clear."""
        if not hasattr(self, "_inspector_value_num"):
            return

        sev_color = {"good": OK, "normal": TEXT, "watch": WARN, "abnormal": ERR}
        sev_label = {"good": "✓", "normal": "·", "watch": "!", "abnormal": "✗"}

        # Clear path
        if midi is None or spl is None:
            self._inspector_value_coords.configure(text="—")
            self._inspector_value_num.configure(text="—", fg=ACCENT_HI)
            self._inspector_value_unit.configure(text="")
            self._inspector_value_sev.configure(text="")
            return

        name = self.metric_var.get()
        if not name or self._last_df is None or name not in self._last_df.columns:
            self._inspector_value_coords.configure(text="—")
            self._inspector_value_num.configure(text="—", fg=ACCENT_HI)
            self._inspector_value_sev.configure(text="")
            return

        # Find nearest cell in _last_df (rows are unique (MIDI, dB) pairs).
        try:
            df = self._last_df
            mi = int(round(midi))
            si = int(round(spl))
            row = df[(df["MIDI"] == mi) & (df["dB"] == si)]
            if row.empty:
                self._inspector_value_coords.configure(
                    text=tr("inspector.coords_no_data", mi=mi, si=si))
                self._inspector_value_num.configure(text="—", fg=ACCENT_HI)
                self._inspector_value_sev.configure(text="")
                return
            value = float(row[name].iloc[0])
        except Exception:
            return

        # Severity lookup
        try:
            from voicemap.report import _THRESHOLDS
            bands = _THRESHOLDS.get(name)
        except Exception:
            bands = None
        sev = None
        if bands:
            for lo, hi, _label, s in bands:
                if lo <= value < hi:
                    sev = s
                    break
        try:
            from voicemap.metrics_registry import get as get_spec
            spec = get_spec(name)
            unit = (spec.unit if spec else "") or ""
        except Exception:
            unit = ""

        color = sev_color.get(sev, ACCENT_HI)
        self._inspector_value_coords.configure(
            text=tr("inspector.coords", mi=mi, si=si))
        self._inspector_value_num.configure(text=f"{value:.2f}", fg=color)
        self._inspector_value_unit.configure(text=unit)
        if sev is not None:
            # severity word goes through tr() so it shows 优/正常/注意/异常
            # in zh and good/normal/watch/abnormal in en
            self._inspector_value_sev.configure(
                text=f"{sev_label[sev]}  {tr(f'severity.{sev}')}", fg=color)
        else:
            self._inspector_value_sev.configure(text="")

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
                    selectcolor=ACCENT, borderwidth=0, relief="flat", activeborderwidth=0)
        # 持有 cascade 子菜单的引用 —— Tk 的 add_cascade 不会持有 menu
        # 对象的 Python 引用，函数返回后 sub 被 GC，下拉就空了。
        self._popup_submenus = []
        for section_title, cols in sa:
            sub = tk.Menu(m, tearoff=0,
                          bg=PANEL_HI, fg=TEXT,
                          activebackground=ACCENT, activeforeground=BG,
                          selectcolor=ACCENT, borderwidth=0, relief="flat", activeborderwidth=0)
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
                self._show_placeholder(tr("placeholder.no_cell", thr=thr))
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
            self._show_placeholder(tr("placeholder.no_data", col=col))
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
            return tr("centroid.status.loaded", name=name, k=k)
        return tr("centroid.status.untrained")

    def _load_centroids(self):
        path = filedialog.askopenfilename(
            title=tr("fd.pick_centroid"),
            filetypes=[(tr("fd.filter.csv"), "*.csv"), (tr("fd.filter.all"), "*.*")])
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
            self._append_log("META", tr("log.centroid_loaded", name=Path(path).name, k=cent.shape[0]))
            self._refresh_centroid_status()
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", tr("log.centroid_load_fail", e=e))

    def _train_centroids_from_many(self):
        """Pick multiple wavs → pool EGG features → one K-means → save CSV.
        Produces centroids that yield consistent cluster labels across all
        recordings analysed against them (cross-subject studies)."""
        if self._worker and self._worker.is_alive():
            self._append_log("WARNING", tr("log.train_busy"))
            return
        paths = filedialog.askopenfilenames(
            title=tr("fd.pick_train_wavs"),
            filetypes=[(tr("fd.filter.wav"), "*.wav"), (tr("fd.filter.all"), "*.*")])
        if not paths:
            return
        paths = [str(Path(p)) for p in paths if str(p).lower().endswith(".wav")]
        if not paths:
            self._append_log("WARNING", tr("log.no_wav_picked"))
            return
        out_csv = filedialog.asksaveasfilename(
            title=tr("fd.save_centroid"),
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="cEGG_joint.csv")
        if not out_csv:
            return

        # Modal progress dialog (reuse ProgressDialog shell)
        dlg = ProgressDialog(self, tr("progress.train_n_wavs", n=len(paths)))
        self._progress_dialog = dlg
        dlg.set_status(tr("progress.training"))

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
            if self.cent_save_btn is not None: self.cent_save_btn.state(["!disabled"])
            self._refresh_centroid_status()
            self._append_log("META",
                             tr("log.train_done",
                                n=payload['n_wavs'],
                                file=Path(payload['csv']).name))
            self._append_log("INFO", tr("log.train_loaded"))
        else:
            self._append_log("ERROR", payload["error"])

    def _save_centroids(self):
        if self._last_analyzer is None:
            self._append_log("WARNING", tr("log.no_centroid"))
            return
        path = filedialog.asksaveasfilename(
            title=tr("fd.save_centroid_one"),
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="cEGG.csv")
        if not path:
            return
        try:
            self._last_analyzer.save_centroids(path)
            self._append_log("META", tr("log.centroid_saved", name=Path(path).name))
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", tr("log.centroid_save_fail", e=e))

    def _refresh_centroid_status(self):
        # 顶栏状态
        try:
            (self.cent_status_lbl.configure(text=self._centroid_status_text() if self.cent_status_lbl is not None else None))
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

    def _update_statusbar(self):
        """Reflect current data state in the bottom status bar (option-C).
        Spec: ``● 文件 · N 网格 · k=K · M 个周期 · 耗时 X.Xs``."""
        if not hasattr(self, "_statusbar_left"):
            return
        path = getattr(self, "audio_path", None)
        df = getattr(self, "_last_df", None)
        if path is None:
            text = tr("statusbar.no_file")
        else:
            n = len(df) if df is not None else 0
            dt = getattr(self, "_last_analysis_time", 0.0)
            # k = current cluster count (analyzer's setting, falls back to var)
            try:
                k = int(self.cluster_k_var.get())
            except Exception:
                k = 5
            cycles = 0
            if df is not None and "Total" in df.columns:
                try:
                    cycles = int(df["Total"].sum())
                except Exception:
                    cycles = 0
            if cycles > 0:
                text = tr("statusbar.file_meta_full",
                          name=path.name, n=n, k=k,
                          cycles=f"{cycles:,}", dt=dt)
            else:
                # File loaded, not yet analyzed.
                text = tr("statusbar.file_meta", name=path.name, n=n, dt=dt)
        try:
            self._statusbar_left.configure(text=text)
        except tk.TclError:
            pass

    def _set_status(self, text: str, color: str = MUTED, *,
                     key: str | None = None, **kwargs):
        """Update the top-right status pill.

        ``text`` is the rendered string (already translated by caller).
        For lang-switch survival, callers should also pass ``key=`` and
        the kwargs that produced the text — _on_language_changed will
        re-render via tr(key, **kwargs) when the user switches language.
        """
        self.status_lbl.configure(text=text, fg=color)
        self.status_dot.configure(fg=color)
        if key is not None:
            self._status_key = key
            self._status_kwargs = kwargs
        # Persist color too, so language re-render keeps the same hue.
        self._status_color = color

    def _enable_plot_toolbar(self):
        """No-op since A0-3: plot toolbar is removed in favour of the
        menubar entries (编辑 + 视图). Kept as a method so existing
        callers don't error out; can be deleted entirely after one
        more pass."""
        return

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
                    font="TkMenuFont", bd=0, relief="flat", activeborderwidth=0)
        m.add_command(label=tr("fit.header"), state="disabled",
                      foreground=ACCENT)
        m.add_separator()
        m.add_command(label=tr("fit.center_linear"),
                      command=lambda: self._apply_fit("center", "linear"))
        m.add_command(label=tr("fit.center_poly"),
                      command=lambda: self._apply_fit("center", "polynomial"))
        m.add_command(label=tr("fit.center_spline"),
                      command=lambda: self._apply_fit("center", "spline"))
        m.add_command(label=tr("fit.center_lowess"),
                      command=lambda: self._apply_fit("center", "lowess"))
        m.add_separator()
        m.add_command(label=tr("fit.trend_poly"),
                      command=lambda: self._apply_fit("trend", "polynomial"))
        m.add_command(label=tr("fit.trend_lowess"),
                      command=lambda: self._apply_fit("trend", "lowess"))
        m.add_separator()
        m.add_command(label=tr("fit.clear"),
                      command=self._clear_overlays)
        try:
            # fit_btn 已移除（toolbar 整片删了），改在鼠标当前位置弹出
            x, y = self.winfo_pointerxy()
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
        self._append_log("META", tr("log.overlay_applied", kind=kind, method=method))

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
            pass  # annot_btn removed; menu reflects state via 编辑→标注 (TODO: checkmark)
            cw.configure(cursor="")
        else:
            # Turn on — next plot click prompts for text
            self._annot_mode_on = True
            pass  # annot_btn removed; annotation mode is tracked via self._annot_mode_on
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
            tr("annotate.title"), tr("annotate.prompt", x=x_data, y=y_data),
            parent=self)
        if not text:
            return
        from voicemap.plot_overlay import add_annotation
        ax = event.inaxes
        artists = add_annotation(ax, x_data, y_data, text)
        self._overlay_mgr.add(artists)
        self._canvas.draw_idle()
        self._append_log("META", tr("log.annotated", x=x_data, y=y_data, text=text))
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
                    font="TkMenuFont", bd=0, relief="flat", activeborderwidth=0)
        m.add_command(label=tr("save.header"), state="disabled",
                      foreground=ACCENT)
        m.add_separator()
        for desc, ext in SAVE_FORMATS:
            m.add_command(label=f"  {desc} (.{ext})",
                          command=lambda e=ext, d=desc: self._save_canvas(e, d))
        try:
            # save_btn 已移除，鼠标位置弹出
            x, y = self.winfo_pointerxy()
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def _save_canvas(self, fmt: str, desc: str = ""):
        col = self.metric_var.get() or "voice_map"
        from voicemap.plot_overlay import save_figure
        from tkinter import filedialog
        default = f"{Path(self.last_csv).stem if self.last_csv else 'voice_map'}_{col}.{fmt}"
        path = filedialog.asksaveasfilename(
            title=tr("fd.save_image", desc=desc),
            defaultextension=f".{fmt}",
            filetypes=[(desc, f"*.{fmt}")],
            initialfile=default,
            initialdir=str(Path(self.output_dir_var.get())))
        if not path:
            return
        try:
            save_figure(self._fig, path, fmt=fmt, dpi=300)
            self._append_log("META", tr("log.image_saved", path=path))
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", tr("log.save_fail", e=e))

    def _copy_canvas(self):
        from voicemap.plot_overlay import copy_figure_to_clipboard
        if self._last_df is None or self._showing_placeholder:
            return
        ok = copy_figure_to_clipboard(self._fig)
        if ok:
            self._append_log("META", tr("log.copied_clipboard"))
        else:
            self._append_log("ERROR",
                              tr("log.copy_fail"))

    # ────────────────────────────────────────────────────────────────────
    def _open_compare_dialog(self):
        """A | B | A-B comparison on two previously-written VRP CSVs."""
        CompareDialog(self)

    def _open_with_default_app(self, path):
        """Open `path` with the OS default application."""
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", tr("log.open_fail", path=path, e=e))

    def _reveal_in_folder(self, path):
        """Open the parent directory of `path` in the OS file manager.
        On Windows uses /select so the file itself is highlighted."""
        p = Path(path)
        try:
            if sys.platform.startswith("win"):
                # explorer /select, "C:\full\path\file" highlights the file
                subprocess.Popen(["explorer", "/select,", str(p)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p.parent)])
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", tr("log.open_fail", path=p.parent, e=e))

    def _post_export_prompt(self, path: str):
        """After a successful export, ask the user what to do with the
        file: open it / show in folder / dismiss. A small modal Toplevel
        that mirrors ModernPopup styling. Per user spec — auto-opening
        is too aggressive when the user just wanted the file saved."""
        from voicemap.gui.theme import (
            BG, PANEL, PANEL_HI, BORDER, TEXT, ACCENT, ACCENT_HI, MUTED,
            FONT_UI, FONT_UI_B,
        )
        dlg = tk.Toplevel(self)
        dlg.title(tr("export.done.title"))
        dlg.configure(bg=PANEL)
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.grab_set()

        body = tk.Frame(dlg, bg=PANEL)
        body.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(body, text=tr("export.done.heading"),
                 bg=PANEL, fg=ACCENT, font=FONT_UI_B,
                 anchor="w").pack(fill="x", pady=(0, 4))
        tk.Label(body, text=Path(path).name,
                 bg=PANEL, fg=TEXT, font=FONT_UI_B,
                 anchor="w").pack(fill="x")
        tk.Label(body, text=str(Path(path).parent),
                 bg=PANEL, fg=MUTED, font=FONT_UI,
                 anchor="w", wraplength=460,
                 justify="left").pack(fill="x", pady=(0, 12))

        btns = tk.Frame(body, bg=PANEL)
        btns.pack(fill="x")

        def _open_file():
            dlg.destroy()
            self._open_with_default_app(path)

        def _open_folder():
            dlg.destroy()
            self._reveal_in_folder(path)

        def _dismiss():
            dlg.destroy()

        ttk.Button(btns, text=tr("export.done.open_file"),
                   style="Accent.TButton",
                   command=_open_file).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text=tr("export.done.open_folder"),
                   style="Ghost.TButton",
                   command=_open_folder).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text=tr("export.done.dismiss"),
                   style="Ghost.TButton",
                   command=_dismiss).pack(side="right")

        # Center over the parent window
        dlg.update_idletasks()
        w = dlg.winfo_reqwidth(); h = dlg.winfo_reqheight()
        px = self.winfo_rootx() + (self.winfo_width() - w) // 2
        py = self.winfo_rooty() + (self.winfo_height() - h) // 2
        dlg.geometry(f"+{max(0, px)}+{max(0, py)}")
        dlg.bind("<Escape>", lambda _e: _dismiss())

    def _export_report(self):
        """生成中文嗓音分析报告 (.md)：每项指标按阈值自动分级。
        导出成功后弹窗询问：打开文件 / 打开文件夹 / 不打开。"""
        if self._last_df is None or self.last_csv is None:
            self._append_log("WARNING", tr("log.no_data_for_report"))
            return
        default = str(Path(self.last_csv).with_suffix(".report.md"))
        path = filedialog.asksaveasfilename(
            title=tr("fd.save_report"),
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
            self._append_log("META", tr("log.report_saved", path=path))
            self._post_export_prompt(path)
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", tr("log.report_fail", e=e))

    def _export_excel(self):
        """一次分析完成后，可导出 .xlsx：Summary + Grouped + 每 metric 一个 heatmap sheet。
        导出成功后弹窗询问：打开文件 / 打开文件夹 / 不打开。"""
        if self._last_df is None or self.last_csv is None:
            self._append_log("WARNING", tr("log.no_data_for_excel"))
            return
        default = str(Path(self.last_csv).with_suffix(".xlsx"))
        path = filedialog.asksaveasfilename(
            title=tr("fd.save_excel"),
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=Path(default).name,
            initialdir=str(Path(default).parent))
        if not path:
            return
        try:
            from voicemap.excel_export import export_vrp_xlsx
            export_vrp_xlsx(self._last_df, path)
            self._append_log("META", tr("log.excel_saved", path=path))
            self._post_export_prompt(path)
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", tr("log.excel_fail", e=e))

    def _open_csv(self):
        """用系统默认程序直接打开 CSV 文件（Excel / 记事本等）。"""
        if not self.last_csv:
            return
        p = Path(self.last_csv)
        if not p.exists():
            self._append_log("ERROR", tr("log.csv_not_found", path=p))
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(p))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:  # noqa: BLE001
            self._append_log("ERROR", tr("log.csv_open_fail", e=e))

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
            self._append_log("ERROR", tr("log.opendir_fail", e=e))


def main():
    app = VoiceMapApp()
    app.mainloop()


if __name__ == "__main__":
    main()
