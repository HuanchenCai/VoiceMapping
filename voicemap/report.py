#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clinical narrative report — one .md / .txt file per analysis.

Walks the grouped DataFrame, looks up each metric's clinical thresholds,
writes a human-readable summary saying what the voice "looks like" with
the metric values and what they mean.

The threshold tables below are condensed from the literature already
cited inline in the metric calculator classes. A value's `band` is the
first range it falls into, and the band label is rendered into the
narrative.
"""

import os
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


# ─── Per-metric clinical thresholds ──────────────────────────────────────────
# Each entry: list of (lower, upper, label, severity) — first match wins.
# severity: "good" / "normal" / "watch" / "abnormal"
_THRESHOLDS: Dict[str, List[Tuple[float, float, str, str]]] = {
    # Acoustic — perturbation
    "Jitter": [
        (0.0,    1.04,  "正常",                                "normal"),
        (1.04,   2.0,   "轻度异常",                            "watch"),
        (2.0,   1e9,    "病理",                                "abnormal"),
    ],
    "Shimmer": [
        (0.0,    3.81,  "正常",                                "normal"),
        (3.81,   6.0,   "轻度异常",                            "watch"),
        (6.0,   1e9,    "病理",                                "abnormal"),
    ],
    "ShimmerDB": [
        (0.0,    0.35,  "正常",                                "normal"),
        (0.35,   0.7,   "轻度异常",                            "watch"),
        (0.7,   1e9,    "病理",                                "abnormal"),
    ],
    # Acoustic — quality
    "HNR": [
        (-1e9,   10.0,  "可能病理",                            "abnormal"),
        (10.0,   20.0,  "中等",                                "watch"),
        (20.0,   35.0,  "健康",                                "normal"),
        (35.0,  1e9,    "极佳",                                "good"),
    ],
    "NHR": [
        (0.0,    0.13,  "正常",                                "normal"),
        (0.13,   0.19,  "临界",                                "watch"),
        (0.19,  1e9,    "病理",                                "abnormal"),
    ],
    "CPP": [
        (-1e9,   8.0,   "可能气声",                            "watch"),
        (8.0,    14.0,  "中等",                                "normal"),
        (14.0,   25.0,  "健康",                                "good"),
        (25.0,  1e9,    "极佳",                                "good"),
    ],
    "Clarity": [
        (0.96,   1.0,   "高置信度",                            "good"),
        (-1e9,   0.96,  "置信度偏低",                          "watch"),
    ],
    # Singing-specific
    "VibratoRate": [
        (0.0,    3.0,   "无显著颤音",                           "normal"),
        (3.0,    5.0,   "慢颤音",                              "normal"),
        (5.0,    7.0,   "典型颤音",                            "good"),
        (7.0,   10.0,   "快颤音",                              "watch"),
        (10.0,  1e9,    "异常颤动",                            "abnormal"),
    ],
    "VibratoExtent": [
        (0.0,   30.0,   "颤音弱",                              "normal"),
        (30.0,  100.0,  "颤音中等",                            "normal"),
        (100.0, 200.0,  "颤音明显",                            "good"),
        (200.0, 1e9,    "颤音偏宽",                            "watch"),
    ],
    "SingersFormant": [
        (-1e9,  -13.0,  "无明显共振峰",                        "normal"),
        (-13.0, -7.0,   "共振峰显著",                          "good"),
        (-7.0,  1e9,    "共振峰极强",                          "good"),
    ],
    "H1H2": [
        (-1e9,   0.0,   "压声 / 紧张",                          "watch"),
        (0.0,    6.0,   "正常嗓音",                            "normal"),
        (6.0,   1e9,    "气声 / 松弛",                          "watch"),
    ],
    # EGG
    "Qcontact": [
        (0.0,    0.3,   "接触不足，气声型",                     "watch"),
        (0.3,    0.6,   "正常接触",                            "normal"),
        (0.6,   1e9,    "接触过强，挤压型",                     "watch"),
    ],
    "OQ": [
        (0.0,    0.4,   "开商低，挤压声型",                     "watch"),
        (0.4,    0.7,   "开商正常，模态",                       "normal"),
        (0.7,   1e9,    "开商高，气声型",                       "watch"),
    ],
    # Density / 整曲级
    "MPT": [
        (0.0,   10.0,   "短",                                  "watch"),
        (10.0,  20.0,   "中等",                                "normal"),
        (20.0,  1e9,    "良好",                                "good"),
    ],
    "VoicingRatio": [
        (0.0,    0.5,   "偏低",                                "watch"),
        (0.5,    0.85,  "正常",                                "normal"),
        (0.85,  1e9,    "高比例浊音",                          "good"),
    ],
    # ── batch 2: extra reference ranges per user spec ──
    # Crest factor: 1.4-2.0 typical for speech, < 1.5 = saturated /
    # over-compressed, > 3 = transient-heavy. Cite: Boersma & Weenink
    # Praat manual §intensity, default expected range.
    "Crest": [
        (-1e9,   1.4,   "饱和 / 过压缩",                        "watch"),
        (1.4,    2.0,   "典型语音",                            "normal"),
        (2.0,    3.0,   "动态丰富",                            "good"),
        (3.0,   1e9,    "瞬态主导",                            "watch"),
    ],
    # SpecBal (10·log10(E_low / E_high), 1500 Hz cut): around 0 dB =
    # balanced; > 0 = darker; < 0 = brighter. Voice clinic norm
    # typically -10 to +10 dB.
    "SpecBal": [
        (-1e9,   -10.0, "明亮 / 高频主导",                      "watch"),
        (-10.0,   10.0, "平衡",                                "normal"),
        (10.0,   1e9,   "暗哑 / 低频主导",                      "watch"),
    ],
    # SpectralFlatness (Wiener entropy): 0 = pure tone, 1 = white noise.
    # Voiced speech 0.05-0.30; > 0.5 indicates noise dominance.
    "SpectralFlatness": [
        (0.0,    0.05,  "纯音化",                              "watch"),
        (0.05,   0.30,  "典型嗓音",                            "normal"),
        (0.30,   0.50,  "噪声偏多",                            "watch"),
        (0.50,  1e9,    "噪声主导",                            "abnormal"),
    ],
    # AlphaRatio (10·log10(E[50-1000] / E[1-5kHz])):
    # +ve = lax / dark; -ve = tense / bright. Eyben et al. clinical
    # voice norms: -10 to +10 dB normal range.
    "AlphaRatio": [
        (-1e9,   -10.0, "声门绷紧 / 偏亮",                      "watch"),
        (-10.0,   10.0, "正常",                                "normal"),
        (10.0,   1e9,   "声门松弛 / 偏暗",                      "watch"),
    ],
    # HammarbergIndex: typical voice 15-30 dB. > 35 dB = breathy /
    # depressed; < 10 dB = pressed / aroused. (Hammarberg 1980 study
    # on dysphonic voices.)
    "HammarbergIndex": [
        (-1e9,   10.0,  "压制 / 紧张",                          "watch"),
        (10.0,   30.0,  "正常",                                "normal"),
        (30.0,  1e9,    "气声 / 低沉",                          "watch"),
    ],
    # DUV (% unvoiced): inverse of VoicingRatio. < 15% normal sustained
    # phonation; > 50% suggests breathy / interrupted phonation.
    "DUV": [
        (0.0,    15.0,  "正常",                                "normal"),
        (15.0,   50.0,  "中度断点",                            "watch"),
        (50.0,  1e9,    "高度断点 / 气声",                      "abnormal"),
    ],
    # Entropy (sample-entropy on EGG harmonics): 0 = perfectly
    # repeating, > 1.5 = chaotic. Healthy voice 0.3-1.0.
    "Entropy": [
        (-1e9,   0.3,   "高度规律",                            "good"),
        (0.3,    1.0,   "正常",                                "normal"),
        (1.0,   1e9,    "无序振动",                            "watch"),
    ],
    # SPR (Singing Power Ratio): trained singers > -7 dB indicates
    # presence of singer's formant; speech voices typically -25 to -15 dB.
    "SPR": [
        (-1e9,   -25.0, "无歌者共振",                          "normal"),
        (-25.0,  -10.0, "中等共振",                            "normal"),
        (-10.0,  1e9,   "强烈歌者共振",                        "good"),
    ],
}

# English translations of the band labels above. Indexed by zh string
# so the GUI's `_inspector_set_clinical` can swap labels at render time
# without touching `_THRESHOLDS` (which the report.md generator still
# wants in zh). If a zh label is missing here, the zh label falls
# through unchanged.
_THRESHOLDS_LABEL_EN: Dict[str, str] = {
    "正常":             "normal",
    "轻度异常":         "mildly abnormal",
    "病理":             "pathological",
    "可能病理":         "likely pathological",
    "中等":             "intermediate",
    "健康":             "healthy",
    "极佳":             "excellent",
    "临界":             "borderline",
    "可能气声":         "possibly breathy",
    "高置信度":         "high confidence",
    "置信度偏低":       "low confidence",
    "无显著颤音":       "no clear vibrato",
    "慢颤音":           "slow vibrato",
    "典型颤音":         "typical vibrato",
    "快颤音":           "fast vibrato",
    "异常颤动":         "abnormal tremor",
    "颤音弱":           "weak vibrato",
    "颤音中等":         "moderate vibrato",
    "颤音明显":         "strong vibrato",
    "颤音偏宽":         "wide vibrato",
    "无明显共振峰":     "no clear formant",
    "共振峰显著":       "clear formant",
    "共振峰极强":       "very strong formant",
    "压声 / 紧张":      "pressed / tense",
    "正常嗓音":         "normal voice",
    "气声 / 松弛":      "breathy / lax",
    "接触不足，气声型": "under-contact, breathy",
    "正常接触":         "normal contact",
    "接触过强，挤压型": "over-contact, pressed",
    "开商低，挤压声型": "low OQ, pressed",
    "开商正常，模态":   "normal OQ, modal",
    "开商高，气声型":   "high OQ, breathy",
    "短":               "short",
    "良好":             "good",
    "偏低":             "low",
    "高比例浊音":       "high voicing",
    # batch 2 — Crest / SpecBal / SpectralFlatness / AlphaRatio /
    # HammarbergIndex / DUV / Entropy / SPR
    "饱和 / 过压缩":    "saturated / over-compressed",
    "典型语音":         "typical speech",
    "动态丰富":         "dynamic-rich",
    "瞬态主导":         "transient-dominated",
    "明亮 / 高频主导":  "bright / high-freq dominated",
    "平衡":             "balanced",
    "暗哑 / 低频主导":  "dark / low-freq dominated",
    "纯音化":           "tonal",
    "典型嗓音":         "typical voice",
    "噪声偏多":         "noisy",
    "噪声主导":         "noise-dominated",
    "声门绷紧 / 偏亮":  "tight glottis / bright",
    "声门松弛 / 偏暗":  "lax glottis / dark",
    "压制 / 紧张":      "pressed / tense",
    "气声 / 低沉":      "breathy / muffled",
    "中度断点":         "moderately broken",
    "高度断点 / 气声":  "highly broken / breathy",
    "高度规律":         "highly regular",
    "无序振动":         "disordered vibration",
    "无歌者共振":       "no singer's formant",
    "中等共振":         "moderate resonance",
    "强烈歌者共振":     "strong singer's formant",
}

def get_band_label(zh_label: str, lang: str) -> str:
    """Map a `_THRESHOLDS` band label to the active language. Returns
    the original zh string when lang != 'en' or when no en mapping
    exists — graceful fallback so the GUI never shows a missing key."""
    if lang == "en":
        return _THRESHOLDS_LABEL_EN.get(zh_label, zh_label)
    return zh_label

# Severity → emoji + colour for plain-text rendering
_SEVERITY_TAG = {
    "good":     "✓ 良好",
    "normal":   "· 正常",
    "watch":    "! 关注",
    "abnormal": "✗ 异常",
}


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _classify(metric: str, value: float) -> Tuple[str, str]:
    """Return (label, severity) for a metric value, or (None, None) if no rule."""
    rules = _THRESHOLDS.get(metric)
    if rules is None or value is None or not np.isfinite(value):
        return None, None
    for lo, hi, label, sev in rules:
        if lo <= value < hi:
            return label, sev
    return None, None


def _safe_mean(s: pd.Series) -> float:
    arr = pd.to_numeric(s, errors="coerce")
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return float("nan")
    return float(arr.mean())


def _emit_section(lines: list, title: str, df: pd.DataFrame,
                  cols, fallback: str | None = None) -> None:
    """Render one '## section\\n\\nbody\\n' block. body is the
    `_summary_row` for each column that exists with finite data.
    If no rows produce output, write `fallback` (or skip body when
    fallback is None). Cuts ~10 lines × 4 sections of repetition."""
    a = lines.append
    a(f"## {title}")
    a("")
    out = [r for r in (_summary_row(df, c) for c in cols) if r]
    if out:
        lines.extend(out)
    elif fallback is not None:
        a(fallback)
    a("")


def _summary_row(df: pd.DataFrame, col: str, prefer_max: bool = False) -> str:
    if col not in df.columns:
        return ""
    s = pd.to_numeric(df[col], errors="coerce")
    s = s[np.isfinite(s)]
    if len(s) == 0:
        return ""
    if prefer_max:
        v = float(s.max())
    else:
        v = float(s.mean())
    label, sev = _classify(col, v)
    tag = _SEVERITY_TAG.get(sev, "")
    if label:
        return f"- **{col}**: {v:.3f} — {label} {tag}"
    return f"- **{col}**: {v:.3f}"


# ─── Main entry ──────────────────────────────────────────────────────────────
def generate_report(grouped_df: pd.DataFrame,
                    out_path: str,
                    audio_name: str = "(unknown)",
                    title: str = "嗓音声学分析报告") -> str:
    """
    Write a clinical narrative report to `out_path` (.md or .txt).
    Returns the absolute path written.
    """
    df = grouped_df
    n_cells = len(df)
    midi_min = int(df["MIDI"].min()) if "MIDI" in df else 0
    midi_max = int(df["MIDI"].max()) if "MIDI" in df else 0
    spl_min  = int(df["dB"].min())   if "dB"   in df else 0
    spl_max  = int(df["dB"].max())   if "dB"   in df else 0
    total_cycles = int(df["Total"].sum()) if "Total" in df else 0

    lines = []
    a = lines.append

    a(f"# {title}")
    a("")
    a(f"- **文件**: `{audio_name}`")
    a(f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    a(f"- **覆盖范围**: MIDI {midi_min}–{midi_max} ({_midi_range_to_pitch(midi_min, midi_max)})  |  SPL {spl_min}–{spl_max} dB")
    a(f"- **数据点**: {n_cells} 个 (MIDI, dB) 网格 cell, 共 {total_cycles:,} 个声门周期")
    a("")
    a("> 本报告依据已发表的临床阈值对每项指标自动分级。"
      "**·** = 正常区间，**!** = 需关注，**✗** = 异常，**✓** = 良好。"
      "受限于自动算法和录音质量，本报告**不构成诊断**，仅供研究 / 筛查参考。")
    a("")

    _emit_section(lines, "一、总览", df,
                  ("F0_Hz", "MPT", "VoicingRatio"))
    _emit_section(lines, "二、嗓音质量（声学）", df,
                  ("HNR", "NHR", "CPP", "CPPS",
                   "Jitter", "JitterRAP", "JitterPPQ5",
                   "Shimmer", "ShimmerDB", "ShimmerAPQ11"),
                  fallback="_无可用数据_")
    _emit_section(lines, "三、EGG · 声门接触特征", df,
                  ("Qcontact", "Icontact", "dEGGmax", "HRFegg",
                   "OQ", "SPQ", "CIQ"))
    _emit_section(lines, "四、唱歌特征", df,
                  ("VibratoRate", "VibratoExtent", "VibratoJitter",
                   "F1", "F2", "F3", "B1", "B2", "B3",
                   "FormantDispersion", "SingersFormant", "SPR",
                   "H1H2", "H1H3"))

    # ── 频谱特征（M1） ────
    spec_cols = ("RMS", "SpectralCentroid", "SpectralBandwidth",
                  "SpectralRolloff85", "SpectralFlatness",
                  "SpectralSlope", "AlphaRatio", "HammarbergIndex")
    out = []
    for col in spec_cols:
        if col not in df.columns:
            continue
        v = _safe_mean(df[col])
        if not np.isfinite(v):
            continue
        out.append(f"- **{col}**: {v:.3f}")
    if out:
        a("## 五、频谱形态特征")
        a("")
        lines.extend(out)
        a("")

    # ── 自动建议 ────
    a("## 六、自动观察")
    a("")
    obs = _build_observations(df)
    if obs:
        for o in obs:
            a(f"- {o}")
    else:
        a("- 各项指标均在文献参考范围内。")
    a("")

    # ── 附：完整原始数值 ────
    a("---")
    a("")
    a("### 附录：完整原始指标")
    a("")
    a("| 指标 | 均值 | 中位数 | 最小 | 最大 |")
    a("|---|---:|---:|---:|---:|")
    metric_cols = [c for c in df.columns
                    if c not in ("MIDI", "dB") and pd.api.types.is_numeric_dtype(df[c])]
    for col in metric_cols:
        s = pd.to_numeric(df[col], errors="coerce")
        s = s[np.isfinite(s)]
        if len(s) == 0:
            continue
        a(f"| {col} | {s.mean():.3f} | {np.median(s):.3f} | {s.min():.3f} | {s.max():.3f} |")

    text = "\n".join(lines) + "\n"
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return os.path.abspath(out_path)


def _midi_range_to_pitch(lo: int, hi: int) -> str:
    """30 → F#1, 96 → C8 etc."""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    def _name(m):
        if m <= 0:
            return "—"
        return f"{names[m % 12]}{m // 12 - 1}"
    return f"{_name(lo)} – {_name(hi)}"


