# -*- coding: utf-8 -*-
"""Minimal dict-based i18n for VoiceMap.

Why not gettext
---------------
gettext means .po → .mo compilation, locale dirs, and tooling that
software-copyright reviewers may flag as 'extra dependencies'. We have
~150 strings total; a Python dict is faster to write, faster to read,
and ships as plain UTF-8 source — diff-friendly and one-file-grep-able.

Usage
-----
::

    from voicemap.i18n import tr, set_language, get_language, subscribe

    label = tr("menu.file")           # → "文件" or "File"
    set_language("en")                 # broadcasts to all subscribers
    subscribe(lambda: rebuild_ui())    # called on every language change

A subscriber is a callback with no args. The current language is
persisted to ``~/.voicemap/config.json`` and restored on next start.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

# ── translation table ──────────────────────────────────────────────────
# Keys use dot-separated namespaces ("menu.file", "file.open_wav") so
# greppable scope is obvious.  When the en string is identical to the
# untranslated key (rare), still list it explicitly so a missing entry
# in either language surfaces as a clear gap.
STRINGS: dict[str, dict[str, str]] = {
    "zh": {
        # ── window / status ──
        "app.title":            "嗓音声学品质多维分析图谱",
        "status.ready":         "就绪",
        "status.analyzing":     "分析中…",
        "status.done":          "完成 · {n} 点",
        "status.failed":        "失败",
        "status.tip":           "立体声 WAV · 通道 1 = 麦克风   通道 2 = EGG",

        # ── menubar top labels ──
        "menu.file":            "文件",
        "menu.edit":            "编辑",
        "menu.metric":          "参数",
        "menu.view":            "视图",
        "menu.help":            "帮助",

        # ── file menu ──
        "file.open_wav":        "打开 WAV...",
        "file.open_outdir":     "打开输出目录",
        "file.export_excel":    "导出 Excel",
        "file.gen_report":      "生成报告",
        "file.compare":         "对比 2 段录音…",
        "file.settings":        "设置...",
        "file.quit":            "退出",

        # ── edit menu ──
        "edit.annotate":        "标注",
        "edit.annotate_active": "标注 ●",
        "edit.reset_annotate":  "复位标注",
        "edit.copy_image":      "复制图片",
        "edit.save_image":      "保存图片…",

        # ── metric menu ──
        "metric.prev":          "上一个 metric  ←",
        "metric.next":          "下一个 metric  →",
        "metric.acoustic":      "声学",
        "metric.egg":           "EGG",
        "metric.singing":       "唱歌特异性",
        "metric.cluster":       "聚类",
        "metric.density":       "密度",
        "metric.centroid":      "聚类中心 (Centroid)",
        "metric.centroid.load": "加载 centroid CSV...",
        "metric.centroid.save": "保存当前 centroids",
        "metric.centroid.train":"多 wav 联合训练...",

        # ── view menu ──
        "view.fit":             "拟合曲线…",

        # ── help menu ──
        "help.about":           "关于...",
        "help.language":        "语言",
        "lang.zh":              "中文",
        "lang.en":              "English",

        # ── drop zone / header ──
        "drop.title":           "拖入 .wav 文件  /  点击浏览",
        "drop.title_no_dnd":    "点击浏览（安装 tkinterdnd2 可启用拖拽）",
        "drop.subtitle":        "立体声 WAV · 通道 1 = 麦克风   通道 2 = EGG",
        "drop.placeholder":     "拖入 .wav 文件开始",
        "header.metric":        "Metric",

        # ── option-C layout (Tracks / Metric Bar / Inspector / Status Bar) ──
        "tracks.label":         "录音轨",
        "metric_bar.label":     "指标",
        "metric_bar.nav_hint":  "│  上一个 ←   下一个 →",
        "inspector.title":      "详情",
        "inspector.no_metric":  "选中文件后查看详情",
        "inspector.unit":       "单位",
        "inspector.clinical":   "临床参考范围",
        "inspector.current":    "本次值",
        "statusbar.no_file":    "未加载文件",
        "statusbar.file_meta":  "{name}  ·  {n} 网格  ·  耗时 {dt:.1f}s",
        "statusbar.file_meta_full": "● {name}  ·  {n} 网格  ·  k={k}  ·  {cycles} 个周期  ·  耗时 {dt:.1f}s",
        "statusbar.copyright":  "© 2026 蔡寰宸  ·  v{ver}",
        # Inspector action buttons (spec) + log dialog
        "inspector.btn.excel":  "导出 Excel",
        "inspector.btn.report": "生成报告",
        "inspector.btn.compare":"对比 2 段录音",
        "log.window.title":     "日志面板",
        "view.log":             "日志面板…",
        # Tracks panel row
        "tracks.no_files":      "还没有文件 · 拖入 .wav 开始",
        "tracks.unanalyzed":    "未分析",

        # ── left panel ──
        "left.settings":        "⚙  设置",
        "left.latest_csv":      "最新 CSV",
        "left.open_csv":        "打开 CSV",
        "left.open_outdir":     "打开输出目录",
        "left.export_excel":    "导出 Excel",
        "left.gen_report":      "生成报告",
        "left.compare":         "对比 2 段录音…",
        "left.log":             "日志",

        # ── status / placeholder ──
        "status.analyzing.first_done": "✓ 第一组指标完成，先出图，剩余指标后台继续…",
        "placeholder.no_metric": "无可用 metric",
        "placeholder.no_cell":   "Clarity ≥ {thr:.2f} · 无 cell",
        "placeholder.no_data":   "{col} · 无数据",
        "placeholder.failed":    "分析失败 — 查看日志",

        # ── log messages (also 用户可见，所以入 i18n) ──
        "log.dnd_failed":       "拖放未就绪：{e}",
        "log.ignored_non_wav":  "忽略：非 .wav 文件",
        "log.analysis_busy":    "分析进行中，已忽略新文件",
        "log.no_file":          "文件不存在：{path}",
        "log.no_outdir":        "请先指定输出目录",
        "log.centroid_loaded":  "✓ centroids 加载：{name} k={k}",
        "log.centroid_load_fail":"centroid 加载失败：{e}",
        "log.train_busy":       "分析进行中，训练已忽略",
        "log.no_wav_picked":    "没有选到 .wav",
        "log.train_done":       "✓ 联合训练完成：{n} 个 wav → {file}",
        "log.train_loaded":     "已自动加载新 centroid；下一次拖 wav 分析会用它",
        "log.no_centroid":      "还没分析过，没有 centroid 可保存",
        "log.centroid_saved":   "✓ centroids 保存：{name}",
        "log.centroid_save_fail":"centroid 保存失败：{e}",
        "log.no_data_for_report":"还没分析过，无法生成报告",
        "log.report_saved":     "✓ 报告已导出：{path}",
        "log.report_fail":      "报告生成失败：{e}",
        "log.no_data_for_excel":"还没分析过，无法导出 Excel",
        "log.excel_saved":      "✓ Excel 已导出：{path}",
        "log.excel_fail":       "Excel 导出失败：{e}",
        "log.csv_not_found":    "CSV 不存在：{path}",
        "log.csv_open_fail":    "打开 CSV 失败：{e}",
        "log.opendir_fail":     "打开目录失败：{e}",
        "log.image_saved":      "✓ 已保存: {path}",
        "log.save_fail":        "保存失败: {e}",
        "log.copied_clipboard": "✓ 已复制到剪贴板",
        "log.copy_fail":        "复制失败 — 检查 pywin32 (Win) 或 xclip/wl-copy (Linux)",
        "log.overlay_applied":  "叠加 {kind}/{method}",
        "log.annotated":        "标注 ({x:.1f}, {y:.1f}): {text}",

        # ── centroid status text ──
        "centroid.status.loaded":   "已加载 {name} (k={k})",
        "centroid.status.untrained":"（未加载，将从头训练）",

        # ── filedialog titles ──
        "fd.pick_audio":        "选择音频文件",
        "fd.pick_outdir":       "选择输出目录",
        "fd.pick_centroid":     "加载 centroid CSV",
        "fd.pick_train_wavs":   "选择多个 .wav 做联合 centroid 训练",
        "fd.save_centroid":     "保存联合 centroid 到 CSV",
        "fd.save_centroid_one": "保存 centroid CSV",
        "fd.save_report":       "导出嗓音分析报告",
        "fd.save_excel":        "导出 Excel",
        "fd.save_image":        "保存为 {desc}",
        "fd.filter.wav":        "WAV 文件",
        "fd.filter.csv":        "CSV",
        "fd.filter.all":        "所有文件",

        # ── annotation prompt ──
        "annotate.title":       "标注",
        "annotate.prompt":      "在 (MIDI={x:.1f}, SPL={y:.1f}) 处的标注文本：",

        # ── fit menu ──
        "fit.header":           "  在图上叠加：",
        "fit.center_linear":    "  音域中心线 (linear)",
        "fit.center_poly":      "  音域中心线 (polynomial deg=3)",
        "fit.center_spline":    "  音域中心线 (spline)",
        "fit.center_lowess":    "  音域中心线 (lowess)",
        "fit.trend_poly":       "  当前 metric 趋势 (twin axis, polynomial)",
        "fit.trend_lowess":     "  当前 metric 趋势 (twin axis, lowess)",
        "fit.clear":            "  清除叠加",

        # ── save menu ──
        "save.header":          "  保存当前画布为：",

        # ── settings dialog ──
        "settings.title":       "设置",
        "settings.section.analysis": "分析参数",
        "settings.clarity":     "Clarity 阈值",
        "settings.clarity_range":"(0.80 – 1.00)",
        "settings.section.cluster": "聚类  (下次分析生效)",
        "settings.cluster_k":   "簇数 k",
        "settings.cluster_n":   "谐波数 n",
        "settings.section.output": "输出",
        "settings.outdir":      "目录",
        "settings.auto_png":    "自动导出 PNG",
        "settings.auto_png_to":"分析完成后输出到 plots/",
        "settings.layout.per":  "每 metric 一张图",
        "settings.layout.comb": "合并为一张总览",
        "settings.done":        "完成",

        # ── compare dialog ──
        "compare.title":        "对比 2 段录音 · Voice Map diff",
        "compare.metric":       "Metric:",
        "compare.refresh":      "刷新绘图",
        "compare.export_png":   "导出 PNG",
        "compare.tip_load":     "加载 A 和 B 的 VRP CSV",
        "compare.tip_pick":     "选 {slot} 的 VRP CSV",
        "compare.tip_read_fail":"读取失败：{e}",
        "compare.tip_load_both":"还没加载两个 CSV",
        "compare.tip_empty":    "{metric} 在 A/B 中都为空",
        "compare.fd.save":      "保存对比 PNG",
        "compare.log.saved":    "✓ 对比图已保存：{path}",
        "compare.log.fail":     "保存失败：{e}",

        # ── progress dialog ──
        "progress.title":       "分析进行中",
        "progress.heading":     "正在分析 · Voice Range Profile",
        "progress.preparing":   "准备中…",
        "progress.training":    "准备训练…",
        "progress.train_n_wavs":"{n} 个 wav",

        # ── about dialog ──
        "about.title":          "关于",
        "about.description":    "Voice Range Profile (VRP) 多维分析工具\nStereo WAV → 40+ voice-quality metrics on the (MIDI, SPL) grid",
        "about.author":         "作者 / Author",
        "about.email":          "邮箱 / Email",
        "about.license":        "许可 / License",
        "about.copyright":      "版权 / Copyright",
        "about.close":          "关闭",

        # ── inspector hover pill (was hardcoded "MIDI x · SPL y dB") ──
        "inspector.coords":         "音高 {mi} · 声压 {si} dB",
        "inspector.coords_no_data": "音高 {mi} · 声压 {si} dB · 无数据",

        # ── severity labels (was hardcoded English good/normal/watch/abnormal) ──
        "severity.good":            "优",
        "severity.normal":          "正常",
        "severity.watch":           "注意",
        "severity.abnormal":        "异常",

        # ── metric descriptions: zh prose for the ~80 metric specs ──
        # Looked up by Inspector via tr(f"metric.desc.{name}"); falls back
        # to spec.description (English) if a key is missing.
        "metric.desc.Total":            "本 (音高, 声压) 网格内分析的发声周期数。",
        "metric.desc.Clarity":          "McLeod-Wyvill NSDF 基频检测置信度。",
        "metric.desc.CPP":              "倒谱峰显著度 (Cepstral Peak Prominence)。",
        "metric.desc.CPPS":             "平滑后的 CPP (Hillenbrand 1996)。",
        "metric.desc.SpecBal":          "10·log10(1500 Hz 以下能量 / 以上能量)。",
        "metric.desc.Crest":            "峰值 / 有效值幅度比。",
        "metric.desc.Entropy":          "对每周期 EGG 谐波向量做 Sample Entropy。",
        "metric.desc.Jitter":           "MDVP 风格的周期抖动 (factor 1.3×)。",
        "metric.desc.JitterRAP":        "MDVP RAP 周期抖动 (3 周期窗口)。",
        "metric.desc.JitterPPQ5":       "MDVP PPQ5 周期抖动 (5 周期窗口)。",
        "metric.desc.Shimmer":          "MDVP 风格的振幅扰动。",
        "metric.desc.ShimmerAPQ3":      "MDVP APQ3 振幅扰动 (3 周期窗口)。",
        "metric.desc.ShimmerAPQ5":      "MDVP APQ5 振幅扰动 (5 周期窗口)。",
        "metric.desc.ShimmerAPQ11":     "MDVP APQ11 振幅扰动 (11 周期窗口)。",
        "metric.desc.ShimmerDB":        "dB shimmer = 平均 |20·log10(A[i]/A[i-1])|。",
        "metric.desc.HNR":              "谐噪比 (Praat 自相关算法)。",
        "metric.desc.NHR":              "噪谐比 = 1 / 10^(HNR/10)。",
        "metric.desc.PPE":              "滑动窗内对数周期的香农熵。",
        "metric.desc.ZCR":              "每周期过零数 / 周期长度。",
        "metric.desc.Qcontact":         "FonaDyn 积分式声门接触商。",
        "metric.desc.dEGGmax":          "EGG 微分波形的峰值幅度。",
        "metric.desc.Icontact":         "log10(dEGGmax) · Qcontact。",
        "metric.desc.HRFegg":           "EGG 频谱的谐波丰度因子 (HRF)。",
        "metric.desc.OQ":               "(T - GOI) / T，源自 dEGG 峰位 (开商)。",
        "metric.desc.SPQ":              "T_opening / T_closing (开闭速度商)。",
        "metric.desc.CIQ":              "(T_closing - T_opening) / T_open。",
        "metric.desc.VibratoRate":      "4-8 Hz 频段内主导的 F0 调制频率。",
        "metric.desc.VibratoExtent":    "F0 调制的峰峰值幅度。",
        "metric.desc.F1":               "LPC 谱中第一共振峰 (≥ f1_floor)。",
        "metric.desc.F2":               "LPC 谱中第二共振峰 (高于 F1)。",
        "metric.desc.F3":               "LPC 谱中第三共振峰。",
        "metric.desc.SingersFormant":   "2.8-3.4 kHz 频段能量 / 总能量 (dB)。",
        "metric.desc.H1H2":             "声谱 H1 − H2 幅度差 (dB)。",
        "metric.desc.H1H3":             "声谱 H1 − H3 幅度差 (dB)。",
        "metric.desc.maxCluster":       "本网格内 EGG 形状聚类占比最大的簇编号。",
        "metric.desc.maxCPhon":         "本网格内 cPhon (质量 K-means) 占比最大的簇编号。",
        "metric.desc.Cluster 1":        "EGG 聚类 1 在本网格的周期占比 (%)。",
        "metric.desc.Cluster 2":        "EGG 聚类 2 在本网格的周期占比 (%)。",
        "metric.desc.Cluster 3":        "EGG 聚类 3 在本网格的周期占比 (%)。",
        "metric.desc.Cluster 4":        "EGG 聚类 4 在本网格的周期占比 (%)。",
        "metric.desc.Cluster 5":        "EGG 聚类 5 在本网格的周期占比 (%)。",
        "metric.desc.cPhon 1":          "嗓音质量聚类 1 在本网格的周期占比 (%)。",
        "metric.desc.cPhon 2":          "嗓音质量聚类 2 在本网格的周期占比 (%)。",
        "metric.desc.cPhon 3":          "嗓音质量聚类 3 在本网格的周期占比 (%)。",
        "metric.desc.cPhon 4":          "嗓音质量聚类 4 在本网格的周期占比 (%)。",
        "metric.desc.cPhon 5":          "嗓音质量聚类 5 在本网格的周期占比 (%)。",
        "metric.desc.RMS":              "时域均方根 (每帧)。",
        "metric.desc.F0_Hz":            "基频 (Hz) = 440·2^((MIDI-69)/12)。",
        "metric.desc.SpectralCentroid": "Σ(f·|X|²) / Σ|X|² —— 频谱能量重心。",
        "metric.desc.SpectralBandwidth":"频谱围绕重心的展宽。",
        "metric.desc.SpectralRolloff85":"低于此频率的能量占总能量的 85%。",
        "metric.desc.SpectralFlatness": "几何平均 / 算术平均 —— 0 纯音, 1 噪声。",
        "metric.desc.SpectralSlope":    "log10(|X|) 对频率的线性斜率 (0-5 kHz)。",
        "metric.desc.SpectralSkewness": "频谱围绕重心的三阶矩 (偏度)。",
        "metric.desc.SpectralKurtosis": "频谱四阶矩 − 3 (峭度)。",
        "metric.desc.AlphaRatio":       "10·log10(E[50-1000Hz] / E[1-5kHz]) — alpha 比。",
        "metric.desc.HammarbergIndex":  "max(0-2 kHz dB) − max(2-5 kHz dB) — Hammarberg 指数。",
        "metric.desc.MFCC1":            "梅尔倒谱系数 MFCC 1 (log-mel 的 DCT-II)。",
        "metric.desc.MFCC2":            "梅尔倒谱系数 MFCC 2。",
        "metric.desc.MFCC3":            "梅尔倒谱系数 MFCC 3。",
        "metric.desc.MFCC4":            "梅尔倒谱系数 MFCC 4。",
        "metric.desc.MFCC5":            "梅尔倒谱系数 MFCC 5。",
        "metric.desc.MFCC6":            "梅尔倒谱系数 MFCC 6。",
        "metric.desc.MFCC7":            "梅尔倒谱系数 MFCC 7。",
        "metric.desc.MFCC8":            "梅尔倒谱系数 MFCC 8。",
        "metric.desc.MFCC9":            "梅尔倒谱系数 MFCC 9。",
        "metric.desc.MFCC10":           "梅尔倒谱系数 MFCC 10。",
        "metric.desc.MFCC11":           "梅尔倒谱系数 MFCC 11。",
        "metric.desc.MFCC12":           "梅尔倒谱系数 MFCC 12。",
        "metric.desc.MFCC13":           "梅尔倒谱系数 MFCC 13。",
        "metric.desc.B1":               "F1 LPC 根带宽 = -ln|z|·Fs/π。",
        "metric.desc.B2":               "F2 LPC 根带宽。",
        "metric.desc.B3":               "F3 LPC 根带宽。",
        "metric.desc.FormantDispersion":"(F3 − F1) / 2 —— 声道长度代理。",
        "metric.desc.SPR":              "10·log10(E[2-4kHz] / E[0-2kHz]) — 唱歌功率比。",
        "metric.desc.VibratoJitter":    "滑动窗内 vibrato 周期的变异系数 CV (%)。",
        "metric.desc.GNE":              "简化的声门-噪声激励比 (Glottal-to-Noise Excitation)。",
        "metric.desc.MPT":              "最长连续发声段 (秒)。",
        "metric.desc.VoicingRatio":     "有声周期 / 总周期。",
        "metric.desc.DUV":              "100 − VoicingRatio·100 —— 无声段比例。",
    },
    "en": {
        # ── window / status ──
        "app.title":            "VoiceMap",
        "status.ready":         "Ready",
        "status.analyzing":     "Analyzing…",
        "status.done":          "Done · {n} points",
        "status.failed":        "Failed",
        "status.tip":           "Stereo WAV · Ch 1 = Microphone   Ch 2 = EGG",

        # ── menubar top labels ──
        "menu.file":            "File",
        "menu.edit":            "Edit",
        "menu.metric":          "Metric",
        "menu.view":            "View",
        "menu.help":            "Help",

        # ── file menu ──
        "file.open_wav":        "Open WAV...",
        "file.open_outdir":     "Open Output Folder",
        "file.export_excel":    "Export Excel",
        "file.gen_report":      "Generate Report",
        "file.compare":         "Compare Two Recordings…",
        "file.settings":        "Settings...",
        "file.quit":            "Quit",

        # ── edit menu ──
        "edit.annotate":        "Annotate",
        "edit.annotate_active": "Annotate ●",
        "edit.reset_annotate":  "Clear Annotations",
        "edit.copy_image":      "Copy Image",
        "edit.save_image":      "Save Image…",

        # ── metric menu ──
        "metric.prev":          "Previous metric  ←",
        "metric.next":          "Next metric  →",
        "metric.acoustic":      "Acoustic",
        "metric.egg":           "EGG",
        "metric.singing":       "Singing-specific",
        "metric.cluster":       "Cluster",
        "metric.density":       "Density",
        "metric.centroid":      "Centroid",
        "metric.centroid.load": "Load centroid CSV...",
        "metric.centroid.save": "Save current centroids",
        "metric.centroid.train":"Joint-train across WAVs...",

        # ── view menu ──
        "view.fit":             "Fit curves…",

        # ── help menu ──
        "help.about":           "About...",
        "help.language":        "Language",
        "lang.zh":              "中文",
        "lang.en":              "English",

        # ── drop zone / header ──
        "drop.title":           "Drop a .wav file  /  click to browse",
        "drop.title_no_dnd":    "Click to browse (install tkinterdnd2 to enable drag-drop)",
        "drop.subtitle":        "Stereo WAV · Ch 1 = Microphone   Ch 2 = EGG",
        "drop.placeholder":     "Drop a .wav file to begin",
        "header.metric":        "Metric",

        # ── option-C layout ──
        "tracks.label":         "Tracks",
        "metric_bar.label":     "Metric",
        "metric_bar.nav_hint":  "│  Prev ←   Next →",
        "inspector.title":      "Details",
        "inspector.no_metric":  "Select a file to view details",
        "inspector.unit":       "Unit",
        "inspector.clinical":   "Clinical reference",
        "inspector.current":    "Current value",
        "statusbar.no_file":    "No file loaded",
        "statusbar.file_meta":  "{name}  ·  {n} cells  ·  {dt:.1f}s",
        "statusbar.file_meta_full": "● {name}  ·  {n} cells  ·  k={k}  ·  {cycles} cycles  ·  {dt:.1f}s",
        "statusbar.copyright":  "© 2026 Huanchen Cai  ·  v{ver}",
        # Inspector action buttons + log dialog
        "inspector.btn.excel":  "Export Excel",
        "inspector.btn.report": "Generate Report",
        "inspector.btn.compare":"Compare Two Recordings",
        "log.window.title":     "Log Console",
        "view.log":             "Log Console…",
        # Tracks panel row
        "tracks.no_files":      "No file yet · drop a .wav to begin",
        "tracks.unanalyzed":    "not analyzed",

        # ── left panel ──
        "left.settings":        "⚙  Settings",
        "left.latest_csv":      "Latest CSV",
        "left.open_csv":        "Open CSV",
        "left.open_outdir":     "Open Output Folder",
        "left.export_excel":    "Export Excel",
        "left.gen_report":      "Generate Report",
        "left.compare":         "Compare Two Recordings…",
        "left.log":             "Log",

        # ── status / placeholder ──
        "status.analyzing.first_done": "✓ First metric set ready, drawing now; remaining metrics continue in background…",
        "placeholder.no_metric": "No metric available",
        "placeholder.no_cell":   "Clarity ≥ {thr:.2f} · no cells",
        "placeholder.no_data":   "{col} · no data",
        "placeholder.failed":    "Analysis failed — check log",

        # ── log messages ──
        "log.dnd_failed":       "Drag-drop not ready: {e}",
        "log.ignored_non_wav":  "Ignored: not a .wav file",
        "log.analysis_busy":    "Analysis in progress, ignoring new file",
        "log.no_file":          "File does not exist: {path}",
        "log.no_outdir":        "Specify an output directory first",
        "log.centroid_loaded":  "✓ centroids loaded: {name} k={k}",
        "log.centroid_load_fail":"centroid load failed: {e}",
        "log.train_busy":       "Analysis in progress, training ignored",
        "log.no_wav_picked":    "No .wav files picked",
        "log.train_done":       "✓ Joint training done: {n} wavs → {file}",
        "log.train_loaded":     "New centroids auto-loaded; next dropped wav will use them",
        "log.no_centroid":      "Nothing analyzed yet, no centroid to save",
        "log.centroid_saved":   "✓ centroids saved: {name}",
        "log.centroid_save_fail":"centroid save failed: {e}",
        "log.no_data_for_report":"Nothing analyzed yet, cannot generate report",
        "log.report_saved":     "✓ Report exported: {path}",
        "log.report_fail":      "Report generation failed: {e}",
        "log.no_data_for_excel":"Nothing analyzed yet, cannot export Excel",
        "log.excel_saved":      "✓ Excel exported: {path}",
        "log.excel_fail":       "Excel export failed: {e}",
        "log.csv_not_found":    "CSV not found: {path}",
        "log.csv_open_fail":    "Open CSV failed: {e}",
        "log.opendir_fail":     "Open folder failed: {e}",
        "log.image_saved":      "✓ Saved: {path}",
        "log.save_fail":        "Save failed: {e}",
        "log.copied_clipboard": "✓ Copied to clipboard",
        "log.copy_fail":        "Copy failed — check pywin32 (Win) or xclip/wl-copy (Linux)",
        "log.overlay_applied":  "Overlay {kind}/{method}",
        "log.annotated":        "Annotated ({x:.1f}, {y:.1f}): {text}",

        # ── centroid status text ──
        "centroid.status.loaded":   "Loaded {name} (k={k})",
        "centroid.status.untrained":"(none, will train from scratch)",

        # ── filedialog titles ──
        "fd.pick_audio":        "Pick an audio file",
        "fd.pick_outdir":       "Pick output folder",
        "fd.pick_centroid":     "Load centroid CSV",
        "fd.pick_train_wavs":   "Pick multiple .wav for joint centroid training",
        "fd.save_centroid":     "Save joint centroid CSV",
        "fd.save_centroid_one": "Save centroid CSV",
        "fd.save_report":       "Export voice analysis report",
        "fd.save_excel":        "Export Excel",
        "fd.save_image":        "Save as {desc}",
        "fd.filter.wav":        "WAV files",
        "fd.filter.csv":        "CSV",
        "fd.filter.all":        "All files",

        # ── annotation prompt ──
        "annotate.title":       "Annotate",
        "annotate.prompt":      "Annotation text at (MIDI={x:.1f}, SPL={y:.1f}):",

        # ── fit menu ──
        "fit.header":           "  Overlay on plot:",
        "fit.center_linear":    "  Range center (linear)",
        "fit.center_poly":      "  Range center (polynomial deg=3)",
        "fit.center_spline":    "  Range center (spline)",
        "fit.center_lowess":    "  Range center (lowess)",
        "fit.trend_poly":       "  Current metric trend (twin axis, polynomial)",
        "fit.trend_lowess":     "  Current metric trend (twin axis, lowess)",
        "fit.clear":            "  Clear overlays",

        # ── save menu ──
        "save.header":          "  Save current canvas as:",

        # ── settings dialog ──
        "settings.title":       "Settings",
        "settings.section.analysis": "Analysis",
        "settings.clarity":     "Clarity threshold",
        "settings.clarity_range":"(0.80 – 1.00)",
        "settings.section.cluster": "Clustering  (next analysis)",
        "settings.cluster_k":   "Clusters k",
        "settings.cluster_n":   "Harmonics n",
        "settings.section.output": "Output",
        "settings.outdir":      "Folder",
        "settings.auto_png":    "Auto-export PNG",
        "settings.auto_png_to":"Write to plots/ after analysis",
        "settings.layout.per":  "One PNG per metric",
        "settings.layout.comb": "Single combined overview",
        "settings.done":        "Done",

        # ── compare dialog ──
        "compare.title":        "Compare two recordings · Voice Map diff",
        "compare.metric":       "Metric:",
        "compare.refresh":      "Refresh plot",
        "compare.export_png":   "Export PNG",
        "compare.tip_load":     "Load A and B VRP CSVs",
        "compare.tip_pick":     "Pick the {slot} VRP CSV",
        "compare.tip_read_fail":"Read failed: {e}",
        "compare.tip_load_both":"Load both CSVs first",
        "compare.tip_empty":    "{metric} is empty in both A and B",
        "compare.fd.save":      "Save comparison PNG",
        "compare.log.saved":    "✓ Comparison saved: {path}",
        "compare.log.fail":     "Save failed: {e}",

        # ── progress dialog ──
        "progress.title":       "Analyzing",
        "progress.heading":     "Analyzing · Voice Range Profile",
        "progress.preparing":   "Preparing…",
        "progress.training":    "Preparing training…",
        "progress.train_n_wavs":"{n} wav files",

        # ── about dialog ──
        "about.title":          "About",
        "about.description":    "Voice Range Profile (VRP) multi-metric analyzer\nStereo WAV → 40+ voice-quality metrics on the (MIDI, SPL) grid",
        "about.author":         "Author",
        "about.email":          "Email",
        "about.license":        "License",
        "about.copyright":      "Copyright",
        "about.close":          "Close",

        # ── inspector hover pill ──
        "inspector.coords":         "MIDI {mi} · SPL {si} dB",
        "inspector.coords_no_data": "MIDI {mi} · SPL {si} dB · no data",

        # ── severity labels ──
        "severity.good":            "good",
        "severity.normal":          "normal",
        "severity.watch":           "watch",
        "severity.abnormal":        "abnormal",

        # ── metric descriptions: en (carbon-copy of spec.description so the
        # Inspector path is uniform — tr() always wins, never falls through
        # to spec.description). Keys must mirror the zh table exactly.
        "metric.desc.Total":            "Number of analysed cycles in this (MIDI, dB) cell.",
        "metric.desc.Clarity":          "McLeod-Wyvill NSDF pitch-detection confidence.",
        "metric.desc.CPP":              "Cepstral Peak Prominence.",
        "metric.desc.CPPS":             "Smoothed CPP (Hillenbrand 1996).",
        "metric.desc.SpecBal":          "10·log10(E_below_1500Hz / E_above).",
        "metric.desc.Crest":            "Peak / RMS amplitude ratio.",
        "metric.desc.Entropy":          "Sample Entropy on per-cycle EGG harmonic vectors.",
        "metric.desc.Jitter":           "MDVP-style period perturbation with 1.3× factor.",
        "metric.desc.JitterRAP":        "MDVP RAP period perturbation (3-cycle window).",
        "metric.desc.JitterPPQ5":       "MDVP PPQ5 period perturbation (5-cycle window).",
        "metric.desc.Shimmer":          "MDVP-style amplitude perturbation.",
        "metric.desc.ShimmerAPQ3":      "MDVP APQ3 amplitude perturbation (3-cycle window).",
        "metric.desc.ShimmerAPQ5":      "MDVP APQ5 amplitude perturbation (5-cycle window).",
        "metric.desc.ShimmerAPQ11":     "MDVP APQ11 amplitude perturbation (11-cycle window).",
        "metric.desc.ShimmerDB":        "dB shimmer = mean |20·log10(A[i]/A[i-1])|.",
        "metric.desc.HNR":              "Harmonics-to-Noise Ratio (Praat autocorrelation).",
        "metric.desc.NHR":              "Noise-to-Harmonics Ratio = 1/10^(HNR/10).",
        "metric.desc.PPE":              "Shannon entropy of log-period in sliding window.",
        "metric.desc.ZCR":              "Per-cycle zero-crossings / cycle length.",
        "metric.desc.Qcontact":         "FonaDyn integral-based contact quotient.",
        "metric.desc.dEGGmax":          "Peak amplitude of EGG derivative.",
        "metric.desc.Icontact":         "log10(dEGGmax) · Qcontact.",
        "metric.desc.HRFegg":           "Harmonic Richness Factor on EGG DFT.",
        "metric.desc.OQ":               "(T - GOI) / T from dEGG peaks.",
        "metric.desc.SPQ":              "T_opening / T_closing.",
        "metric.desc.CIQ":              "(T_closing - T_opening) / T_open.",
        "metric.desc.VibratoRate":      "Dominant F0 modulation in 4-8 Hz band.",
        "metric.desc.VibratoExtent":    "Peak-to-peak F0 modulation amplitude.",
        "metric.desc.F1":               "LPC spectrum peak ≥ f1_floor.",
        "metric.desc.F2":               "2nd LPC peak above F1.",
        "metric.desc.F3":               "3rd LPC peak.",
        "metric.desc.SingersFormant":   "2.8-3.4 kHz band energy / total (dB).",
        "metric.desc.H1H2":             "Voice DFT amplitude difference H1 − H2 (dB).",
        "metric.desc.H1H3":             "Voice DFT amplitude difference H1 − H3 (dB).",
        "metric.desc.maxCluster":       "argmax of EGG-shape cluster shares per cell.",
        "metric.desc.maxCPhon":         "argmax of cPhon (quality K-means) shares per cell.",
        "metric.desc.Cluster 1":        "% of cycles in EGG cluster 1.",
        "metric.desc.Cluster 2":        "% of cycles in EGG cluster 2.",
        "metric.desc.Cluster 3":        "% of cycles in EGG cluster 3.",
        "metric.desc.Cluster 4":        "% of cycles in EGG cluster 4.",
        "metric.desc.Cluster 5":        "% of cycles in EGG cluster 5.",
        "metric.desc.cPhon 1":          "% of cycles in phonation cluster 1.",
        "metric.desc.cPhon 2":          "% of cycles in phonation cluster 2.",
        "metric.desc.cPhon 3":          "% of cycles in phonation cluster 3.",
        "metric.desc.cPhon 4":          "% of cycles in phonation cluster 4.",
        "metric.desc.cPhon 5":          "% of cycles in phonation cluster 5.",
        "metric.desc.RMS":              "Time-domain root-mean-square per frame.",
        "metric.desc.F0_Hz":            "Fundamental frequency in Hz (= 440·2^((MIDI-69)/12)).",
        "metric.desc.SpectralCentroid": "Σ(f·|X|²)/Σ|X|² — spectral 'center of mass'.",
        "metric.desc.SpectralBandwidth":"Spectral spread around centroid.",
        "metric.desc.SpectralRolloff85":"Frequency below which 85% of spectral energy lies.",
        "metric.desc.SpectralFlatness": "geomean / mean — 0 tonal, 1 noisy.",
        "metric.desc.SpectralSlope":    "Linear slope of log10(|X|) vs frequency (0-5 kHz).",
        "metric.desc.SpectralSkewness": "Third spectral moment around centroid.",
        "metric.desc.SpectralKurtosis": "Fourth spectral moment − 3.",
        "metric.desc.AlphaRatio":       "10·log10(E[50-1000Hz] / E[1-5kHz]).",
        "metric.desc.HammarbergIndex":  "max(0-2 kHz dB) − max(2-5 kHz dB).",
        "metric.desc.MFCC1":            "Mel-frequency cepstral coefficient 1 (DCT-II of log-mel).",
        "metric.desc.MFCC2":            "Mel-frequency cepstral coefficient 2.",
        "metric.desc.MFCC3":            "Mel-frequency cepstral coefficient 3.",
        "metric.desc.MFCC4":            "Mel-frequency cepstral coefficient 4.",
        "metric.desc.MFCC5":            "Mel-frequency cepstral coefficient 5.",
        "metric.desc.MFCC6":            "Mel-frequency cepstral coefficient 6.",
        "metric.desc.MFCC7":            "Mel-frequency cepstral coefficient 7.",
        "metric.desc.MFCC8":            "Mel-frequency cepstral coefficient 8.",
        "metric.desc.MFCC9":            "Mel-frequency cepstral coefficient 9.",
        "metric.desc.MFCC10":           "Mel-frequency cepstral coefficient 10.",
        "metric.desc.MFCC11":           "Mel-frequency cepstral coefficient 11.",
        "metric.desc.MFCC12":           "Mel-frequency cepstral coefficient 12.",
        "metric.desc.MFCC13":           "Mel-frequency cepstral coefficient 13.",
        "metric.desc.B1":               "LPC root bandwidth = -ln|z|·Fs/π.",
        "metric.desc.B2":               "LPC root bandwidth for F2.",
        "metric.desc.B3":               "LPC root bandwidth for F3.",
        "metric.desc.FormantDispersion":"(F3 − F1) / 2 — vocal-tract length proxy.",
        "metric.desc.SPR":              "10·log10(E[2-4kHz] / E[0-2kHz]).",
        "metric.desc.VibratoJitter":    "CV (%) of vibrato cycle period in sliding window.",
        "metric.desc.GNE":              "Simplified Glottal-to-Noise Excitation proxy.",
        "metric.desc.MPT":              "Longest contiguous voiced run in seconds.",
        "metric.desc.VoicingRatio":     "Voiced cycles / total cycles.",
        "metric.desc.DUV":              "100 − VoicingRatio·100.",
    },
}

# ── runtime state ──────────────────────────────────────────────────────
_current_lang: str = "zh"
_subscribers: list[Callable[[], None]] = []

_CONFIG_PATH = Path.home() / ".voicemap" / "config.json"


# ── public API ─────────────────────────────────────────────────────────
def tr(key: str, **kwargs) -> str:
    """Look up ``key`` in the current language. Returns the key itself
    if not found (so a missing translation surfaces visibly rather than
    silently falling back to "" or English). ``**kwargs`` are passed to
    ``str.format`` so callers can do ``tr("status.done", n=12525)``."""
    s = STRINGS.get(_current_lang, {}).get(key)
    if s is None:
        # Last-resort fallback: try the other language so partial coverage
        # (e.g. an untranslated en string) doesn't show as the bare key.
        for lang, table in STRINGS.items():
            if lang != _current_lang and key in table:
                s = table[key]
                break
        if s is None:
            s = key
    return s.format(**kwargs) if kwargs else s


def get_language() -> str:
    return _current_lang


def set_language(lang: str) -> None:
    """Switch the current language and broadcast to all subscribers.
    Persists the choice to ~/.voicemap/config.json."""
    global _current_lang
    if lang not in STRINGS or lang == _current_lang:
        return
    _current_lang = lang
    _save_to_config(lang)
    for cb in list(_subscribers):
        try:
            cb()
        except Exception:
            # A bad subscriber shouldn't take down language switching.
            pass


def subscribe(callback: Callable[[], None]) -> None:
    """Register ``callback`` to be invoked every time the language
    changes. The callback receives no args; it should re-read ``tr()``
    for the strings it cares about and update its widgets."""
    if callback not in _subscribers:
        _subscribers.append(callback)


def unsubscribe(callback: Callable[[], None]) -> None:
    """Drop a callback. Safe to call with a callback that wasn't
    subscribed (no-op)."""
    try:
        _subscribers.remove(callback)
    except ValueError:
        pass


# ── persistence ────────────────────────────────────────────────────────
def _save_to_config(lang: str) -> None:
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        cfg = {}
        if _CONFIG_PATH.exists():
            try:
                cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        cfg["language"] = lang
        _CONFIG_PATH.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False),
            encoding="utf-8")
    except Exception:
        # Persistence is best-effort. If ~/.voicemap is unwritable for
        # any reason, the in-memory choice still applies for this session.
        pass


def _load_from_config() -> str:
    try:
        if _CONFIG_PATH.exists():
            cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            lang = cfg.get("language")
            if lang in STRINGS:
                return lang
    except Exception:
        pass
    return "zh"


# Initialize current language from disk on module load.
_current_lang = _load_from_config()
