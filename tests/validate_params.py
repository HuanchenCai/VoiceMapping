#!/usr/bin/env python3
"""
Parameter-extraction validation — systematic regression tests.

Runs four kinds of check against a reference recording:

  1. Praat cross-check      Compare each voice-mic metric to Praat
                             (parselmouth). Report per-metric Δ%.
  2. Range sanity           Every metric falls inside its documented
                             plausible range (e.g. OQ ∈ [0, 1]).
  3. Structural sanity      maxCluster / maxCPhon ∈ {1..k} on all
                             non-empty cells, no all-zero columns
                             where data is expected.
  4. Internal consistency   CPP vs CPPS, HNR vs NHR etc. should
                             satisfy mathematical relationships.

Each check produces one of:  PASS  / WARN  / FAIL.
Results are printed as a table AND written to `result/validation_report.json`
so CI / downstream scripts can machine-read them.

Praat cross-check intentionally does NOT demand exact match — cycle
segmentation is different (EGG vs voice-autocorr) so Jitter/Shimmer run
2-4× Praat's by design. Tolerances reflect those methodological gaps.

Run:
  python tests/validate_params.py [path/to/wav]
"""

import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
import parselmouth
from parselmouth.praat import call as praat_call

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from config import VoiceMapConfig          # noqa: E402
from analyzer import VoiceMapAnalyzer      # noqa: E402


# ─── Result records ──────────────────────────────────────────────────────────
@dataclass
class Check:
    name: str
    category: str              # "praat" | "range" | "structural" | "consistency"
    status: str                # "PASS" | "WARN" | "FAIL"
    ours: Optional[float]
    praat: Optional[float]
    expected_range: Optional[tuple]
    delta_pct: Optional[float]
    note: str

    def to_dict(self):
        return asdict(self)


# ─── Formatting ──────────────────────────────────────────────────────────────
_COLOR = {"PASS": "\033[32m", "WARN": "\033[33m", "FAIL": "\033[31m"}
_RESET = "\033[0m"

def _fmt(v):
    if v is None: return "   —"
    if isinstance(v, (int, np.integer)): return f"{v:7d}"
    if isinstance(v, float) and np.isnan(v): return "   nan"
    return f"{v:7.3f}"

def _pct(v):
    if v is None: return "     —"
    return f"{v:+6.1f}%"


def _print_table(checks):
    print(f"\n{'Metric':22s} {'Ours':>8s} {'Praat':>8s} {'Δ%':>8s}  Status  Note")
    print("-" * 84)
    for c in checks:
        col = _COLOR.get(c.status, "")
        print(f"{c.name:22s} {_fmt(c.ours)} {_fmt(c.praat)} {_pct(c.delta_pct)}  "
              f"{col}{c.status:5s}{_RESET}  {c.note}")


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _nz_mean(arr):
    arr = np.asarray(arr)
    nz = arr[arr != 0]
    return float(nz.mean()) if len(nz) else float("nan")


def _classify_praat_delta(delta_pct, metric_name):
    """Return (status, note) given the known methodological gap."""
    if delta_pct is None or np.isnan(delta_pct):
        return "FAIL", "no value"
    abs_d = abs(delta_pct)
    # EGG vs voice-autocorr segmentation — Jitter can legitimately run
    # 3-4× Praat's. Still PASS if within documented spread.
    if metric_name.startswith("Jitter"):
        if abs_d < 400: return "WARN", "EGG-seg methodological gap (expected)"
        return "FAIL", "too far from Praat even for EGG seg"
    # Shimmer: closer match expected
    if metric_name.startswith("Shimmer"):
        if abs_d < 60:  return "PASS", "within shimmer spread"
        if abs_d < 200: return "WARN", "higher than typical spread"
        return "FAIL", "way off"
    # HNR: silent-frame handling differs
    if metric_name == "HNR":
        if abs_d < 50:  return "PASS", "within silent-frame handling gap"
        return "WARN", "larger than expected"
    # Formants: LPC method gap
    if metric_name.startswith("F"):
        if abs_d < 30:  return "PASS", "within LPC method spread"
        if abs_d < 60:  return "WARN", "larger than expected"
        return "FAIL", "too far"
    # Default: 20% tolerance
    if abs_d < 20:  return "PASS", ""
    if abs_d < 50:  return "WARN", ""
    return "FAIL", ""


