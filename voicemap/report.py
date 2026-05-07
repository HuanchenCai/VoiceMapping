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
from pathlib import Path
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
}

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

    # ── 总览 ────
    a("## 一、总览")
    a("")
    overall_lines = []
    for col in ("F0_Hz", "MPT", "VoicingRatio"):
        line = _summary_row(df, col)
        if line:
            overall_lines.append(line)
    if overall_lines:
        lines.extend(overall_lines)
        a("")

    # ── 嗓音质量（声学，最关键临床指标） ────
    a("## 二、嗓音质量（声学）")
    a("")
    quality_cols = ("HNR", "NHR", "CPP", "CPPS",
                     "Jitter", "JitterRAP", "JitterPPQ5",
                     "Shimmer", "ShimmerDB", "ShimmerAPQ11")
    out = []
    for col in quality_cols:
        line = _summary_row(df, col)
        if line:
            out.append(line)
    if out:
        lines.extend(out)
    else:
        a("_无可用数据_")
    a("")

    # ── EGG ────
    a("## 三、EGG · 声门接触特征")
    a("")
    egg_cols = ("Qcontact", "Icontact", "dEGGmax", "HRFegg",
                 "OQ", "SPQ", "CIQ")
    out = []
    for col in egg_cols:
        line = _summary_row(df, col)
        if line:
            out.append(line)
    if out:
        lines.extend(out)
    a("")

    # ── 唱歌特征 ────
    a("## 四、唱歌特征")
    a("")
    singing_cols = ("VibratoRate", "VibratoExtent", "VibratoJitter",
                     "F1", "F2", "F3", "B1", "B2", "B3",
                     "FormantDispersion", "SingersFormant", "SPR",
                     "H1H2", "H1H3")
    out = []
    for col in singing_cols:
        line = _summary_row(df, col)
        if line:
            out.append(line)
    if out:
        lines.extend(out)
    a("")

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
