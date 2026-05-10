# -*- coding: utf-8 -*-
"""Dialog windows.

  * SettingsDialog  — analysis params (clarity / cluster / output dir).
  * CompareDialog   — pick 2 VRP CSVs, render A | B | A−B per metric.
  * ProgressDialog  — modal progress shown while analysis runs.
  * AboutDialog     — version + author + copyright.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from typing import TYPE_CHECKING

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from voicemap.gui.theme import (
    PANEL, PANEL_HI, BORDER, TEXT, MUTED, ACCENT,
    OK, WARN, ERR, BG_CODE,
    FONT_UI, FONT_UI_B, FONT_MONO, FONT_ABOUT_TITLE,
)
from voicemap.i18n import tr

if TYPE_CHECKING:
    from voicemap.gui.app import VoiceMapApp


# ─── 设置对话框 ──────────────────────────────────────────────────────────────
class SettingsDialog(tk.Toplevel):
    """所有分析/输出相关的可配置项都在这里。现在只有 Clarity 阈值和输出目录，
    随着新 metric（clustering / jitter / formants 等）加进来会继续扩展。"""

    def __init__(self, app: "VoiceMapApp"):
        super().__init__(app)
        self.app = app
        self.transient(app)
        self.title(tr("settings.title"))
        self.configure(bg=PANEL)
        self.resizable(False, False)
        self.bind("<Escape>", lambda _e: self.destroy())

        pad = tk.Frame(self, bg=PANEL)
        pad.pack(padx=24, pady=20)

        # ─ 分析参数 ─
        tk.Label(pad, text=tr("settings.section.analysis"), bg=PANEL, fg=ACCENT, font=FONT_UI_B
                 ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        tk.Label(pad, text=tr("settings.clarity"), bg=PANEL, fg=TEXT, font=FONT_UI
                 ).grid(row=1, column=0, sticky="w", pady=3)
        wrap = tk.Frame(pad, bg=PANEL)
        wrap.grid(row=1, column=1, sticky="w", padx=(18, 0), pady=3)
        ttk.Spinbox(wrap, from_=0.80, to=1.00, increment=0.01,
                    textvariable=app.clarity_var,
                    format="%.2f", width=8, font=FONT_UI,
                    ).pack(side="left")
        tk.Label(wrap, text=tr("settings.clarity_range"), bg=PANEL, fg=MUTED,
                 font=FONT_UI).pack(side="left", padx=(8, 0))
        # 兼容 update_clarity_label 调用；没有单独的数字显示了，做成 no-op
        self.clarity_lbl = None

        # ─ 聚类（下次分析生效） ─
        tk.Label(pad, text=tr("settings.section.cluster"), bg=PANEL, fg=ACCENT, font=FONT_UI_B
                 ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(18, 6))

        tk.Label(pad, text=tr("settings.cluster_k"), bg=PANEL, fg=TEXT, font=FONT_UI
                 ).grid(row=3, column=0, sticky="w", pady=3)
        ttk.Spinbox(pad, from_=2, to=10, textvariable=app.cluster_k_var,
                    width=6).grid(row=3, column=1, sticky="w", padx=(18, 0), pady=3)

        tk.Label(pad, text=tr("settings.cluster_n"), bg=PANEL, fg=TEXT, font=FONT_UI
                 ).grid(row=4, column=0, sticky="w", pady=3)
        ttk.Spinbox(pad, from_=3, to=20, textvariable=app.cluster_nharm_var,
                    width=6).grid(row=4, column=1, sticky="w", padx=(18, 0), pady=3)

        # ─ 输出 ─
        tk.Label(pad, text=tr("settings.section.output"), bg=PANEL, fg=ACCENT, font=FONT_UI_B
                 ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(18, 6))

        tk.Label(pad, text=tr("settings.outdir"), bg=PANEL, fg=TEXT, font=FONT_UI
                 ).grid(row=6, column=0, sticky="w", pady=3)
        out_row = tk.Frame(pad, bg=PANEL)
        out_row.grid(row=6, column=1, sticky="ew", padx=(18, 0), pady=3)
        ttk.Entry(out_row, textvariable=app.output_dir_var, width=32
                  ).pack(side="left")
        ttk.Button(out_row, text="…", style="Ghost.TButton",
                   command=app._pick_output_dir, width=3
                   ).pack(side="left", padx=(6, 0))

        # 自动导出 PNG 开关
        tk.Label(pad, text=tr("settings.auto_png"), bg=PANEL, fg=TEXT, font=FONT_UI
                 ).grid(row=7, column=0, sticky="w", pady=3)
        exp_row = tk.Frame(pad, bg=PANEL)
        exp_row.grid(row=7, column=1, sticky="w", padx=(18, 0), pady=3)
        ttk.Checkbutton(exp_row, variable=app.export_plots_var,
                        text=tr("settings.auto_png_to")).pack(anchor="w")
        layout_row = tk.Frame(exp_row, bg=PANEL)
        layout_row.pack(anchor="w", pady=(4, 0))
        ttk.Radiobutton(layout_row, variable=app.plot_layout_var,
                        value="per-metric", text=tr("settings.layout.per")
                        ).pack(side="left")
        ttk.Radiobutton(layout_row, variable=app.plot_layout_var,
                        value="combined", text=tr("settings.layout.comb")
                        ).pack(side="left", padx=(12, 0))

        # ─ 关闭 ─
        btn_row = tk.Frame(pad, bg=PANEL)
        btn_row.grid(row=8, column=0, columnspan=2, sticky="e", pady=(22, 0))
        ttk.Button(btn_row, text=tr("settings.done"), style="Accent.TButton",
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

    def __init__(self, app: "VoiceMapApp"):
        super().__init__(app)
        self.app = app
        self.transient(app)
        self.title(tr("compare.title"))
        self.configure(bg=PANEL)
        self.bind("<Escape>", lambda _e: self.destroy())
        # Three subplots side-by-side (A | B | Δ) need a lot of horizontal
        # room. The matplotlib figure is 14 inches wide; at 150% Windows
        # DPI scaling that's ~2310 px. We default to 90 % of screen
        # width capped at 1900 px so the dialog uses almost the full
        # monitor on 1080p / 1440p screens without overflowing on
        # smaller displays.
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        dlg_w = min(1900, max(1400, int(sw * 0.90)))
        dlg_h = min(900,  max(560,  int(sh * 0.70)))
        self.geometry(f"{dlg_w}x{dlg_h}")
        self.minsize(1200, 500)

        # File pickers (top bar)
        bar = tk.Frame(self, bg=PANEL)
        bar.pack(fill="x", padx=12, pady=(10, 4))

        self.csv_a = tk.StringVar(value="")
        self.csv_b = tk.StringVar(value="")
        self._df_a = None
        self._df_b = None

        # 路径展示：Label 只显示文件名；完整路径存在 csv_a / csv_b
        # 的 StringVar 里供分析器使用，文件名下方的小 Label 显示父
        # 目录作为上下文。
        self._csv_name_lbls = {}
        self._csv_dir_lbls  = {}
        for label, var, slot in (("A", self.csv_a, "a"), ("B", self.csv_b, "b")):
            f = tk.Frame(bar, bg=PANEL)
            f.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(f, text=label, bg=PANEL, fg=ACCENT,
                     font=FONT_UI_B, width=2).pack(side="left")
            mid = tk.Frame(f, bg=PANEL)
            mid.pack(side="left", fill="x", expand=True)
            self._csv_name_lbls[slot] = tk.Label(
                mid, text=tr("compare.no_file"),
                bg=PANEL, fg=TEXT, font=FONT_UI_B,
                anchor="w")
            self._csv_name_lbls[slot].pack(fill="x", anchor="w")
            self._csv_dir_lbls[slot] = tk.Label(
                mid, text="", bg=PANEL, fg=MUTED, font=FONT_UI,
                anchor="w")
            self._csv_dir_lbls[slot].pack(fill="x", anchor="w")
            ttk.Button(f, text=tr("compare.pick_btn"), style="Ghost.TButton",
                       command=lambda s=slot: self._pick_csv(s)).pack(side="left", padx=(8, 0))

        # Metric + render controls
        ctrl = tk.Frame(self, bg=PANEL)
        ctrl.pack(fill="x", padx=12, pady=(4, 8))
        tk.Label(ctrl, text=tr("compare.metric"), bg=PANEL, fg=MUTED, font=FONT_UI).pack(side="left")
        self.metric = tk.StringVar(value="CPP")
        self.metric_combo = ttk.Combobox(ctrl, textvariable=self.metric,
                                          state="readonly", width=18, font=FONT_UI,
                                          values=["CPP"])
        self.metric_combo.pack(side="left", padx=(6, 0))
        self.metric_combo.bind("<<ComboboxSelected>>", lambda _e: self._render())
        ttk.Button(ctrl, text=tr("compare.refresh"), style="Accent.TButton",
                   command=self._render).pack(side="left", padx=(12, 0))
        ttk.Button(ctrl, text=tr("compare.export_png"), style="Ghost.TButton",
                   command=self._save_png).pack(side="left", padx=(6, 0))

        # Canvas — Figure aspect 12:4 keeps 3 sub-plots horizontal but
        # leaves bottom margin for the MIDI axis label even at smallish
        # dialog heights.
        self._fig = Figure(figsize=(12, 4.0), dpi=100, facecolor=PANEL)
        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        cw = self._canvas.get_tk_widget()
        cw.configure(bg=PANEL, highlightthickness=0, bd=0)
        cw.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        # matplotlib's built-in <Configure> auto-resize doesn't always
        # fire reliably in a Toplevel — the heatmap rendered at the
        # initial figsize while the canvas widget grew, so the bottom
        # of the plot (MIDI axis) clipped below the visible canvas.
        # Explicitly sync figure dpi-pixels to widget pixels on every
        # resize, then re-render so tight_layout uses the new geometry.
        cw.bind("<Configure>", self._on_canvas_resize, add="+")

        self._show_msg(tr("compare.tip_load"))

    def _sync_fig_to_canvas(self) -> bool:
        """Force the matplotlib figure size in inches to match the
        canvas widget's pixel size / dpi. Returns True if anything
        changed (caller may want to draw_idle / tight_layout). Safe
        to call from any code path; no-ops if the widget hasn't been
        laid out yet (size < 50 px) or already matches."""
        try:
            cw = self._canvas.get_tk_widget()
            w = cw.winfo_width()
            h = cw.winfo_height()
            if w < 50 or h < 50:
                return False
            dpi = self._fig.get_dpi() or 100
            need_w, need_h = w / dpi, h / dpi
            cur_w, cur_h = self._fig.get_size_inches()
            if abs(cur_w - need_w) < 0.05 and abs(cur_h - need_h) < 0.05:
                return False
            self._fig.set_size_inches(need_w, need_h, forward=True)
            return True
        except tk.TclError:
            return False

    def _on_canvas_resize(self, event):
        # Auto-handler for <Configure>. Re-syncs fig size, re-runs
        # tight_layout, redraws.
        if event.width < 50 or event.height < 50:
            return
        if not self._sync_fig_to_canvas():
            return
        try:
            self._fig.tight_layout(pad=0.8)
        except Exception:
            pass
        self._canvas.draw_idle()

    def _show_msg(self, msg: str):
        # Sync fig to canvas first so the message centres correctly even
        # on the very first draw (before any <Configure> has fired).
        self._sync_fig_to_canvas()
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
            parent=self, title=tr("compare.tip_pick", slot=slot.upper()),
            filetypes=[(tr("fd.filter.csv"), "*.csv")],
            initialdir=str(Path(self.app.output_dir_var.get())))
        if not path:
            return
        try:
            import pandas as _pd
            df = _pd.read_csv(path, sep=";")
        except Exception as e:  # noqa: BLE001
            self._show_msg(tr("compare.tip_read_fail", e=e))
            return
        p = Path(path)
        if slot == "a":
            self.csv_a.set(path); self._df_a = df
        else:
            self.csv_b.set(path); self._df_b = df
        # Update visible labels: filename prominent, parent dir muted
        self._csv_name_lbls[slot].configure(text=p.name)
        self._csv_dir_lbls[slot].configure(text=str(p.parent))
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
            self._show_msg(tr("compare.tip_load_both"))
            return
        # 必须在 draw 之前先 sync figure→canvas 尺寸。否则首次渲染
        # 用的还是初始 figsize(12,4)（_show_msg 占位会覆盖 mount 期间
        # 的 <Configure> 自动 resize），MIDI 轴会跑出可视区域，
        # 直到用户手动改窗口大小。
        self._sync_fig_to_canvas()
        from voicemap.plotter import draw_vrp_comparison
        ok = draw_vrp_comparison(
            self._df_a, self._df_b, self.metric.get(), self._fig,
            label_a=Path(self.csv_a.get()).stem,
            label_b=Path(self.csv_b.get()).stem)
        if not ok:
            self._show_msg(tr("compare.tip_empty", metric=self.metric.get()))
            return
        self._canvas.draw_idle()

    def _save_png(self):
        if self._df_a is None or self._df_b is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title=tr("compare.fd.save"),
            defaultextension=".png", filetypes=[("PNG", "*.png")],
            initialfile=f"{Path(self.csv_a.get()).stem}_vs_{Path(self.csv_b.get()).stem}_{self.metric.get()}.png")
        if not path:
            return
        try:
            self._fig.savefig(path, dpi=130, bbox_inches="tight",
                               facecolor=self._fig.get_facecolor())
            self.app._append_log("META", tr("compare.log.saved", path=path))
        except Exception as e:  # noqa: BLE001
            self.app._append_log("ERROR", tr("compare.log.fail", e=e))


# ─── 分析进度对话框 ──────────────────────────────────────────────────────────
class ProgressDialog(tk.Toplevel):
    """模态小窗：分析进行时显示文件名 + 当前阶段 + 不确定进度条。"""
    def __init__(self, parent: tk.Misc, filename: str):
        super().__init__(parent)
        self.transient(parent)
        self.title(tr("progress.title"))
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

        tk.Label(pad, text=tr("progress.heading"),
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
        self._status = tk.Label(step_row, text=tr("progress.preparing"),
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


# ─── 日志窗（option-C: 日志不在主界面 Inspector 里） ───────────────────────
class LogWindow(tk.Toplevel):
    """独立日志面板。spec 里 Inspector 不放 log；通过菜单 视图 → 日志面板
    打开此窗口。再次打开则置顶现有窗口（单例）。"""

    _instance: "LogWindow | None" = None

    @classmethod
    def show(cls, app: "VoiceMapApp") -> "LogWindow":
        if cls._instance is not None and cls._instance.winfo_exists():
            cls._instance.lift()
            cls._instance.focus_force()
            return cls._instance
        cls._instance = cls(app)
        return cls._instance

    def __init__(self, app: "VoiceMapApp"):
        super().__init__(app)
        self.app = app
        self.transient(app)
        self.title(tr("log.window.title"))
        self.configure(bg=PANEL)
        self.geometry("720x460")
        self.minsize(480, 240)
        self.bind("<Escape>", lambda _e: self.destroy())

        pad = tk.Frame(self, bg=PANEL)
        pad.pack(fill="both", expand=True, padx=14, pady=14)

        # Title row
        tk.Label(pad, text=tr("log.window.title"), bg=PANEL, fg=ACCENT,
                 font=FONT_UI_B).pack(anchor="w", pady=(0, 6))

        wrap = tk.Frame(pad, bg=PANEL)
        wrap.pack(fill="both", expand=True)

        # Mirror tk.Text widget; we relocate the live one from the app.
        self.text = tk.Text(wrap, bg=BG_CODE, fg=TEXT,
                             font=("Consolas", 10),
                             bd=0, highlightthickness=1,
                             highlightbackground=BORDER,
                             highlightcolor=BORDER,
                             insertbackground=TEXT, wrap="word",
                             padx=8, pady=6, state="disabled")
        self.text.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(wrap, command=self.text.yview)
        sb.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=sb.set)
        # Severity colors map to existing theme tokens (WARN / ERR /
        # OK live in theme.py) so the log stays visually aligned with
        # the Inspector severity legend.
        for tag, color in (("INFO", TEXT), ("DEBUG", MUTED),
                           ("WARNING", WARN), ("ERROR", ERR),
                           ("OK", OK), ("META", ACCENT)):
            self.text.tag_configure(tag, foreground=color)

        # Sync existing log content from app's main log_text widget so
        # opening the window mid-session doesn't lose history.
        try:
            src = app.log_text
            src.configure(state="normal")
            content = src.get("1.0", "end-1c")
            src.configure(state="disabled")
            if content:
                self.text.configure(state="normal")
                self.text.insert("end", content + "\n")
                self.text.configure(state="disabled")
                self.text.see("end")
        except Exception:
            pass

        # Wire app's _append_log to also push into this window. The hook
        # is removed automatically when the window is destroyed.
        self._orig_append = app._append_log
        def _append_to_both(level: str, text: str):
            self._orig_append(level, text)
            try:
                self.text.configure(state="normal")
                self.text.insert("end", text + "\n", level)
                self.text.see("end")
                self.text.configure(state="disabled")
            except tk.TclError:
                pass
        app._append_log = _append_to_both

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        # Restore original _append_log so closing doesn't break logging.
        try:
            self.app._append_log = self._orig_append
        except Exception:
            pass
        type(self)._instance = None
        self.destroy()


# ─── 关于对话框 ────────────────────────────────────────────────────────────
class AboutDialog(tk.Toplevel):
    """版本 / 作者 / 版权信息。按 docs/UI_DESIGN.md option-C 设计语言
    布局：card layout + accent button。"""

    def __init__(self, app: "VoiceMapApp"):
        super().__init__(app)
        from voicemap.__version__ import (
            __version__, __title_zh__, __title_en__,
            __author__, __email__, __license__, __copyright__,
        )
        self.transient(app)
        self.title(tr("about.title"))
        self.configure(bg=PANEL)
        self.resizable(False, False)
        self.bind("<Escape>", lambda _e: self.destroy())

        pad = tk.Frame(self, bg=PANEL)
        pad.pack(padx=32, pady=24)

        # 中文全称（标题）
        tk.Label(pad, text=__title_zh__, bg=PANEL, fg=TEXT,
                 font=FONT_ABOUT_TITLE
                 ).pack(anchor="center")
        # 英文短名 + 版本
        tk.Label(pad, text=f"{__title_en__}  ·  {__version__}",
                 bg=PANEL, fg=ACCENT, font=("Consolas", 11)
                 ).pack(anchor="center", pady=(2, 16))

        # 描述
        tk.Label(pad,
                 text=tr("about.description"),
                 bg=PANEL, fg=MUTED, font=FONT_UI, justify="center"
                 ).pack(pady=(0, 16))

        # 元数据表
        info = tk.Frame(pad, bg=PANEL)
        info.pack(anchor="w", pady=(0, 16))
        rows = [
            (tr("about.author"), __author__),
            (tr("about.email"), __email__),
            (tr("about.license"), __license__),
            (tr("about.copyright"), __copyright__),
        ]
        for i, (label, value) in enumerate(rows):
            tk.Label(info, text=label, bg=PANEL, fg=MUTED, font=FONT_UI,
                     anchor="e", width=18).grid(row=i, column=0,
                                                  sticky="e", pady=2, padx=(0, 12))
            tk.Label(info, text=value, bg=PANEL, fg=TEXT, font=FONT_UI,
                     anchor="w").grid(row=i, column=1, sticky="w", pady=2)

        # 关闭按钮
        ttk.Button(pad, text=tr("about.close"), style="Accent.TButton",
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