def _build_observations(df: pd.DataFrame) -> List[str]:
    """Generate auto-observations from threshold violations."""
    obs = []
    findings = []
    for col in _THRESHOLDS:
        if col not in df.columns:
            continue
        v = _safe_mean(df[col])
        if not np.isfinite(v):
            continue
        label, sev = _classify(col, v)
        if sev in ("watch", "abnormal"):
            findings.append((col, v, label, sev))

    if not findings:
        return []

    abnormal = [f for f in findings if f[3] == "abnormal"]
    watch    = [f for f in findings if f[3] == "watch"]

    if abnormal:
        names = ", ".join(f"**{f[0]}**" for f in abnormal)
        obs.append(f"以下指标进入**病理范围**，建议进一步专业评估：{names}")
    if watch:
        names = ", ".join(f"**{f[0]}**" for f in watch)
        obs.append(f"以下指标处于**临界 / 关注**区间：{names}")

    # Cross-metric heuristics
    if "Jitter" in df.columns and "Shimmer" in df.columns:
        j = _safe_mean(df["Jitter"])
        s = _safe_mean(df["Shimmer"])
        if np.isfinite(j) and np.isfinite(s) and j > 1.04 and s > 3.81:
            obs.append("Jitter 与 Shimmer 同时偏高，提示声门源不稳定（可能粗糙 / 噪声型嗓音）。")

    if "H1H2" in df.columns and "Qcontact" in df.columns:
        h12 = _safe_mean(df["H1H2"])
        qc  = _safe_mean(df["Qcontact"])
        if np.isfinite(h12) and np.isfinite(qc):
            if h12 > 6 and qc < 0.3:
                obs.append("H1-H2 偏高且 Qcontact 偏低 → 气声型发声特征。")
            if h12 < 0 and qc > 0.6:
                obs.append("H1-H2 偏低且 Qcontact 偏高 → 压声 / 紧张型发声特征。")

    if "VibratoRate" in df.columns and "VibratoExtent" in df.columns:
        vr = _safe_mean(df["VibratoRate"])
        ve = _safe_mean(df["VibratoExtent"])
        if np.isfinite(vr) and np.isfinite(ve) and 5.0 <= vr <= 7.0 and 100.0 <= ve <= 250.0:
            obs.append("颤音速率与幅度均处于戏剧 / 戏曲表演的典型区间，颤音表现良好。")

    return obs
