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
        "file.add_files":       "添加文件…",
        "file.add_folder":      "添加文件夹…",
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
        "metric.prev":          "上一个  ←",
        "metric.next":          "下一个  →",
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
        "drop.placeholder":     "打开文件或文件夹以开始",
        "header.metric":        "Metric",

        # ── option-C layout (Tracks / Metric Bar / Inspector / Status Bar) ──
        "tracks.label":         "录音轨",
        "metric_bar.label":     "指标",
        "metric_bar.nav_hint":  "│  上一个 ←   下一个 →",
        "inspector.title":      "详情",
        "inspector.no_metric":  "选中文件后查看详情",
        "inspector.unit":       "单位",
        "inspector.clinical":   "参考范围",
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
        "log.no_wav_in_folder": "目录里没有 .wav 文件：{folder}",
        "log.folder_loaded":    "✓ 添加 {n} 个 wav 自：{folder}",
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
        "log.open_fail":        "无法打开文件 {path}：{e}",
        "export.done.title":    "导出完成",
        "export.done.heading":  "✓ 已导出到：",
        "export.done.open_file":   "打开文件",
        "export.done.open_folder": "打开文件夹",
        "export.done.dismiss":     "不打开",
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
        "fd.pick_folder":       "选择音频文件夹",
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
        "compare.no_file":      "未选择文件",
        "compare.pick_btn":     "打开…",
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
        "metric.desc.JitterRAP":        "用相邻 3 周期取平均后再算频率抖动 (RAP)。比基础 Jitter 更稳，临床嗓音评估常用。",
        "metric.desc.JitterPPQ5":       "用相邻 5 周期取平均再算频率抖动 (PPQ5)。比 RAP 更平滑，对短时噪声不敏感。",
        "metric.desc.Shimmer":          "周期与周期间的振幅波动。反映响度稳定性，值越小代表音量越平稳。",
        "metric.desc.ShimmerAPQ3":      "用相邻 3 周期取平均算振幅扰动 (APQ3)。",
        "metric.desc.ShimmerAPQ5":      "用相邻 5 周期取平均算振幅扰动 (APQ5)。",
        "metric.desc.ShimmerAPQ11":     "用相邻 11 周期取平均算振幅扰动 (APQ11)，最平滑的版本。",
        "metric.desc.ShimmerDB":        "振幅波动用对数 dB 表达，可与临床报告里的 shimmer dB 直接对比。",
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

        # ── metric tooltips: detailed prose for hover-over the metric
        # name. The Inspector card shows the short `metric.desc.X` (a
        # 1-2 sentence tagline); hovering on the title pops a tooltip
        # with the full physical / clinical context AND the math formula
        # (so analysts can verify they're computing what they think).
        # Keys missing here fall back to `metric.desc.X` (short
        # description). User instruction: descriptions stay formula-
        # free, tooltips include formulas.
        "metric.tooltip.Clarity":           "音高检测的可信度，由 McLeod-Wyvill NSDF 算法给出：NSDF(τ) = 2·Σ x[i]·x[i+τ] / Σ (x[i]² + x[i+τ]²)，Clarity = max NSDF。值高代表信号干净、谐波清晰；低值意味着噪声或非浊音段。VoiceMap 默认丢弃 Clarity < 0.96 的网格。",
        "metric.tooltip.CPP":               "倒谱峰显著度。把对数功率谱 log|X(f)| 再做一次 FFT 得到倒谱 c(τ)，CPP = 倒谱在 F0 周期处的峰值减去线性回归基线（dB）。峰越高代表谐波结构越规则、嗓音越浊。健康嗓音典型 CPP > 14 dB，气声/嘶哑会显著降低。",
        "metric.tooltip.CPPS":              "CPP 的平滑版本（Hillenbrand 1996）：在 quefrency 与时间两个维度上各做一次低通平滑后再求峰。CPPS = SmoothPeak(c(τ)) − Baseline。比 CPP 对短时噪声更稳，临床嗓音报告主用此指标。",
        "metric.tooltip.HNR":               "谐波-噪声比。Praat 自相关法：HNR = 10·log10(R_max / (1 − R_max)) (dB)，R_max 为标准化自相关函数在第一非零延迟峰处的值。健康嗓音 HNR > 20 dB；< 10 dB 属于明显病理范围（如声带麻痹、声门闭合不全）。",
        "metric.tooltip.NHR":               "噪声-谐波比，HNR 的反向：NHR = 1 / 10^(HNR/10)。MDVP 阈值 0.13 以下视为正常。NHR 与 HNR 同向但单位不同，看哪个临床上习惯就用哪个。",
        "metric.tooltip.Jitter":            "周期与周期间的频率抖动。Jitter(%) = 100·mean(|T[i] − T[i−1]|) / mean(T[i])，T[i] 为第 i 个声带周期长度。MDVP 阈值 1.04%。声带麻痹、震颤、神经系统疾病常导致 Jitter 升高。注意：Jitter 受音高检测算法精度影响，须在 Clarity 高的网格上看才有意义。",
        "metric.tooltip.JitterRAP":         "RAP（Relative Average Perturbation，相对平均扰动）：先把每 3 个相邻周期取平均得到 T̄[i] = (T[i−1]+T[i]+T[i+1])/3，再算 RAP = mean(|T[i] − T̄[i]|) / mean(T[i])。3 周期平均消除了局部尖刺，比基础 Jitter 更稳。",
        "metric.tooltip.JitterPPQ5":        "PPQ5（5-Period Perturbation Quotient，5 周期扰动商）：用 5 周期滑动平均 T̄[i] = mean(T[i−2..i+2])，PPQ5 = mean(|T[i] − T̄[i]|) / mean(T[i])。窗口更宽更平滑，对短时噪声不敏感。",
        "metric.tooltip.Shimmer":           "周期与周期间的振幅抖动。Shimmer(%) = 100·mean(|A[i] − A[i−1]|) / mean(A[i])，A[i] 为第 i 周期峰幅。和 Jitter 一起看：单项异常是局部问题，两项都抖通常指向更系统性的发声问题。",
        "metric.tooltip.OQ":                "开商（Open Quotient）：OQ = (T − T_GOI) / T，其中 T 是声带周期长度，T_GOI 是 GOI（声门张开瞬间）到下次 GCI（声门闭合瞬间）的时间。GOI / GCI 由 dEGG 波形的负峰 / 正峰给出。气声型 OQ > 0.7，挤压型 OQ < 0.4，模态发声 0.4–0.7。",
        "metric.tooltip.Qcontact":          "声门接触商，积分定义：Qcontact = ∫ EGG_normalized(t) dt / T，对一个完整周期归一化的 EGG 信号求积分。OQ 看打开了多久，Qcontact 看接触了多久，对噪声更稳。0.3–0.6 正常；< 0.3 接触不足（气声）；> 0.6 接触过强（挤压）。",
        "metric.tooltip.dEGGmax":           "EGG 波形对时间求导得到 dEGG(t)，dEGGmax = max |dEGG(t)|。这个峰对应声带快速闭合的瞬间——闭合越快、越有力，峰越尖。临床上反映声带弹性与张力：健康声带闭合迅速 dEGGmax 高，肿胀/麻痹声带 dEGGmax 低。",
        "metric.tooltip.HRFegg":            "EGG 频谱的谐波丰度因子：HRFegg = (Σ_{k≥2} |EGG_k|²) / |EGG_1|²，第一谐波之后所有谐波能量与第一谐波能量之比。值高代表振动模式包含丰富高次谐波——声带振动规则、对称；值低代表只有基本模态，声带不灵活。",
        "metric.tooltip.VibratoRate":       "颤音频率（Hz），从 F0(t) 的窗内 FFT 在 4-8 Hz 频段内取主导峰得到。美声、京剧、戏剧唱腔典型 5–7 Hz；流行、爵士偏 5 Hz；> 8 Hz 通常听感为颤抖或紧张。",
        "metric.tooltip.VibratoExtent":     "颤音音高摆动幅度（cents = 1200·log2(f1/f2)），等于 F0(t) 在颤音周期内的峰峰差转换成 cents。30–100 cents 是日常说话/流行歌；100–200 cents 戏剧/京剧/美声；> 200 cents 通常听感为颤抖。",
        "metric.tooltip.SingersFormant":    "歌者共振峰强度（dB）：SF = 10·log10(E[2.8–3.4 kHz] / E_total)。受训歌手把 F3/F4/F5 叠在 2.8–3.4 kHz 形成一个高能量峰，这个频段恰好是人耳最敏感的范围，让声音不靠麦克风就能盖过乐队。流行歌手很少做出这个共振峰。",
        "metric.tooltip.F1":                "第一共振峰频率（Hz），声道（口腔+咽腔）的最低共振。LPC 法在自回归滤波器极点中找最低频极点 → F1 = arg(z) · Fs / (2π)。受口腔开度（下颌张开多少）影响最大：开口元音 /a/ F1 高，闭口元音 /i//u/ F1 低。",
        "metric.tooltip.F2":                "第二共振峰频率（Hz），LPC 极点中第二低频极点。受舌头前后位置影响最大：前元音 /i/、/e/ F2 高，后元音 /u/、/o/ F2 低。F1 和 F2 一起决定元音的“颜色”。",
        "metric.tooltip.F3":                "第三共振峰频率（Hz），LPC 极点中第三低频极点。与音色亮度和声道长度相关：男声 F3 普遍低于女声（声道更长）。F3 与 F1/F2 联合用于训练歌者共振峰。",
        "metric.tooltip.SpectralCentroid":  "频谱重心：Centroid = Σ f_k · |X[k]|² / Σ |X[k]|²，是功率谱在频率轴上的加权平均位置。听感上对应“音色亮度”：重心高 → 高频成分多 → 亮、尖；重心低 → 低频主导 → 暗、闷。",
        "metric.tooltip.SpectralBandwidth": "频谱宽度（标准差形式）：BW² = Σ (f_k − Centroid)² · |X[k]|² / Σ |X[k]|²。能量在频率轴上的分散度。窄带 = 能量集中（清晰、纯净）；宽带 = 能量散布广（丰满、空气感、或噪声多）。",
        "metric.tooltip.SpectralRolloff85": "85% 能量截止频率：找到最小 f_R 使得 Σ_{k≤R} |X[k]|² ≥ 0.85 · Σ |X[k]|²。f_R 越高，高频成分（毛擦、辅音、噪声）越多。浊音段一般 < 1500 Hz，清音/辅音段 2000–4000 Hz。",
        "metric.tooltip.SpectralFlatness":  "频谱平坦度（Wiener entropy）：Flatness = exp(mean ln|X[k]|²) / mean(|X[k]|²)，几何平均除以算术平均。纯音极限 → 0；白噪声极限 → 1。0.1–0.3 是有谐波结构的乐音；> 0.5 表明噪声主导。",
        "metric.tooltip.AlphaRatio":        "alpha 比：α = 10·log10(E[50–1000 Hz] / E[1–5 kHz]) (dB)。中低频与中高频能量的对比。值高（正）= 声门松弛，声音偏暗；值低（负）= 声门绷紧，声音偏亮、有压力感。",
        "metric.tooltip.HammarbergIndex":   "Hammarberg 指数（Hammarberg 1980）：H = max|X(f)|_{0–2kHz} − max|X(f)|_{2–5kHz} (dB)。两个频段最大值之差。值高 = 声音偏闷（抑郁倾向相关）；值低 = 紧张/焦虑/激发状态。",
        "metric.tooltip.MPT":               "最长持续发声时间（秒）。被试深吸一口气持续发 /a/，能保持的最长时间。MPT = max{ Σ_{voiced} Δt }，连续浊音段的最长持续。成年人正常 > 15 秒，专业歌手 30–40 秒，呼吸功能受损 < 10 秒。",
        "metric.tooltip.VoicingRatio":      "浊音段占比：VoicingRatio = N_voiced / N_total，浊音帧数与总帧数之比。高比例说明被试在持续发声、停顿少；低比例 = 断断续续，辅音多/气声多/喉部疲劳。和 DUV (1 − VoicingRatio) 互补。",
        # ── batch 2: tooltips for the remaining 40 metrics ──
        "metric.tooltip.Total":             "本网格内分析的发声周期数：Total = count(cycles ∈ cell)。反映采样密度。健康嗓音 VRP 中常见上千周期/格；少于 5 周期的格通常排除（噪声驱动）。",
        "metric.tooltip.SpecBal":           "频谱平衡：SpecBal = 10·log10(E[<1500 Hz] / E[≥1500 Hz]) (dB)。1.5 kHz 以下能量与以上能量的比值。值高 = 低频主导（声音偏暗），值低 = 高频主导（声音偏亮）。临床正常嗓音 ±10 dB。",
        "metric.tooltip.Crest":             "波形峰值因子：Crest = max|x[n]| / RMS(x)，时域峰值与有效值之比。值越大代表瞬态成分越强、动态范围越宽。典型语音 1.4-2.0；纯正弦 = √2 ≈ 1.41；脉冲信号 > 3。",
        "metric.tooltip.Entropy":           "EGG 谐波形状的样本熵：SampEn(m=2, r=0.2σ)。把每周期 EGG 的 10 维谐波向量当时间序列算 Sample Entropy。值高 = 振动模式更随机/紊乱；值低 = 周期间高度自相似。",
        "metric.tooltip.ShimmerAPQ3":       "APQ3（3-Period Amplitude Quotient）：先对每 3 个相邻周期峰幅取平均 Ā[i] = (A[i−1]+A[i]+A[i+1])/3，再算 APQ3 = mean(|A[i] − Ā[i]|) / mean(A[i])。3 周期平均消除局部尖刺，比基础 Shimmer 更稳。",
        "metric.tooltip.ShimmerAPQ5":       "APQ5（5-Period Amplitude Quotient）：5 周期滑动平均 Ā[i] = mean(A[i−2..i+2])，APQ5 = mean(|A[i] − Ā[i]|) / mean(A[i])。比 APQ3 更平滑。",
        "metric.tooltip.ShimmerAPQ11":      "APQ11（11-Period Amplitude Quotient）：11 周期滑动平均，APQ11 = mean(|A[i] − Ā[i]|) / mean(A[i])。最长窗口、最平滑的 Shimmer 变体。",
        "metric.tooltip.ShimmerDB":         "ShimmerDB = mean(|20·log10(A[i] / A[i−1])|) (dB)。把 Shimmer 用对数 dB 表达，可直接对比临床报告里的 'shimmer dB' 数字。MDVP 阈值 0.35 dB 视为正常。",
        "metric.tooltip.PPE":               "音高周期熵 PPE（Pitch Period Entropy）：在滑动窗里把 log(T[i]) 做归一化直方图，再算 Shannon 熵 H = −Σ p·log p。值低 = 音高高度规律；值高 = 抖动/不规则。常用于帕金森嗓音研究。",
        "metric.tooltip.ZCR":               "过零率：ZCR = (1/N)·Σ 𝟙{x[n]·x[n+1] < 0}，每周期内信号过零次数除以周期长度。反映高频成分含量：浊音段低（< 0.05），清音/辅音段高（> 0.2）。",
        "metric.tooltip.Icontact":          "接触强度指数：Icontact = log10(dEGGmax) · Qcontact。综合声带闭合速度（dEGGmax）与持续时间（Qcontact）两个维度，反映闭合的整体力度。注：菜单里默认隐藏，CSV 里仍写入供分析师使用。",
        "metric.tooltip.SPQ":               "开闭速度商：SPQ = T_opening / T_closing，声门张开时间与闭合时间之比。等于 1 = 对称模态；> 1 = 张开慢闭合快（典型健康）；< 1 = 张开快闭合慢（少见）。",
        "metric.tooltip.CIQ":               "接触不对称指数：CIQ = (T_closing − T_opening) / T_open。值越正代表闭合相对张开越快、声带越有力；值接近 0 = 对称张闭。",
        "metric.tooltip.H1H2":              "前两个谐波的能量差：H1H2 = 20·log10(|H1| / |H2|) (dB)，从声波 DFT 里取基频 F0 与 2·F0 的幅度。负值 = 压声型 / 紧张（H1 < H2，能量挤压到高谐波）；正值 = 气声型 / 松弛（H1 > H2，能量集中在基频）。",
        "metric.tooltip.H1H3":              "第一与第三谐波能量差：H1H3 = 20·log10(|H1| / |H3|) (dB)。3·F0 的成分受声门关闭速度影响更大，是开商 OQ 的间接指标。和 H1H2 一起读更可靠。",
        "metric.tooltip.maxCluster":        "本网格主导的 EGG 形状聚类编号：maxCluster = argmax_k count(cycle ∈ cluster_k)。1 至 K（默认 K=5）。聚类是对每周期 EGG 谐波向量做 K-means 得到，每个簇代表一种典型的声门振动形态。",
        "metric.tooltip.maxCPhon":          "本网格主导的 cPhon（嗓音质量聚类）编号：maxCPhon = argmax_k count(cycle ∈ phon_k)。cPhon 在 9 维特征（Clarity/CPP/SpecBal/Crest/Entropy/Qcontact/dEGGmax/Icontact/HRFegg）上做 K-means。",
        "metric.tooltip.Cluster 1":         "EGG 聚类 1 在本网格的周期占比 (%)：share = 100 · count(cycle ∈ cluster_1) / count(cycles in cell)。聚类编号无固定语义，需要看完整 5 簇的相对分布才有意义。",
        "metric.tooltip.Cluster 2":         "EGG 聚类 2 在本网格的周期占比 (%)。",
        "metric.tooltip.Cluster 3":         "EGG 聚类 3 在本网格的周期占比 (%)。",
        "metric.tooltip.Cluster 4":         "EGG 聚类 4 在本网格的周期占比 (%)。",
        "metric.tooltip.Cluster 5":         "EGG 聚类 5 在本网格的周期占比 (%)。",
        "metric.tooltip.cPhon 1":           "嗓音质量聚类 1 在本网格的周期占比 (%)。基于 9 维质量特征（Clarity/CPP/SpecBal/Crest/Entropy/Qcontact/dEGGmax/Icontact/HRFegg）的 K-means。",
        "metric.tooltip.cPhon 2":           "嗓音质量聚类 2 在本网格的周期占比 (%)。",
        "metric.tooltip.cPhon 3":           "嗓音质量聚类 3 在本网格的周期占比 (%)。",
        "metric.tooltip.cPhon 4":           "嗓音质量聚类 4 在本网格的周期占比 (%)。",
        "metric.tooltip.cPhon 5":           "嗓音质量聚类 5 在本网格的周期占比 (%)。",
        "metric.tooltip.RMS":               "时域均方根：RMS = sqrt((1/N)·Σ x[n]²)。每帧的能量度量，对应感知响度。",
        "metric.tooltip.F0_Hz":             "基频 (Hz)，由 MIDI 音高换算：F0 = 440 · 2^((MIDI − 69) / 12)。MIDI 69 = A4 = 440 Hz。男声常驻 80-200 Hz，女声 165-300 Hz，高音歌手可达 1000+ Hz。",
        "metric.tooltip.SpectralSlope":     "频谱斜率：linear_fit(log10|X(f)|, f) 在 0-5 kHz 频段拟合的一次斜率（dB/Hz）。负斜率 = 高频衰减（暗、松）；正/平 = 高频丰富（亮、紧）。声门紧张度间接指标。",
        "metric.tooltip.SpectralSkewness":  "频谱偏度：μ_3 / σ³，频谱围绕重心的三阶标准化矩。0 = 对称分布；正值 = 高频拖尾（能量更多聚于高频）；负值 = 低频拖尾。",
        "metric.tooltip.SpectralKurtosis":  "频谱峭度：μ_4 / σ⁴ − 3。0 = 高斯分布形状；正值 = 尖锐峰（少数频率主导）；负值 = 平坦分布（能量散开）。值高代表能量集中。",
        "metric.tooltip.B1":                "F1 共振峰带宽：B1 = -ln|z₁| · Fs / π，z₁ 为 LPC 自回归滤波器对应 F1 的极点。带宽越窄代表共振越尖锐、声道越紧张。健康男声 F1 带宽典型 50-100 Hz。",
        "metric.tooltip.B2":                "F2 共振峰带宽：同 B1，z₂ 为 F2 极点。",
        "metric.tooltip.B3":                "F3 共振峰带宽：同 B1，z₃ 为 F3 极点。",
        "metric.tooltip.FormantDispersion": "共振峰平均间隔：FD = (F3 − F1) / 2 (Hz)。是声道长度的代理指标 —— 声道越长 FD 越小。男声典型 FD ≈ 800 Hz，女声 ≈ 950 Hz。",
        "metric.tooltip.SPR":               "歌者功率比：SPR = 10·log10(E[2-4 kHz] / E[0-2 kHz]) (dB)。高频段相对低频段的能量比。受过训练的歌手 > -7 dB（歌者共振峰存在）；普通说话嗓音 -25 至 -15 dB。",
        "metric.tooltip.VibratoJitter":     "颤音规则性：滑动窗内颤音周期长度 T_vib[i] 的变异系数 CV = std(T_vib) / mean(T_vib) (%)。值低 = 颤音节奏稳定；值高 = 颤音忽快忽慢，可能颤抖或紧张。",
        "metric.tooltip.GNE":               "声门激励/噪声比 GNE：把声门激励信号在多个 hilbert 包络上做相关，取最大相关系数。GNE ≈ 1 表示纯净激励，≈ 0 表示噪声主导。简化的 vocal noise 指标。",
        "metric.tooltip.DUV":               "无声段比例：DUV = 100 · (1 − VoicingRatio) (%)。无声帧（辅音、停顿、断点）占总帧数。和 VoicingRatio 互补。MPT 测试中 DUV < 15% 为正常。",
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
        "file.add_files":       "Add files…",
        "file.add_folder":      "Add folder…",
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
        "metric.prev":          "Previous  ←",
        "metric.next":          "Next  →",
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
        "drop.placeholder":     "Open a file or folder to start",
        "header.metric":        "Metric",

        # ── option-C layout ──
        "tracks.label":         "Tracks",
        "metric_bar.label":     "Metric",
        "metric_bar.nav_hint":  "│  Prev ←   Next →",
        "inspector.title":      "Details",
        "inspector.no_metric":  "Select a file to view details",
        "inspector.unit":       "Unit",
        "inspector.clinical":   "Reference range",
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
        "log.no_wav_in_folder": "No .wav files found under: {folder}",
        "log.folder_loaded":    "✓ Added {n} wav file(s) from: {folder}",
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
        "log.open_fail":        "Cannot open file {path}: {e}",
        "export.done.title":    "Export complete",
        "export.done.heading":  "✓ Exported to:",
        "export.done.open_file":   "Open file",
        "export.done.open_folder": "Open folder",
        "export.done.dismiss":     "Dismiss",
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
        "fd.pick_folder":       "Pick an audio folder",
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
        "compare.no_file":      "No file selected",
        "compare.pick_btn":     "Open…",
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
        "metric.desc.JitterRAP":        "Frequency wobble averaged over 3 neighbouring cycles (RAP). Steadier than basic Jitter; standard clinical metric.",
        "metric.desc.JitterPPQ5":       "Frequency wobble averaged over 5 neighbouring cycles (PPQ5). Smoother than RAP, robust to short-term noise.",
        "metric.desc.Shimmer":          "Cycle-to-cycle amplitude wobble. Lower means a steadier loudness.",
        "metric.desc.ShimmerAPQ3":      "Amplitude perturbation averaged over 3 cycles (APQ3).",
        "metric.desc.ShimmerAPQ5":      "Amplitude perturbation averaged over 5 cycles (APQ5).",
        "metric.desc.ShimmerAPQ11":     "Amplitude perturbation averaged over 11 cycles (APQ11) — smoothest variant.",
        "metric.desc.ShimmerDB":        "Amplitude wobble expressed in dB, directly comparable to the clinical shimmer dB metric.",
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

        # ── metric tooltips: detailed prose for hover-over the metric name. ──
        "metric.tooltip.Clarity":           "Pitch-detection confidence (McLeod-Wyvill NSDF): NSDF(τ) = 2·Σ x[i]·x[i+τ] / Σ (x[i]² + x[i+τ]²); Clarity = max NSDF. High = clean signal, distinct harmonics; low = noise contamination or non-voiced. VoiceMap drops cells with Clarity < 0.96 by default.",
        "metric.tooltip.CPP":                "Cepstral Peak Prominence: take the FFT of log|X(f)| to get the cepstrum c(τ); CPP = peak of c at the F0 period minus a linear-regression baseline (dB). Higher peaks mean a more regular, voiced harmonic structure. Healthy voices score CPP > 14 dB; breathy/hoarse voices collapse the peak.",
        "metric.tooltip.CPPS":                "Smoothed CPP (Hillenbrand 1996): low-pass smoothing in both quefrency and time before peak picking. CPPS = SmoothPeak(c(τ)) − Baseline. More robust to short-term noise than raw CPP, so clinical reports prefer it.",
        "metric.tooltip.HNR":                 "Harmonics-to-Noise Ratio (Praat autocorrelation): HNR = 10·log10(R_max / (1 − R_max)) (dB), with R_max the peak of the normalised autocorrelation at the first non-zero lag. Healthy > 20 dB; < 10 dB is clearly pathological (paralysis, glottal incompetence).",
        "metric.tooltip.NHR":                 "Noise-to-Harmonics Ratio — the inverse of HNR: NHR = 1 / 10^(HNR/10). MDVP threshold 0.13 = normal. Same direction as HNR with different units; pick whichever matches your protocol.",
        "metric.tooltip.Jitter":              "Cycle-to-cycle frequency wobble: Jitter(%) = 100·mean(|T[i] − T[i−1]|) / mean(T[i]), where T[i] is the i-th vocal-fold period. MDVP threshold 1.04%. High in paralysis, tremor, neurological pathology. Sensitive to F0-estimator accuracy — only meaningful where Clarity is high.",
        "metric.tooltip.JitterRAP":           "RAP (Relative Average Perturbation): smooth periods over 3 neighbours T̄[i] = (T[i−1]+T[i]+T[i+1])/3, then RAP = mean(|T[i] − T̄[i]|) / mean(T[i]). The 3-cycle averaging removes local spikes — steadier than basic Jitter.",
        "metric.tooltip.JitterPPQ5":          "PPQ5 (5-Period Perturbation Quotient): smooth periods over 5 neighbours T̄[i] = mean(T[i−2..i+2]), then PPQ5 = mean(|T[i] − T̄[i]|) / mean(T[i]). Wider window, smoother, less sensitive to short-term noise.",
        "metric.tooltip.Shimmer":             "Cycle-to-cycle amplitude wobble: Shimmer(%) = 100·mean(|A[i] − A[i−1]|) / mean(A[i]), with A[i] the peak of the i-th cycle. Read with Jitter: wobble in one is isolated, wobble in both points at a systemic issue.",
        "metric.tooltip.OQ":                  "Open Quotient: OQ = (T − T_GOI) / T, where T is cycle length and T_GOI is the time from GOI (glottis-opening instant) to the next GCI (closing instant). GOI / GCI come from negative / positive peaks of the dEGG signal. Breathy > 0.7, pressed < 0.4, modal 0.4–0.7.",
        "metric.tooltip.Qcontact":            "Glottal contact quotient (integral form): Qcontact = ∫ EGG_normalised(t) dt / T, integrating the normalised EGG over a full cycle. OQ measures how long the folds are open; Qcontact measures how long they're in contact, more robust to noise. 0.3–0.6 normal; < 0.3 = under-contact (breathy); > 0.6 = over-contact (pressed).",
        "metric.tooltip.dEGGmax":             "Differentiate EGG over time → dEGG(t); dEGGmax = max |dEGG(t)|. The peak corresponds to the moment of fastest vocal-fold closure — sharper peak = faster, more forceful closure. Healthy elastic folds = high dEGGmax; swollen or paralyzed folds = low dEGGmax.",
        "metric.tooltip.HRFegg":               "Harmonic Richness Factor on the EGG spectrum: HRFegg = (Σ_{k≥2} |EGG_k|²) / |EGG_1|². The energy beyond H1 ratioed against H1. High = rich higher harmonics, regular & symmetric vibration; low = single dominant mode, less flexible folds.",
        "metric.tooltip.VibratoRate":         "Vibrato rate (Hz): the dominant peak of the windowed FFT of F0(t) within 4–8 Hz. 5–7 Hz typical for classical / opera / Peking opera; ~5 Hz pop / jazz; > 8 Hz often reads as tremor or tension.",
        "metric.tooltip.VibratoExtent":       "Vibrato pitch swing in cents (cents = 1200·log2(f1/f2)) — peak-to-peak F0 swing within a vibrato cycle, converted to cents. 30–100 cents typical for speech / pop; 100–200 cents theatrical / operatic / Chinese opera; > 200 cents reads as wobble.",
        "metric.tooltip.SingersFormant":      "Singer's formant strength (dB): SF = 10·log10(E[2.8–3.4 kHz] / E_total). Trained singers stack F3, F4, F5 into one peak around 2.8–3.4 kHz — coinciding with the ear's most sensitive range, letting the voice cut over an orchestra unamplified. Pop singers rarely produce it.",
        "metric.tooltip.F1":                  "First formant frequency (Hz) — the lowest resonance of the vocal tract (oral + pharyngeal cavities). LPC-based: find the lowest-frequency pole z of the AR filter → F1 = arg(z) · Fs / (2π). Most affected by jaw / mouth opening: open /a/ raises F1, close /i/, /u/ lowers it.",
        "metric.tooltip.F2":                  "Second formant frequency (Hz) — second-lowest LPC pole. Most affected by tongue front-back position: front /i/, /e/ raises F2; back /u/, /o/ lowers it. F1 and F2 together define vowel 'colour'.",
        "metric.tooltip.F3":                  "Third formant frequency (Hz) — third-lowest LPC pole. Drives brightness and perceived vocal-tract length: male voices have lower F3 (longer tract) than female. F3 combined with F1 / F2 is used to train the singer's formant.",
        "metric.tooltip.SpectralCentroid":    "Spectral centroid: Centroid = Σ f_k · |X[k]|² / Σ |X[k]|² — the weighted-average frequency position of the power spectrum. Perceptually = brightness of timbre. High centroid = high-frequency-rich = bright, sharp; low centroid = low-frequency-dominated = dark, muffled.",
        "metric.tooltip.SpectralBandwidth":   "Spectral spread (std-deviation form): BW² = Σ (f_k − Centroid)² · |X[k]|² / Σ |X[k]|². How wide the energy is around the centroid. Narrow = focused, clean; wide = full, airy, or noisy.",
        "metric.tooltip.SpectralRolloff85":   "85%-energy rolloff frequency: smallest f_R such that Σ_{k≤R} |X[k]|² ≥ 0.85 · Σ |X[k]|². Higher f_R means more high-frequency content (fricatives, consonants, noise). Voiced typically < 1500 Hz; unvoiced / consonants 2000–4000 Hz.",
        "metric.tooltip.SpectralFlatness":    "Spectral flatness (Wiener entropy): Flatness = exp(mean ln|X[k]|²) / mean(|X[k]|²) — geometric mean over arithmetic mean. Pure-tone limit → 0; white-noise limit → 1. 0.1–0.3 is harmonic-structured musical tone; > 0.5 means noise dominates.",
        "metric.tooltip.AlphaRatio":          "Alpha ratio: α = 10·log10(E[50–1000 Hz] / E[1–5 kHz]) (dB). Mid-vs-high-frequency energy contrast. High (positive) = lax glottis, dark voice; low (negative) = tight glottis, bright / pressed voice.",
        "metric.tooltip.HammarbergIndex":     "Hammarberg index (Hammarberg 1980): H = max|X(f)|_{0–2 kHz} − max|X(f)|_{2–5 kHz} (dB). Difference of peak energies in two bands. High = muffled (depression-correlated); low = tense / anxious / aroused state.",
        "metric.tooltip.MPT":                 "Maximum Phonation Time (seconds): MPT = max{ Σ_{voiced} Δt }, the longest contiguous voiced run. Subject takes a deep breath and sustains /a/ as long as possible. Healthy adults > 15 s, professional singers 30–40 s, impaired respiratory function < 10 s.",
        "metric.tooltip.VoicingRatio":        "Voicing fraction: VoicingRatio = N_voiced / N_total — voiced frames over total frames. High = sustained phonation, few pauses; low = stop-and-go, many consonants / breathy phonation / vocal fatigue. Complementary to DUV (1 − VoicingRatio).",
        # ── batch 2: tooltips for the remaining 40 metrics ──
        "metric.tooltip.Total":              "Cycles analysed in this cell: Total = count(cycles ∈ cell). Reflects sampling density. Healthy VRPs commonly hit 1000+ cycles per cell; cells with < 5 cycles are usually excluded (noise-driven).",
        "metric.tooltip.SpecBal":            "Spectral balance: SpecBal = 10·log10(E[<1500 Hz] / E[≥1500 Hz]) (dB). Energy below 1.5 kHz vs above. High = low-freq dominated (dark voice); low = high-freq dominated (bright voice). ±10 dB is clinically normal.",
        "metric.tooltip.Crest":              "Waveform crest factor: Crest = max|x[n]| / RMS(x), peak vs RMS in the time domain. Higher = more impulsive transients, wider dynamic range. Typical speech 1.4-2.0; pure sine = √2 ≈ 1.41; impulsive signal > 3.",
        "metric.tooltip.Entropy":            "Sample entropy on EGG harmonics: SampEn(m=2, r=0.2σ). Treats each cycle's 10-D EGG harmonic vector as a time series. High = random / disordered vibration; low = highly self-similar between cycles.",
        "metric.tooltip.ShimmerAPQ3":        "APQ3 (3-Period Amplitude Quotient): smooth peak amplitudes over 3 cycles Ā[i] = (A[i−1]+A[i]+A[i+1])/3, then APQ3 = mean(|A[i] − Ā[i]|) / mean(A[i]). Removes local spikes — steadier than basic Shimmer.",
        "metric.tooltip.ShimmerAPQ5":        "APQ5 (5-Period Amplitude Quotient): 5-cycle moving average Ā[i] = mean(A[i−2..i+2]), APQ5 = mean(|A[i] − Ā[i]|) / mean(A[i]). Smoother than APQ3.",
        "metric.tooltip.ShimmerAPQ11":       "APQ11 (11-Period Amplitude Quotient): 11-cycle moving average. APQ11 = mean(|A[i] − Ā[i]|) / mean(A[i]). Longest window, smoothest Shimmer variant.",
        "metric.tooltip.ShimmerDB":          "ShimmerDB = mean(|20·log10(A[i] / A[i−1])|) (dB). Shimmer expressed in dB, directly comparable to clinical 'shimmer dB' reports. MDVP threshold 0.35 dB = normal.",
        "metric.tooltip.PPE":                "Pitch Period Entropy: build a normalised histogram of log(T[i]) within a sliding window, then Shannon entropy H = −Σ p·log p. Low = highly regular pitch; high = jittery / irregular. Used in Parkinson's voice research.",
        "metric.tooltip.ZCR":                "Zero-Crossing Rate: ZCR = (1/N)·Σ 𝟙{x[n]·x[n+1] < 0}, sign-changes per cycle divided by cycle length. Reflects high-frequency content: voiced low (< 0.05); unvoiced / consonants high (> 0.2).",
        "metric.tooltip.Icontact":           "Contact intensity: Icontact = log10(dEGGmax) · Qcontact. Combines closure speed (dEGGmax) and duration (Qcontact) — overall closure force. Hidden from menu by default; CSV column still written.",
        "metric.tooltip.SPQ":                "Speed Quotient: SPQ = T_opening / T_closing, ratio of glottal opening time to closing time. = 1 means symmetric; > 1 means slow open, fast close (typical healthy); < 1 is rare.",
        "metric.tooltip.CIQ":                "Contact-asymmetry Index: CIQ = (T_closing − T_opening) / T_open. Positive = closing faster than opening (forceful folds); near 0 = symmetric.",
        "metric.tooltip.H1H2":               "First two harmonic energies' difference: H1H2 = 20·log10(|H1| / |H2|) (dB), from the voice DFT at F0 and 2·F0. Negative = pressed / tense (energy pushed to higher harmonics); positive = breathy / lax (energy concentrated at fundamental).",
        "metric.tooltip.H1H3":               "First vs third harmonic energy: H1H3 = 20·log10(|H1| / |H3|) (dB). The 3·F0 component is more sensitive to glottal closure speed — an indirect Open Quotient marker. Read alongside H1H2 for reliability.",
        "metric.tooltip.maxCluster":         "ID of the dominant EGG-shape cluster in this cell: maxCluster = argmax_k count(cycle ∈ cluster_k). 1 to K (default K=5). Clusters come from K-means on each cycle's EGG harmonic vector — each cluster represents a typical glottal vibration shape.",
        "metric.tooltip.maxCPhon":           "ID of the dominant cPhon (voice-quality) cluster: maxCPhon = argmax_k count(cycle ∈ phon_k). cPhon runs K-means on a 9-D feature space (Clarity/CPP/SpecBal/Crest/Entropy/Qcontact/dEGGmax/Icontact/HRFegg).",
        "metric.tooltip.Cluster 1":          "Fraction of cycles in EGG cluster 1 (%): share = 100 · count(cycle ∈ cluster_1) / count(cycles in cell). Cluster IDs have no fixed semantics — interpret by looking at the relative distribution across all 5 clusters.",
        "metric.tooltip.Cluster 2":          "Fraction of cycles in EGG cluster 2 (%).",
        "metric.tooltip.Cluster 3":          "Fraction of cycles in EGG cluster 3 (%).",
        "metric.tooltip.Cluster 4":          "Fraction of cycles in EGG cluster 4 (%).",
        "metric.tooltip.Cluster 5":          "Fraction of cycles in EGG cluster 5 (%).",
        "metric.tooltip.cPhon 1":            "Fraction of cycles in voice-quality cluster 1 (%). Based on 9-D quality features: Clarity/CPP/SpecBal/Crest/Entropy/Qcontact/dEGGmax/Icontact/HRFegg.",
        "metric.tooltip.cPhon 2":            "Fraction of cycles in voice-quality cluster 2 (%).",
        "metric.tooltip.cPhon 3":            "Fraction of cycles in voice-quality cluster 3 (%).",
        "metric.tooltip.cPhon 4":            "Fraction of cycles in voice-quality cluster 4 (%).",
        "metric.tooltip.cPhon 5":            "Fraction of cycles in voice-quality cluster 5 (%).",
        "metric.tooltip.RMS":                "Time-domain root-mean-square: RMS = sqrt((1/N)·Σ x[n]²). Per-frame energy proxy for perceived loudness.",
        "metric.tooltip.F0_Hz":              "Fundamental frequency in Hz, derived from MIDI: F0 = 440 · 2^((MIDI − 69) / 12). MIDI 69 = A4 = 440 Hz. Male voices commonly 80-200 Hz, female 165-300 Hz, high sopranos 1000+ Hz.",
        "metric.tooltip.SpectralSlope":      "Spectral slope: linear_fit(log10|X(f)|, f) in 0-5 kHz, slope in dB/Hz. Negative = high-freq roll-off (dark, lax); near zero / positive = bright, tense. Indirect glottal-tension marker.",
        "metric.tooltip.SpectralSkewness":   "Spectral skewness: μ_3 / σ³, third standardised moment about the centroid. 0 = symmetric; positive = high-frequency tail (more energy above centroid); negative = low-frequency tail.",
        "metric.tooltip.SpectralKurtosis":   "Spectral kurtosis: μ_4 / σ⁴ − 3. 0 = Gaussian shape; positive = sharp peaks (energy concentrated at a few frequencies); negative = flat distribution (energy spread out).",
        "metric.tooltip.B1":                 "F1 formant bandwidth: B1 = -ln|z₁| · Fs / π, where z₁ is the LPC autoregressive pole corresponding to F1. Narrower bandwidth = sharper resonance, tenser tract. Healthy male voices typically 50-100 Hz.",
        "metric.tooltip.B2":                 "F2 formant bandwidth: same as B1, with z₂ the F2 pole.",
        "metric.tooltip.B3":                 "F3 formant bandwidth: same as B1, with z₃ the F3 pole.",
        "metric.tooltip.FormantDispersion":  "Formant dispersion: FD = (F3 − F1) / 2 (Hz). Proxy for vocal-tract length — longer tracts give smaller FD. Male typical FD ≈ 800 Hz, female ≈ 950 Hz.",
        "metric.tooltip.SPR":                "Singing Power Ratio: SPR = 10·log10(E[2-4 kHz] / E[0-2 kHz]) (dB). Energy ratio of the high band to the low band. Trained singers > -7 dB (singer's formant present); ordinary speech -25 to -15 dB.",
        "metric.tooltip.VibratoJitter":      "Vibrato regularity: coefficient of variation of vibrato cycle length T_vib[i] in a sliding window: CV = std(T_vib) / mean(T_vib) (%). Low = steady vibrato; high = wobbly, possibly tremor or tension.",
        "metric.tooltip.GNE":                "Glottal-to-Noise Excitation: maximum cross-correlation across multiple Hilbert envelopes of the glottal excitation signal. GNE ≈ 1 means clean excitation, ≈ 0 means noise-dominated. Simplified vocal-noise marker.",
        "metric.tooltip.DUV":                "Unvoiced fraction: DUV = 100 · (1 − VoicingRatio) (%). Fraction of frames that are unvoiced (consonants, pauses, gaps). Complementary to VoicingRatio. In MPT testing, DUV < 15% is normal.",
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
