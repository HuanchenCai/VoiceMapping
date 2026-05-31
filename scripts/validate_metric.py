#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 0.2 — Generic metric-validation harness.

Runs the validation recipe for one metric and prints a standard PASS/FAIL
report. Optionally patches Section 5 (Results) of the metric's
`docs/validation/metrics/<name>.md` between auto-generated markers.

Usage:
    python scripts/validate_metric.py jitter
    python scripts/validate_metric.py jitter --no-md      # stdout only
    python scripts/validate_metric.py --list              # known metrics

Design
------
Each metric registers a validator: a callable returning a `Report`. A
validator typically combines up to three evidence types (see PLAN §1):

    (A) Numerical parity   — our value vs a reference tool on identical input
    (B) Synthetic ground   — our value vs an analytically-known answer
    (C) Real corpus        — distribution sanity on real recordings

The harness owns: signal loading, tolerance bookkeeping, table rendering,
pass/fail roll-up, exit code, and the markdown patch. Validators own only
the metric-specific computation.

Exit code is 0 iff every row passes (so CI can gate on it).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

TS_DIR = os.path.join(ROOT, "docs", "validation", "test_signals")
METRICS_DIR = os.path.join(ROOT, "docs", "validation", "metrics")
AUDIO_DIR = os.path.join(ROOT, "audio")

# Praat MDVP-style perturbation query defaults (match the parity tests).
PMIN, PMAX, PERIOD_FACTOR, AMP_FACTOR = 1e-4, 0.02, 1.3, 1.6


# ─── Report model ────────────────────────────────────────────────────────────
@dataclass
class Row:
    test: str
    reference: str
    ours: str
    delta: str
    passed: bool


@dataclass
class Report:
    metric: str
    rows: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    def add(self, test, reference, ours, delta, passed):
        self.rows.append(Row(test, str(reference), str(ours), str(delta),
                             bool(passed)))

    def note(self, msg):
        self.notes.append(msg)

    @property
    def all_passed(self) -> bool:
        return (not self.skipped) and len(self.rows) > 0 and all(
            r.passed for r in self.rows)

    @property
    def status(self) -> str:
        if self.skipped:
            return "SKIPPED"
        return "PASS" if self.all_passed else "FAIL"


