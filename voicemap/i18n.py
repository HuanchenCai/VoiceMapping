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
        # 风格约定：不写公式（Σ / log10 / 上下标 / 分式都禁用），用一两句
        # 物理直觉解释这个指标量的是什么、值高/低代表什么。控制在
        # 25-60 字以内，方便 Inspector 详情区不滚动也能看完。
        "metric.desc.Total":            "本网格内统计到的发声周期数，反映取样密度。",
        "metric.desc.Clarity":          "基频检测的置信度。值越接近 1 代表音高估计越纯净、稳定。",
        "metric.desc.CPP":              "倒谱峰显著度。反映嗓音的谐波结构清晰度，越高越浊音、越健康。",
        "metric.desc.CPPS":             "平滑后的倒谱峰显著度。比 CPP 更稳定，临床嗓音质量评估常用。",
        "metric.desc.SpecBal":          "高低频能量平衡。正值代表低频主导（声音偏暗），负值代表高频丰富（声音偏亮）。",
        "metric.desc.Crest":            "波形峰值相对均方根的比值。突发性能量越强值越大，反映音色冲击力。",
        "metric.desc.Entropy":          "EGG 谐波形状的随机性。值越高代表声门振动模式越无序、紊乱。",
        "metric.desc.Jitter":           "周期与周期间的频率抖动。反映音高稳定性，值越小代表嗓音越平稳。",
        "metric.desc.JitterRAP":        "RAP 风格的频率抖动（3 周期对比）。临床嗓音障碍评估常用。",
        "metric.desc.JitterPPQ5":       "PPQ5 风格的频率抖动（5 周期对比），比 Jitter 更平滑稳定。",
        "metric.desc.Shimmer":          "周期与周期间的振幅波动。反映响度稳定性，值越小代表音量越平稳。",
        "metric.desc.ShimmerAPQ3":      "APQ3 风格的振幅波动（3 周期对比）。",
        "metric.desc.ShimmerAPQ5":      "APQ5 风格的振幅波动（5 周期对比）。",
        "metric.desc.ShimmerAPQ11":     "APQ11 风格的振幅波动（11 周期对比），最平滑的版本。",
        "metric.desc.ShimmerDB":        "振幅波动的 dB 表达。可与临床上报的 'shimmer dB' 直接对比。",
        "metric.desc.HNR":              "谐波相对噪声的能量比。值越高代表嗓音越清亮、噪声越少、越健康。",
        "metric.desc.NHR":              "噪声相对谐波的比例。HNR 的反向指标，值越低越好。",
        "metric.desc.PPE":              "音高规则性指数。值越低代表音高轨迹越规则、越稳定。",
        "metric.desc.ZCR":              "波形过零密度。反映高频成分含量，越高越接近无声/辅音/噪声。",
        "metric.desc.Qcontact":         "声门接触商。声带闭合阶段在一个完整周期内的时间占比。",
        "metric.desc.dEGGmax":          "EGG 微分波形的峰值。反映声带快速闭合瞬间的强度。",
        "metric.desc.Icontact":         "接触强度指数。综合接触深度与速度，反映声带闭合的有力程度。",
        "metric.desc.HRFegg":           "EGG 频谱的谐波丰度。值越高代表声门振动越规则、对称。",
        "metric.desc.OQ":               "开商。声带处于打开状态的时间在一个周期内的占比。气声型偏高，挤压型偏低。",
        "metric.desc.SPQ":              "开闭速度商。声门张开与闭合阶段的时间比，反映对称性。",
        "metric.desc.CIQ":              "接触不对称指数。值越大代表闭合相对张开越快。",
        "metric.desc.VibratoRate":      "颤音频率，每秒颤动次数。5-7 Hz 是典型的美声、京剧颤音范围。",
        "metric.desc.VibratoExtent":    "颤音的音高摆动幅度，单位 cents。戏剧、京剧通常摆得更宽。",
        "metric.desc.F1":               "第一共振峰。受口腔开度（下颌张开程度）影响最大。",
        "metric.desc.F2":               "第二共振峰。受舌位前后位置影响最大。",
        "metric.desc.F3":               "第三共振峰。与音色亮度、声道长度相关。",
        "metric.desc.SingersFormant":   "歌者共振峰。声乐特有的高频聚束（约 3 kHz），让声音穿透乐队。",
        "metric.desc.H1H2":             "前两个谐波的能量差。反映声门关闭程度：正值偏气声，负值偏紧张/挤压。",
        "metric.desc.H1H3":             "第一与第三谐波的能量差。开商的另一种近似指标。",
        "metric.desc.maxCluster":       "本网格内 EGG 形状聚类占比最大的簇编号（1 至 K）。",
        "metric.desc.maxCPhon":         "本网格内嗓音质量聚类占比最大的簇编号（1 至 K）。",
        "metric.desc.Cluster 1":        "EGG 聚类 1 在本网格的周期占比（%）。",
        "metric.desc.Cluster 2":        "EGG 聚类 2 在本网格的周期占比（%）。",
        "metric.desc.Cluster 3":        "EGG 聚类 3 在本网格的周期占比（%）。",
        "metric.desc.Cluster 4":        "EGG 聚类 4 在本网格的周期占比（%）。",
        "metric.desc.Cluster 5":        "EGG 聚类 5 在本网格的周期占比（%）。",
        "metric.desc.cPhon 1":          "嗓音质量聚类 1 在本网格的周期占比（%）。",
        "metric.desc.cPhon 2":          "嗓音质量聚类 2 在本网格的周期占比（%）。",
        "metric.desc.cPhon 3":          "嗓音质量聚类 3 在本网格的周期占比（%）。",
        "metric.desc.cPhon 4":          "嗓音质量聚类 4 在本网格的周期占比（%）。",
        "metric.desc.cPhon 5":          "嗓音质量聚类 5 在本网格的周期占比（%）。",
        "metric.desc.RMS":              "时域能量均方根，反映瞬时响度。",
        "metric.desc.F0_Hz":            "基频，单位赫兹，与 MIDI 音高一一对应。",
        "metric.desc.SpectralCentroid": "频谱重心。声音音色亮度的核心指标，值越高代表声音越亮、越尖。",
        "metric.desc.SpectralBandwidth":"频谱宽度。能量在频率轴上的分散程度，反映音色丰富度与混响感。",
        "metric.desc.SpectralRolloff85":"高频截止频率。低于此频率累积了 85% 的总能量，越高代表高频成分越丰富。",
        "metric.desc.SpectralFlatness": "频谱平坦度。值接近 0 代表纯音（单一频率），接近 1 代表白噪声。",
        "metric.desc.SpectralSlope":    "频谱斜率。能量随频率上升或下降的整体趋势，反映声门紧张程度。",
        "metric.desc.SpectralSkewness": "频谱偏度。能量分布相对重心的不对称性。",
        "metric.desc.SpectralKurtosis": "频谱峭度。能量在频谱上的集中程度，越高代表能量越集中于少数频率峰。",
        "metric.desc.AlphaRatio":       "中频与高频能量的对比。反映声门紧张度，值高代表低频主导（暗、松），低代表高频主导（亮、紧）。",
        "metric.desc.HammarbergIndex":  "低频与中高频最大值的差。反映声门压力与发声力度。",
        "metric.desc.B1":               "第一共振峰的带宽。带宽越窄代表共振越尖锐、声道越紧张。",
        "metric.desc.B2":               "第二共振峰的带宽。",
        "metric.desc.B3":               "第三共振峰的带宽。",
        "metric.desc.FormantDispersion":"共振峰平均间隔。是声道长度的代理指标，男性偏低、女性偏高。",
        "metric.desc.SPR":              "歌者功率比。高频段（2-4 kHz）相对低频段（0-2 kHz）的能量比。",
        "metric.desc.VibratoJitter":    "颤音规则性。颤音周期的变异程度，越低代表颤音节奏越稳定。",
        "metric.desc.GNE":              "声门激励信噪比。反映发声噪声成分，值越高代表激励越纯净。",
        "metric.desc.MPT":              "最长持续发声时长（秒）。反映呼吸支持能力，临床常用。",
        "metric.desc.VoicingRatio":     "浊音段占总分析段的比例。",
        "metric.desc.DUV":              "无声段（断点、辅音）占总段比例（%），是 VoicingRatio 的反向指标。",
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

        # ── metric descriptions: en, formula-free, physical-intuition style.
        # Mirrors the zh keys exactly — same prose convention (no
        # equations, just what the metric measures and what high/low
        # values mean physically).
        "metric.desc.Total":            "Cycles analysed in this cell — sampling density.",
        "metric.desc.Clarity":          "Pitch-detection confidence. Closer to 1 means a cleaner, more stable F0 estimate.",
        "metric.desc.CPP":              "Cepstral peak prominence. Higher = clearer harmonic structure (more voiced, healthier).",
        "metric.desc.CPPS":             "Smoothed cepstral peak prominence — more stable than CPP, widely used clinically.",
        "metric.desc.SpecBal":          "Low-vs-high-frequency energy balance. Positive = darker (low-frequency-dominated); negative = brighter.",
        "metric.desc.Crest":            "Waveform peak relative to its RMS. Larger values indicate more impulsive, edgy timbre.",
        "metric.desc.Entropy":          "Randomness of EGG harmonic shape. Higher = more disordered glottal vibration pattern.",
        "metric.desc.Jitter":           "Cycle-to-cycle frequency wobble. Lower means a steadier pitch.",
        "metric.desc.JitterRAP":        "RAP-style frequency perturbation (3-cycle window). Common clinical voice metric.",
        "metric.desc.JitterPPQ5":       "PPQ5-style frequency perturbation (5-cycle window). Smoother than Jitter.",
        "metric.desc.Shimmer":          "Cycle-to-cycle amplitude wobble. Lower means a steadier loudness.",
        "metric.desc.ShimmerAPQ3":      "APQ3-style amplitude perturbation (3-cycle window).",
        "metric.desc.ShimmerAPQ5":      "APQ5-style amplitude perturbation (5-cycle window).",
        "metric.desc.ShimmerAPQ11":     "APQ11-style amplitude perturbation (11-cycle window) — smoothest variant.",
        "metric.desc.ShimmerDB":        "Amplitude wobble expressed in dB; comparable to clinical 'shimmer dB' reports.",
        "metric.desc.HNR":              "Harmonic vs noise energy. Higher = brighter, less noisy, healthier voice.",
        "metric.desc.NHR":              "Noise vs harmonic energy. Inverse of HNR — lower is better.",
        "metric.desc.PPE":              "Pitch-period regularity. Lower means a more regular pitch trajectory.",
        "metric.desc.ZCR":              "Zero-crossing density. Higher = more high-frequency / consonant / noisy content.",
        "metric.desc.Qcontact":         "Glottal contact quotient — fraction of each cycle the vocal folds are closed.",
        "metric.desc.dEGGmax":          "Peak of the EGG derivative. Reflects the strength of fast vocal-fold closure.",
        "metric.desc.Icontact":         "Contact intensity. Combines closure depth and speed — how forcefully the folds close.",
        "metric.desc.HRFegg":           "Harmonic richness of the EGG spectrum. Higher = more regular, symmetric vibration.",
        "metric.desc.OQ":               "Open quotient — fraction of each cycle the glottis is open. Breathy voices ↑, pressed voices ↓.",
        "metric.desc.SPQ":              "Speed quotient. Ratio of opening to closing time — symmetry of glottal cycle.",
        "metric.desc.CIQ":              "Contact-asymmetry index. Larger means closing is faster than opening.",
        "metric.desc.VibratoRate":      "Vibrato rate — modulations per second. 5-7 Hz is typical for classical / opera / Peking opera.",
        "metric.desc.VibratoExtent":    "Vibrato pitch swing in cents. Drama / operatic styles tend to be wider.",
        "metric.desc.F1":               "First formant. Most affected by jaw / mouth opening.",
        "metric.desc.F2":               "Second formant. Most affected by tongue front-back position.",
        "metric.desc.F3":               "Third formant. Linked to brightness and vocal-tract length.",
        "metric.desc.SingersFormant":   "Singer's formant — a high-frequency cluster around 3 kHz that lets the voice cut over an orchestra.",
        "metric.desc.H1H2":             "First two harmonic energies' difference. Positive = breathier; negative = pressed/tense.",
        "metric.desc.H1H3":             "First vs third harmonic energy difference — alternative open-quotient proxy.",
        "metric.desc.maxCluster":       "ID of the EGG-shape cluster that dominates this cell (1 to K).",
        "metric.desc.maxCPhon":         "ID of the voice-quality cluster that dominates this cell (1 to K).",
        "metric.desc.Cluster 1":        "Fraction of cycles in EGG cluster 1 (%).",
        "metric.desc.Cluster 2":        "Fraction of cycles in EGG cluster 2 (%).",
        "metric.desc.Cluster 3":        "Fraction of cycles in EGG cluster 3 (%).",
        "metric.desc.Cluster 4":        "Fraction of cycles in EGG cluster 4 (%).",
        "metric.desc.Cluster 5":        "Fraction of cycles in EGG cluster 5 (%).",
        "metric.desc.cPhon 1":          "Fraction of cycles in phonation cluster 1 (%).",
        "metric.desc.cPhon 2":          "Fraction of cycles in phonation cluster 2 (%).",
        "metric.desc.cPhon 3":          "Fraction of cycles in phonation cluster 3 (%).",
        "metric.desc.cPhon 4":          "Fraction of cycles in phonation cluster 4 (%).",
        "metric.desc.cPhon 5":          "Fraction of cycles in phonation cluster 5 (%).",
        "metric.desc.RMS":              "Time-domain energy — instantaneous loudness.",
        "metric.desc.F0_Hz":            "Fundamental frequency in Hz — paired one-to-one with MIDI pitch.",
        "metric.desc.SpectralCentroid": "Spectral 'centre of mass'. Higher = brighter, sharper timbre.",
        "metric.desc.SpectralBandwidth":"Spectral spread — how wide the energy is around the centroid; relates to timbre richness.",
        "metric.desc.SpectralRolloff85":"High-frequency rolloff. The frequency below which 85% of the total energy lies.",
        "metric.desc.SpectralFlatness": "Spectral flatness. Near 0 = pure tone (single frequency); near 1 = white noise.",
        "metric.desc.SpectralSlope":    "Spectral slope. Trend of energy rising or falling with frequency — relates to glottal tension.",
        "metric.desc.SpectralSkewness": "Spectral skewness — asymmetry of the energy distribution around the centroid.",
        "metric.desc.SpectralKurtosis": "Spectral kurtosis — how concentrated energy is on a few spectral peaks.",
        "metric.desc.AlphaRatio":       "Mid-vs-high frequency contrast. High = low-frequency-dominated (dark, lax); low = high-frequency (bright, tense).",
        "metric.desc.HammarbergIndex":  "Difference of low- and mid-high-band peaks. Reflects glottal pressure and effort.",
        "metric.desc.B1":               "First-formant bandwidth. Narrower = sharper resonance, tenser vocal tract.",
        "metric.desc.B2":               "Second-formant bandwidth.",
        "metric.desc.B3":               "Third-formant bandwidth.",
        "metric.desc.FormantDispersion":"Average spacing between formants — proxy for vocal-tract length (lower in male, higher in female).",
        "metric.desc.SPR":              "Singing power ratio. Energy ratio of the 2-4 kHz band to the 0-2 kHz band.",
        "metric.desc.VibratoJitter":    "Vibrato regularity — how steady the cycle period is over time. Lower is steadier.",
        "metric.desc.GNE":              "Glottal-to-noise excitation. Higher = cleaner glottal source, less noise.",
        "metric.desc.MPT":              "Maximum phonation time (seconds). Reflects respiratory support — common clinical metric.",
        "metric.desc.VoicingRatio":     "Fraction of analysed segments that are voiced.",
        "metric.desc.DUV":              "Unvoiced fraction (%) — gaps and consonants. Inverse of VoicingRatio.",
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
