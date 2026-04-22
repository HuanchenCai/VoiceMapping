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

FONT_UI    = ("Segoe UI", 10)
FONT_UI_B  = ("Segoe UI Semibold", 10)
FONT_TITLE = ("Segoe UI Semibold", 16)
FONT_SUB   = ("Segoe UI", 10)
FONT_DROP  = ("Segoe UI Semibold", 13)
FONT_MONO  = ("Consolas", 9)

# 下拉里展示的 metric 顺序（剔除聚类相关列）
_METRIC_ORDER = [m for m in METRIC_CFG.keys() if m not in _SKIP_ZERO_METRICS]
_DEFAULT_METRIC_CHAIN = ["CPP", "Clarity", "SpecBal", "Crest"]


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

        self._pb = ttk.Progressbar(pad, mode="indeterminate",
                                   length=360,
                                   style="Accent.Horizontal.TProgressbar")
        self._pb.pack(fill="x")
        self._pb.start(12)

        self._status = tk.Label(pad, text="读取音频 …",
                                bg=PANEL, fg=MUTED, font=FONT_UI,
                                anchor="w", wraplength=360, justify="left")
        self._status.pack(fill="x", pady=(10, 0))

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
        try:
            self._status.configure(text=text)
        except tk.TclError:
            pass

    def close(self):
        try:
            self._pb.stop()
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

        # 高 DPI 下让 Tk 按物理像素缩放，而不是走老式位图放大
        try:
            dpi = self.winfo_fpixels("1i")  # 96 在 100% 缩放下
            self.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            pass

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

        # Metric 下拉
        side = tk.Frame(bar, bg=BG)
        side.pack(side="right", padx=(14, 0))
        tk.Label(side, text="Metric", bg=BG, fg=MUTED, font=FONT_UI).pack(anchor="w")
        self.metric_combo = ttk.Combobox(side, textvariable=self.metric_var,
                                         values=_METRIC_ORDER, state="disabled",
                                         width=16, font=FONT_UI)
        self.metric_combo.pack()
        self.metric_combo.bind("<<ComboboxSelected>>", self._on_metric_change)

    def _build_left_panel(self, parent):
        pad = tk.Frame(parent, bg=PANEL)
        pad.pack(fill="both", expand=True, padx=14, pady=14)

        # Clarity
        tk.Label(pad, text="Clarity 阈值", bg=PANEL, fg=ACCENT, font=FONT_UI_B).pack(anchor="w")
        row = tk.Frame(pad, bg=PANEL)
        row.pack(fill="x", pady=(4, 12))
        scale = ttk.Scale(row, from_=0.80, to=1.00, variable=self.clarity_var,
                          orient="horizontal",
                          command=lambda _v: self._update_clarity_lbl())
        scale.pack(side="left", fill="x", expand=True)
        self.clarity_lbl = tk.Label(row, width=5, bg=PANEL, fg=ACCENT, font=FONT_UI_B)
        self.clarity_lbl.pack(side="left", padx=(8, 0))
        self._update_clarity_lbl()

        # 输出目录
        tk.Label(pad, text="输出目录", bg=PANEL, fg=ACCENT, font=FONT_UI_B).pack(anchor="w")
        out_row = tk.Frame(pad, bg=PANEL)
        out_row.pack(fill="x", pady=(4, 12))
        ttk.Entry(out_row, textvariable=self.output_dir_var).pack(side="left", fill="x", expand=True)
        ttk.Button(out_row, text="…", style="Ghost.TButton",
                   command=self._pick_output_dir, width=3).pack(side="left", padx=(6, 0))

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
        # 左右两条独立的导航带（宽 42px），始终占位，彻底不遮挡图像
        self.nav_left = tk.Frame(parent, bg=PANEL, width=42)
        self.nav_left.pack(side="left", fill="y")
        self.nav_left.pack_propagate(False)

        self.nav_right = tk.Frame(parent, bg=PANEL, width=42)
        self.nav_right.pack(side="right", fill="y")
        self.nav_right.pack_propagate(False)

        self._fig = Figure(figsize=(7, 5), dpi=120, facecolor=PANEL)
        self._canvas = FigureCanvasTkAgg(self._fig, master=parent)
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
        vals = list(self.metric_combo.cget("values"))
        if not vals:
            return
        cur = self.metric_var.get()
        try:
            i = vals.index(cur)
        except ValueError:
            i = 0
        self.metric_var.set(vals[(i + delta) % len(vals)])
        self._on_metric_change()

    def _bind_global_keys(self):
        def on_key(event):
            # 在 Entry / Combobox 里输入时不抢键
            cls = event.widget.winfo_class()
            if cls in ("Entry", "Text", "TCombobox", "TEntry"):
                return
            if event.keysym == "Left":
                self._cycle_metric(-1)
            elif event.keysym == "Right":
                self._cycle_metric(+1)
        self.bind("<Key-Left>",  on_key)
        self.bind("<Key-Right>", on_key)

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

        self.metric_combo.state(["disabled"])
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

        def work():
            try:
                from analyzer import VoiceMapAnalyzer
                analyzer = VoiceMapAnalyzer(cfg)
                data, out_file, grouped = analyzer.analyze_and_output_vrp(
                    audio, return_df=True)
                self._msg_q.put(("done", True, {
                    "df": grouped,
                    "csv": out_file,
                    "points": len(data["midi"]),
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
            self.csv_path_var.set(payload["csv"])
            self.open_csv_btn.state(["!disabled"])
            self._set_status(f"完成 · {payload['points']:,} 点", OK)
            self._append_log("META", f"✓ {payload['csv']}")
            self._refresh_metric_dropdown()
        else:
            self._set_status("失败", ERR)
            self._append_log("ERROR", payload["error"])
            self._show_placeholder("分析失败 — 查看日志")

    # ── Metric 切换 ──
    def _refresh_metric_dropdown(self):
        if self._last_df is None:
            return
        df = self._last_df
        available = []
        for col in _METRIC_ORDER:
            if col not in df.columns:
                continue
            series = df[col]
            try:
                if float(series.abs().sum()) > 0:
                    available.append(col)
            except Exception:
                available.append(col)

        if not available:
            self.metric_combo.configure(values=[])
            self.metric_combo.state(["disabled", "!readonly"])
            self._set_nav_visible(False)
            self._show_placeholder("无可用 metric")
            return

        self.metric_combo.configure(values=available)
        # 同时清掉 disabled 标志，否则 ttk 的 disabled 会压制 readonly → 点不动
        self.metric_combo.state(["!disabled", "readonly"])
        self._set_nav_visible(len(available) > 1)

        default = next((m for m in _DEFAULT_METRIC_CHAIN if m in available), available[0])
        self.metric_var.set(default)
        self._render_metric(default)

    def _on_metric_change(self, _event=None):
        col = self.metric_var.get()
        if col:
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
        ax = self._fig.add_subplot(111)
        ok = draw_vrp_on_ax(ax, self._fig, df, col)
        if not ok:
            self._show_placeholder(f"{col} · 无数据")
            return
        # tight_layout 在有 colorbar 的情况下会自动给 ylabel / title / colorbar 腾
        # 出空间，避免 SPL 标签和 metric 标题被截。pad=1.6 经测试在 dpi=120 下
        # 够用，再大会让绘图区变窄。
        try:
            self._fig.tight_layout(pad=1.6)
        except Exception:
            self._fig.subplots_adjust(left=0.12, right=0.92, top=0.90, bottom=0.14)
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
                elif kind == "done":
                    ok, payload = rest
                    self._on_worker_done(ok, payload)
        except queue.Empty:
            pass
        self.after(80, self._drain_queue)

    # ── 状态 ──
    def _update_clarity_lbl(self):
        self.clarity_lbl.configure(text=f"{self.clarity_var.get():.2f}")
        # Clarity 滑动 → 防抖后刷新 voice map（不重跑分析，只改过滤阈值）
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