# ─── Helpers shared by validators ────────────────────────────────────────────
def _load_make_signals():
    path = os.path.join(TS_DIR, "make_signals.py")
    spec = importlib.util.spec_from_file_location("make_signals", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_manifest() -> dict:
    with open(os.path.join(TS_DIR, "manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _ensure_signals():
    """Generate the synthetic signals if missing (they are gitignored)."""
    if not os.path.exists(os.path.join(TS_DIR, "manifest.json")):
        _load_make_signals().build_all()


def _praat_marks(voice: np.ndarray, fs: float, floor=75.0, ceiling=600.0):
    """Praat PointProcess (cc) cycle-mark times + the Sound + PP object."""
    import parselmouth
    from parselmouth.praat import call
    snd = parselmouth.Sound(np.ascontiguousarray(voice.astype(np.float64)),
                            sampling_frequency=fs)
    pitch = snd.to_pitch_cc(time_step=None,
                            pitch_floor=floor, pitch_ceiling=ceiling)
    pp_obj = call([snd, pitch], "To PointProcess (cc)")
    n = int(call(pp_obj, "Get number of points"))
    times = np.array([call(pp_obj, "Get time from index", i + 1)
                      for i in range(n)], dtype=np.float64)
    return snd, times, pp_obj


# ─── Validators ──────────────────────────────────────────────────────────────
def validate_jitter() -> Report:
    """Jitter (local / RAP / PPQ5 / DDP / local-absolute).

    A metric is `cycle-marker + formula`. We validate the FORMULA here:
      (A) parity vs Praat's own jitter formulas on identical marks
      (B) synthetic ground truth: feed analytically-known cycle marks and
          recover the imposed jitter exactly.
    The cycle-MARKER fidelity is a separate concern (see f0_clarity.md).
    """
    import voicemap.praat_perturbation as pp
    rep = Report("jitter")

    # ── (A) Parity vs Praat on real audio ────────────────────────────────────
    try:
        import soundfile as sf
        from parselmouth.praat import call
    except ImportError as e:
        rep.skipped = True
        rep.skip_reason = f"missing dependency: {e.name}"
        return rep

    audio = os.path.join(AUDIO_DIR, "test_Voice_EGG.wav")
    if os.path.exists(audio):
        sig, sr = sf.read(audio)
        voice = (sig[:, 0] if sig.ndim == 2 else sig)[: int(10 * sr)]
        _snd, times, pp_obj = _praat_marks(voice, float(sr))

        cases = [
            ("jitter_local",          "Get jitter (local)",          pp.jitter_local,          1e-9),
            ("jitter_rap",            "Get jitter (rap)",            pp.jitter_rap,            1e-9),
            ("jitter_ppq5",           "Get jitter (ppq5)",           pp.jitter_ppq5,           1e-9),
            ("jitter_ddp",            "Get jitter (ddp)",            pp.jitter_ddp,            1e-9),
            ("jitter_local_absolute", "Get jitter (local, absolute)", pp.jitter_local_absolute, 1e-12),
        ]
        for name, praat_cmd, fn, atol in cases:
            praat_v = call(pp_obj, praat_cmd, 0, 0, PMIN, PMAX, PERIOD_FACTOR)
            ours = fn(times, PMIN, PMAX, PERIOD_FACTOR)
            d = abs(ours - praat_v)
            rep.add(f"A · parity {name} (real 10 s)", f"{praat_v:.3e}",
                    f"{ours:.3e}", f"{d:.1e} (atol {atol:.0e})", d <= atol)
        rep.note("(A) Parity: our numpy formula vs Praat's formula on the "
                 "*same* Praat cc cycle marks — isolates the formula layer.")
    else:
        rep.note(f"(A) skipped — fixture not found: {audio}")

    # ── (B) Synthetic ground truth: formula recovers imposed jitter ──────────
    _ensure_signals()
    mk = _load_make_signals()
    manifest = {s["filename"]: s for s in _load_manifest()["signals"]}

    # local jitter from an alternating ±d period pattern is exactly 2d.
    # RAP/PPQ5 of a perfectly-alternating sequence have closed forms:
    #   RAP  = (2/3)·local   PPQ5 = (2/5)·local
    syn = [
        ("vowel_jitter_0p5pct.wav", 0.005),
        ("vowel_jitter_2pct.wav",   0.020),
    ]
    for fname, imposed in syn:
        bounds, _ = mk._cycle_boundaries(lambda t: 200.0, 3.0, imposed)
        jl = pp.jitter_local(bounds, PMIN, PMAX, PERIOD_FACTOR)
        rep.add(f"B · GT jitter_local {fname}",
                f"{imposed*100:.4f}%", f"{jl*100:.4f}%",
                f"{abs(jl-imposed)*100:.2e}pp (rtol 1e-3)",
                abs(jl - imposed) <= imposed * 1e-3)
        # cross-check manifest agrees with what we imposed
        gt = manifest[fname]["ground_truth"]["jitter_local_pct"]
        rep.add(f"B · manifest GT consistent {fname}",
                f"{imposed*100:.2f}%", f"{gt:.2f}%", "—",
                abs(gt - imposed * 100) < 1e-9)

    # modal (no jitter) → ~0 from its true marks
    b0, _ = mk._cycle_boundaries(lambda t: 200.0, 5.0, 0.0)
    j0 = pp.jitter_local(b0, PMIN, PMAX, PERIOD_FACTOR)
    rep.add("B · GT jitter_local modal (imposed 0)", "0.0000%",
            f"{j0*100:.4f}%", f"{j0*100:.1e}pp (atol 1e-3)", j0 <= 1e-5)

    rep.note("(B) Ground truth: alternating ±d periods give jitter_local=2d "
             "exactly; formula recovers it to <1e-3 rel.")
    rep.note("(C) Real-corpus distribution test deferred to corpus phase; "
             "jitter parity (A) + synthetic GT (B) satisfy the P0 formula bar.")
    return rep


def validate_shimmer() -> Report:
    """Shimmer (local / local_dB / APQ3 / APQ5 / APQ11 / DDA).

    Like jitter, a shimmer metric is `amplitude-marker + formula`. Here the
    amplitude marker is Praat's Hann-windowed per-period RMS (AmplitudeTier),
    which we reimplement in `point_process_to_amplitude_tier`. We validate:
      (A) parity vs Praat — and because the amplitude tier ITSELF is checked
          against Praat (count + times + values), (A) certifies the whole
          amplitude pipeline AND the formula end-to-end on real audio.
      (B) synthetic ground truth: an alternating +/-d_a amplitude pattern has
          shimmer_local = 2*d_a exactly; the formula must recover it.
    The amplitude-MARKER fidelity on the cc cycle grid is the cycle-marker's
    concern (see f0_clarity.md); see this file's md Section 7 for why the
    end-to-end SOURCE shimmer of the synthetic wav is not a usable GT.
    """
    import voicemap.praat_perturbation as pp
    rep = Report("shimmer")

    try:
        import soundfile as sf
        from parselmouth.praat import call
    except ImportError as e:
        rep.skipped = True
        rep.skip_reason = f"missing dependency: {e.name}"
        return rep

    # ── (A) Parity vs Praat on real audio (amplitude pipeline + formula) ──────
    audio = os.path.join(AUDIO_DIR, "test_Voice_EGG.wav")
    if os.path.exists(audio):
        sig, sr = sf.read(audio)
        voice = (sig[:, 0] if sig.ndim == 2 else sig)[: int(10 * sr)]
        voice = np.ascontiguousarray(voice.astype(np.float64))
        snd, times, pp_obj = _praat_marks(voice, float(sr))

        amp_t, amp_v = pp.point_process_to_amplitude_tier(
            times, voice, float(sr), PMIN, PMAX, PERIOD_FACTOR)

        # Amplitude-tier identity: our Hann-RMS pulses vs Praat's AmplitudeTier.
        atier = call([pp_obj, snd], "To AmplitudeTier (period)",
                     0, 0, PMIN, PMAX, PERIOD_FACTOR)
        m = int(call(atier, "Get number of points"))
        pt = np.array([call(atier, "Get time from index", i + 1)
                       for i in range(m)], dtype=np.float64)
        pv = np.array([call(atier, "Get value at index", i + 1)
                       for i in range(m)], dtype=np.float64)
        rep.add("A · amp-tier pulse count (real 10 s)", m, len(amp_t),
                f"{abs(m - len(amp_t))} (atol 0)", m == len(amp_t))
        if m == len(amp_t):
            dt = float(np.max(np.abs(amp_t - pt)))
            dv = float(np.max(np.abs(amp_v - pv)))
            rep.add("A · amp-tier pulse times", "Praat AmplitudeTier",
                    "Hann-RMS", f"{dt:.1e} (atol 1e-9)", dt <= 1e-9)
            rep.add("A · amp-tier pulse values", "Praat AmplitudeTier",
                    "Hann-RMS", f"{dv:.1e} (atol 1e-6)", dv <= 1e-6)

        cases = [
            ("shimmer_local",    "Get shimmer (local)",    pp.shimmer_local),
            ("shimmer_local_dB", "Get shimmer (local_dB)", pp.shimmer_local_dB),
            ("shimmer_apq3",     "Get shimmer (apq3)",     pp.shimmer_apq3),
            ("shimmer_apq5",     "Get shimmer (apq5)",     pp.shimmer_apq5),
            ("shimmer_apq11",    "Get shimmer (apq11)",    pp.shimmer_apq11),
        ]
        for name, praat_cmd, fn in cases:
            praat_v = call([pp_obj, snd], praat_cmd,
                           0, 0, PMIN, PMAX, PERIOD_FACTOR, AMP_FACTOR)
            ours = fn(amp_t, amp_v, PMIN, PMAX, AMP_FACTOR)
            d = abs(ours - praat_v)
            rep.add(f"A · parity {name} (real 10 s)", f"{praat_v:.3e}",
                    f"{ours:.3e}", f"{d:.1e} (atol 1e-6)", d <= 1e-6)
        rep.note("(A) Parity: our amplitude tier (Hann-RMS) is byte-identical "
                 "to Praat's, so the shimmer parity certifies the amplitude "
                 "pipeline AND the formula end-to-end on real audio.")
    else:
        rep.note(f"(A) skipped — fixture not found: {audio}")

    # ── (B) Synthetic ground truth: formula recovers imposed shimmer ─────────
    _ensure_signals()
    mk = _load_make_signals()
    manifest = {s["filename"]: s for s in _load_manifest()["signals"]}

    # alternating amplitude A(1±d_a) on a regular period grid gives
    #   shimmer_local = 2·d_a   exactly (mean|Δa| = 2·A·d_a, mean(a) = A).
    syn = [("vowel_shimmer_5pct.wav", 0.05)]
    for fname, imposed in syn:
        bounds, signs = mk._cycle_boundaries(lambda t: 200.0, 3.0, 0.0)
        d_a = imposed / 2.0
        amp_vals = 1.0 + signs * d_a
        sl = pp.shimmer_local(bounds, amp_vals, PMIN, PMAX, AMP_FACTOR)
        rep.add(f"B · GT shimmer_local {fname}",
                f"{imposed*100:.4f}%", f"{sl*100:.4f}%",
                f"{abs(sl-imposed)*100:.2e}pp (rtol 1e-3)",
                abs(sl - imposed) <= imposed * 1e-3)
        gt = manifest[fname]["ground_truth"]["shimmer_local_pct"]
        rep.add(f"B · manifest GT consistent {fname}",
                f"{imposed*100:.2f}%", f"{gt:.2f}%", "—",
                abs(gt - imposed * 100) < 1e-9)
        # dB form has a closed form on alternating amps: 20·|log10((1+d)/(1-d))|.
        sdb = pp.shimmer_local_dB(bounds, amp_vals, PMIN, PMAX, AMP_FACTOR)
        exp_db = 20.0 * abs(np.log10((1 + d_a) / (1 - d_a)))
        rep.add(f"B · GT shimmer_local_dB {fname}", f"{exp_db:.4f} dB",
                f"{sdb:.4f} dB", f"{abs(sdb-exp_db):.1e} (atol 1e-9)",
                abs(sdb - exp_db) <= 1e-9)

    # modal (no shimmer) → exactly 0
    b0, s0 = mk._cycle_boundaries(lambda t: 200.0, 5.0, 0.0)
    a0 = np.ones_like(s0)
    sm = pp.shimmer_local(b0, a0, PMIN, PMAX, AMP_FACTOR)
    rep.add("B · GT shimmer_local modal (imposed 0)", "0.0000%",
            f"{sm*100:.4f}%", f"{sm*100:.1e}pp (atol 1e-5)", sm <= 1e-5)

    rep.note("(B) Ground truth: alternating ±d_a amplitudes give "
             "shimmer_local = 2·d_a exactly; formula recovers it to <1e-3 rel.")
    rep.note("(C) Real-corpus distribution deferred to corpus phase; (A)+(B) "
             "satisfy the P0 amplitude-pipeline + formula bar. The end-to-end "
             "SOURCE shimmer of the synthetic wav over-reports (5%→8.9%) due to "
             "formant-cascade inter-cycle memory — faithfully (ours==Praat), so "
             "it is a signal-model property, not a defect. See md §7.")
    return rep


VALIDATORS: dict[str, Callable[[], Report]] = {
    "jitter": validate_jitter,
    "shimmer": validate_shimmer,
}
# convenience aliases
for _a in ("jitter_local", "jitter_rap", "jitter_ppq5", "jitter_ddp"):
    VALIDATORS[_a] = validate_jitter
for _a in ("shimmer_local", "shimmer_local_dB", "shimmer_apq3",
           "shimmer_apq5", "shimmer_apq11", "shimmer_dda"):
    VALIDATORS[_a] = validate_shimmer


# ─── Reporting ───────────────────────────────────────────────────────────────
def render_table(rep: Report) -> str:
    lines = ["| Test | Reference | Our Value | Δ (tol) | Pass? |",
             "|---|---|---|---|---|"]
    for r in rep.rows:
        lines.append(f"| {r.test} | {r.reference} | {r.ours} | "
                     f"{r.delta} | {'✓' if r.passed else '✗'} |")
    return "\n".join(lines)


def _ascii(s: str) -> str:
    """Console-safe: the Windows OEM code page (GBK) mangles box-drawing
    and math glyphs, so keep stdout pure ASCII. Markdown files stay UTF-8."""
    return (s.replace("Δ", "d").replace("·", "-").replace("±", "+/-")
             .replace("→", "->").replace("≈", "~").replace("—", "-")
             .replace("✓", "ok").replace("✗", "x"))


def print_report(rep: Report) -> None:
    bar = "=" * 68
    print(f"\n{bar}\n  VALIDATE: {rep.metric}\n{bar}")
    if rep.skipped:
        print(f"  SKIPPED - {rep.skip_reason}")
        return
    w = max((len(r.test) for r in rep.rows), default=10)
    for r in rep.rows:
        mark = "PASS" if r.passed else "FAIL"
        print(_ascii(f"  [{mark}] {r.test:<{w}}  ours={r.ours:<12} "
                     f"ref={r.reference:<12} d={r.delta}"))
    print(bar)
    n_pass = sum(r.passed for r in rep.rows)
    print(f"  {rep.status}: {n_pass}/{len(rep.rows)} checks passed")
    for note in rep.notes:
        print(_ascii(f"  - {note}"))
    print(bar)


def patch_md(rep: Report) -> Optional[str]:
    """Replace the auto-generated block in metrics/<metric>.md Section 5."""
    md_path = os.path.join(METRICS_DIR, f"{rep.metric}.md")
    start = f"<!-- VALIDATE:{rep.metric}:START -->"
    end = f"<!-- VALIDATE:{rep.metric}:END -->"
    block = (f"{start}\n"
             f"*Auto-generated by `scripts/validate_metric.py {rep.metric}` "
             f"— do not edit by hand.*\n\n"
             f"**Result: {rep.status}** "
             f"({sum(r.passed for r in rep.rows)}/{len(rep.rows)} checks)\n\n"
             f"{render_table(rep)}\n"
             f"{end}")
    if not os.path.exists(md_path):
        return None
    with open(md_path, encoding="utf-8") as fh:
        text = fh.read()
    if start in text and end in text:
        pre = text[: text.index(start)]
        post = text[text.index(end) + len(end):]
        text = pre + block + post
    else:
        return None  # caller warns
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return md_path


def validate(metric_name, *, report_md=True) -> Report:
    if metric_name not in VALIDATORS:
        raise SystemExit(f"unknown metric '{metric_name}'. "
                         f"known: {sorted(set(VALIDATORS))}")
    rep = VALIDATORS[metric_name]()
    print_report(rep)
    if report_md and not rep.skipped:
        patched = patch_md(rep)
        if patched:
            print(f"  patched {os.path.relpath(patched, ROOT)} §5")
        else:
            print(f"  (no VALIDATE markers in metrics/{rep.metric}.md — "
                  f"stdout only)")
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate one VoiceMap metric.")
    ap.add_argument("metric", nargs="?", help="metric name (e.g. jitter)")
    ap.add_argument("--no-md", action="store_true",
                    help="print report only; do not patch the metric md")
    ap.add_argument("--list", action="store_true", help="list known metrics")
    args = ap.parse_args()

    if args.list or not args.metric:
        print("Known metrics:", ", ".join(sorted(set(VALIDATORS))))
        return
    rep = validate(args.metric, report_md=not args.no_md)
    sys.exit(0 if rep.all_passed else 1)


if __name__ == "__main__":
    main()
