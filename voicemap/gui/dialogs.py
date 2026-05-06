# -*- coding: utf-8 -*-
"""Dialog windows.

  * SettingsDialog  — analysis params (clarity / cluster / output dir).
  * CompareDialog   — pick 2 VRP CSVs, render A | B | A−B per metric.
  * ProgressDialog  — modal progress shown while analysis runs.
  * AboutDialog     — version + author + copyright (added in A0-2).
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
    FONT_UI, FONT_UI_B,
)

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

    def __init__(self, app: "VoiceMapApp"):
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
        from voicemap.plotter import draw_vrp_comparison
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


# ─── 关于对话框（A0-2 新增） ────────────────────────────────────────────────
class AboutDialog(tk.Toplevel):
    """版本 / 作者 / 版权信息。软著申请截图里要有这一张。

    A0-2 阶段先用现有色板把信息摆出来；A0-3 / A0-4 视觉打磨时会按
    docs/UI_DESIGN.md 的 option-C 设计语言重新排版（accent button +
    card layout）。"""

    def __init__(self, app: "VoiceMapApp"):
        super().__init__(app)
        from voicemap.__version__ import (
            __version__, __title_zh__, __title_en__,
            __author__, __email__, __license__, __copyright__,
        )
        self.transient(app)
        self.title("关于")
        self.configure(bg=PANEL)
        self.resizable(False, False)

        pad = tk.Frame(self, bg=PANEL)
        pad.pack(padx=32, pady=24)

        # 中文全称（标题）
        tk.Label(pad, text=__title_zh__, bg=PANEL, fg=TEXT,
                 font=("Microsoft YaHei UI", 16, "bold")
                 ).pack(anchor="center")
        # 英文短名 + 版本
        tk.Label(pad, text=f"{__title_en__}  ·  {__version__}",
                 bg=PANEL, fg=ACCENT, font=("Consolas", 11)
                 ).pack(anchor="center", pady=(2, 16))

        # 描述
        tk.Label(pad,
                 text="Voice Range Profile (VRP) 多维分析工具\n"
                      "Stereo WAV → 40+ voice-quality metrics on the (MIDI, SPL) grid",
                 bg=PANEL, fg=MUTED, font=FONT_UI, justify="center"
                 ).pack(pady=(0, 16))

        # 元数据表
        info = tk.Frame(pad, bg=PANEL)
        info.pack(anchor="w", pady=(0, 16))
        rows = [
            ("作者 / Author", __author__),
            ("邮箱 / Email", __email__),
            ("许可 / License", __license__),
            ("版权 / Copyright", __copyright__),
        ]
        for i, (label, value) in enumerate(rows):
            tk.Label(info, text=label, bg=PANEL, fg=MUTED, font=FONT_UI,
                     anchor="e", width=18).grid(row=i, column=0,
                                                  sticky="e", pady=2, padx=(0, 12))
            tk.Label(info, text=value, bg=PANEL, fg=TEXT, font=FONT_UI,
                     anchor="w").grid(row=i, column=1, sticky="w", pady=2)

        # 关闭按钮
        ttk.Button(pad, text="关闭", style="Accent.TButton",
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