# ─── The checks ──────────────────────────────────────────────────────────────
def run_validation(wav_path: str):
    print(f"\nValidating: {wav_path}\n" + "=" * 84)
    checks: list[Check] = []

    # ─ Run our analyzer ─
    a = VoiceMapAnalyzer(VoiceMapConfig(clarity_threshold=0.96,
                                          output_dir="result"))
    data, _, df = a.analyze_and_output_vrp(
        wav_path, return_df=True, plot_mode="none")

    # ─ Run Praat on the voice channel ─
    snd = parselmouth.Sound(wav_path)
    voice = praat_call(snd, "Extract one channel", 1) if snd.n_channels > 1 else snd
    pp = praat_call(voice, "To PointProcess (periodic, cc)", 60, 600)
    pf = 1.3
    af = 1.6
    pr = {
        "Jitter":       praat_call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, pf) * 100,
        "JitterRAP":    praat_call(pp, "Get jitter (rap)",   0, 0, 0.0001, 0.02, pf) * 100,
        "JitterPPQ5":   praat_call(pp, "Get jitter (ppq5)",  0, 0, 0.0001, 0.02, pf) * 100,
        "Shimmer":      praat_call([voice, pp], "Get shimmer (local)",    0, 0, 0.0001, 0.02, pf, af) * 100,
        "ShimmerDB":    praat_call([voice, pp], "Get shimmer (local_dB)", 0, 0, 0.0001, 0.02, pf, af),
        "ShimmerAPQ3":  praat_call([voice, pp], "Get shimmer (apq3)",     0, 0, 0.0001, 0.02, pf, af) * 100,
        "ShimmerAPQ5":  praat_call([voice, pp], "Get shimmer (apq5)",     0, 0, 0.0001, 0.02, pf, af) * 100,
        "ShimmerAPQ11": praat_call([voice, pp], "Get shimmer (apq11)",    0, 0, 0.0001, 0.02, pf, af) * 100,
    }
    harm = voice.to_harmonicity_cc(time_step=0.01, minimum_pitch=75.0,
                                    silence_threshold=0.1, periods_per_window=4.5)
    pr["HNR"] = praat_call(harm, "Get mean", 0, 0)

    # Formants
    fmt = voice.to_formant_burg(time_step=0.01, max_number_of_formants=5,
                                 maximum_formant=5500.0, window_length=0.025,
                                 pre_emphasis_from=50.0)
    n_frames = fmt.get_number_of_frames()
    for f_idx, key in ((1, "F1"), (2, "F2"), (3, "F3")):
        vals = []
        for i in range(1, n_frames + 1):
            v = fmt.get_value_at_time(f_idx, fmt.get_time_from_frame_number(i))
            if np.isfinite(v):
                vals.append(v)
        pr[key] = float(np.mean(vals)) if vals else float("nan")

    # ─ Praat-comparable metrics ─
    praat_map = {
        "Jitter":       _nz_mean(data["jitter"]),
        "JitterRAP":    _nz_mean(data["jitter_rap"]),
        "JitterPPQ5":   _nz_mean(data["jitter_ppq5"]),
        "Shimmer":      _nz_mean(data["shimmer"]),
        "ShimmerDB":    _nz_mean(data["shimmer_db"]),
        "ShimmerAPQ3":  _nz_mean(data["shimmer_apq3"]),
        "ShimmerAPQ5":  _nz_mean(data["shimmer_apq5"]),
        "ShimmerAPQ11": _nz_mean(data["shimmer_apq11"]),
        "HNR":          _nz_mean(data["hnr"]),
        "F1":           _nz_mean(data["f1"]),
        "F2":           _nz_mean(data["f2"]),
        "F3":           _nz_mean(data["f3"]),
    }
    for name, ours in praat_map.items():
        praat_v = pr.get(name)
        delta = None
        if praat_v and not np.isnan(praat_v) and praat_v != 0:
            delta = 100.0 * (ours - praat_v) / abs(praat_v)
        status, note = _classify_praat_delta(delta, name)
        checks.append(Check(name=name, category="praat", status=status,
                             ours=ours, praat=praat_v, expected_range=None,
                             delta_pct=delta, note=note))

    # ─ Range sanity ─ (lo ≤ aggregated value ≤ hi)
    range_checks = [
        ("Clarity",        0.80, 1.0),
        ("CPP",            0.0,  40.0),
        ("CPPS",           0.0,  40.0),
        ("SpecBal",       -50.0, 10.0),
        ("Crest",          1.0,  10.0),
        ("Entropy",        0.0,  20.0),
        ("Qcontact",       0.0,  1.0),
        ("Icontact",       0.0,  1.5),
        ("dEGGmax",        0.0,  50.0),
        ("HRFegg",       -80.0,  20.0),
        ("OQ",             0.0,  1.0),
        ("SPQ",            0.0,  10.0),
        ("CIQ",           -1.0,  1.0),
        ("NHR",            0.0,  10.0),
        ("PPE",            0.0,  1.0),
        ("ZCR",            0.0,  1.0),
        ("VibratoRate",    0.0,  10.0),
        ("VibratoExtent",  0.0,  500.0),
    ]
    for col, lo, hi in range_checks:
        if col not in df.columns:
            checks.append(Check(col, "range", "FAIL", None, None, (lo, hi),
                                 None, "missing column"))
            continue
        vals = df[col].values
        if len(vals) == 0:
            status = "WARN"; note = "no cells"
        elif np.any(vals < lo - 1e-6) or np.any(vals > hi + 1e-6):
            bad_lo = int(np.sum(vals < lo - 1e-6))
            bad_hi = int(np.sum(vals > hi + 1e-6))
            status = "FAIL"; note = f"{bad_lo} < lo, {bad_hi} > hi"
        else:
            status = "PASS"; note = f"all in [{lo}, {hi}]"
        checks.append(Check(col, "range", status, float(vals.mean()), None,
                             (lo, hi), None, note))

    # ─ Structural sanity ─
    for max_col, n in (("maxCluster", 5), ("maxCPhon", 5)):
        vals = df[max_col].values
        nz = vals[vals > 0]
        in_range = np.all((nz >= 1) & (nz <= n)) if len(nz) else True
        unique = set(int(x) for x in nz)
        all_present = unique == set(range(1, n + 1))
        if not in_range:
            s, note = "FAIL", f"values outside 1..{n}"
        elif not all_present:
            missing = set(range(1, n + 1)) - unique
            s, note = "WARN", f"missing label(s) {sorted(missing)}"
        else:
            s, note = "PASS", f"all {n} labels present"
        checks.append(Check(max_col, "structural", s, None, None, (1, n),
                             None, note))

    # ─ Internal consistency ─
    # Per-cycle (not mean-of): nhr[i] should be 1/10^(hnr[i]/10). Mean-of
    # would mismatch due to Jensen's inequality on the exp.
    hnr_arr = np.asarray(data["hnr"])
    nhr_arr = np.asarray(data["nhr"])
    good = (hnr_arr != 0) & (nhr_arr > 0)
    if good.any():
        expected = 1.0 / np.power(10.0, hnr_arr[good] / 10.0)
        rel = np.abs(nhr_arr[good] - expected) / np.maximum(expected, 1e-12)
        max_rel = float(np.max(rel))
        status, note = ("PASS", f"pointwise max err {max_rel*100:.1f}%") \
            if max_rel < 0.05 else \
            ("WARN", f"pointwise max err {max_rel*100:.0f}%")
        checks.append(Check("NHR vs HNR (per-cycle)", "consistency", status,
                             float(nhr_arr[good].mean()),
                             float(expected.mean()),
                             None, None, note))

    # CPPS should be close to CPP (it's a temporal smoothing)
    cpp_mean  = _nz_mean(data["cpp"])
    cpps_mean = _nz_mean(data["cpps"])
    if np.isfinite(cpp_mean) and np.isfinite(cpps_mean):
        rel = abs(cpps_mean - cpp_mean) / max(cpp_mean, 1e-9)
        status = "PASS" if rel < 0.1 else "WARN"
        checks.append(Check("CPPS ≈ CPP", "consistency", status,
                             cpps_mean, cpp_mean, None, rel * 100, "smoothed"))

    # ─ Report ─
    _print_table(checks)

    by_status = {}
    for c in checks:
        by_status[c.status] = by_status.get(c.status, 0) + 1
    print()
    print(f"Summary:  PASS={by_status.get('PASS',0)}  "
          f"WARN={by_status.get('WARN',0)}  "
          f"FAIL={by_status.get('FAIL',0)}  (total {len(checks)})")

    report = {
        "wav": wav_path,
        "summary": by_status,
        "checks": [c.to_dict() for c in checks],
    }
    report_path = os.path.join(ROOT, "result", "validation_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nFull report: {report_path}")

    # Exit code reflects FAIL count — handy for CI
    return by_status.get("FAIL", 0)


if __name__ == "__main__":
    wav = sys.argv[1] if len(sys.argv) > 1 else "audio/test_Voice_EGG.wav"
    if not os.path.exists(wav):
        print(f"WAV not found: {wav}", file=sys.stderr)
        sys.exit(1)
    sys.exit(min(run_validation(wav), 255))
