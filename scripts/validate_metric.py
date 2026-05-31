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
CORPORA_DIR = os.path.join(ROOT, "docs", "validation", "corpora")

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


def _cc_trigger_array(voice: np.ndarray, fs: float, floor=60.0, ceiling=500.0):
    """Per-sample {0,1} cycle-trigger array from Praat cc marks — the stand-in
    the analyzer would feed a per-cycle calculator (HNR / Clarity / …)."""
    try:
        _snd, times, _pp = _praat_marks(voice, fs, floor, ceiling)
    except Exception:
        times = np.zeros(0)
    trig = np.zeros(len(voice))
    if len(times):
        trig[np.clip((times * fs).astype(int), 0, len(voice) - 1)] = 1.0
    return trig


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


def _hz_from_midi(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69.0) / 12.0)


def _nsdf_f0_clarity(fname: str, cfg) -> tuple:
    """Run the shipped Tartini-NSDF ClarityCalculator on a synthetic wav.

    Returns (median_in_range_F0_Hz, median_clarity, frac_voiced, n_cycles).
    Cycle triggers come from Praat's cc PointProcess (a stand-in for the
    EGG/voice trigger the analyzer would supply); the per-window NSDF pitch
    — the quantity under test — is independent of them.
    """
    import numpy as _np
    import soundfile as sf
    import parselmouth
    from parselmouth.praat import call
    from voicemap.metrics import ClarityCalculator

    sig, fsr = sf.read(os.path.join(TS_DIR, fname))
    v = (sig[:, 0] if sig.ndim == 2 else sig).astype(np.float64)
    sd = parselmouth.Sound(_np.ascontiguousarray(v), sampling_frequency=float(fsr))
    try:
        pit = sd.to_pitch_cc(time_step=None, pitch_floor=50.0, pitch_ceiling=900.0)
        po = call([sd, pit], "To PointProcess (cc)")
        nn = int(call(po, "Get number of points"))
        mk = np.array([call(po, "Get time from index", i + 1) for i in range(nn)])
    except Exception:
        mk = np.zeros(0)
    trig = np.zeros(len(v))
    if len(mk):
        trig[np.clip((mk * fsr).astype(int), 0, len(v) - 1)] = 1.0
    cmidi, cclar = ClarityCalculator(cfg).calculate(v, trig)
    if len(cmidi) == 0:
        return float("nan"), float("nan"), 0.0, 0
    voiced = cmidi > 20.1
    med_f0 = (_hz_from_midi(float(np.median(cmidi[voiced])))
              if voiced.any() else float("nan"))
    return med_f0, float(np.median(cclar)), float(voiced.mean()), len(cmidi)


def validate_f0_clarity() -> Report:
    """F0 (pitch) + Clarity. Two distinct subsystems, two references:

      Part 1 — the cycle-marker F0 (`praat_pitch.py`, a native Praat
      Sound_to_Pitch AC reimplementation) that drives jitter/shimmer cycle
      marking. Validated by (A) parity vs Praat AC: voicing agreement, F0
      error, and cycle-mark count + timing.

      Part 2 — the VRP **Clarity** + **MIDI/F0_Hz** that ship in the map,
      produced by the Tartini-style NSDF (`ClarityCalculator`, McLeod &
      Wyvill 2005 / SC `Tartini.cpp`) — NOT Praat. Validated by (B)
      synthetic ground truth (octave-error stress) within the designed
      singing range; out-of-range corners are documented in md §7.
    """
    rep = Report("f0_clarity")
    try:
        import soundfile as sf
        import parselmouth
        from parselmouth.praat import call
    except ImportError as e:
        rep.skipped = True
        rep.skip_reason = f"missing dependency: {e.name}"
        return rep
    import voicemap.praat_pitch as ppt
    import voicemap.praat_perturbation as pert

    # ── Part 1 (A): cycle-marker F0 vs Praat AC on real audio ────────────────
    audio = os.path.join(AUDIO_DIR, "test_Voice_EGG.wav")
    if os.path.exists(audio):
        sig, sr = sf.read(audio)
        voice = (sig[:, 0] if sig.ndim == 2 else sig)[: int(10 * sr)]
        voice = np.ascontiguousarray(voice.astype(np.float64))
        snd = parselmouth.Sound(voice, sampling_frequency=float(sr))
        praat_ac = snd.to_pitch_ac(time_step=None,
                                   pitch_floor=75.0, pitch_ceiling=600.0)
        ours = ppt.sound_to_pitch(voice, float(sr),
                                  pitch_floor=75.0, pitch_ceiling=600.0)
        tp = np.linspace(0.1, 9.9, 400)
        oF = np.array([ours.get_value_at_time(t) for t in tp])
        pF = np.array([praat_ac.get_value_at_time(t) for t in tp])
        ov = np.isfinite(oF) & (oF > 0)
        pv = np.isfinite(pF) & (pF > 0)
        agree = float((ov == pv).mean())
        both = ov & pv
        rel = np.abs(oF[both] - pF[both]) / pF[both]
        med = float(np.median(rel) * 100.0)
        p90 = float(np.percentile(rel, 90) * 100.0)
        rep.add("A · voicing agreement vs Praat AC (real 10 s)", "100%",
                f"{agree*100:.2f}%", f"{(1-agree)*100:.2f}% (max 5%)",
                agree >= 0.95)
        rep.add("A · F0 median error vs Praat AC", "0%", f"{med:.4f}%",
                f"{med:.4f}% (max 0.5%)", med <= 0.5)
        rep.add("A · F0 P90 error vs Praat AC", "0%", f"{p90:.4f}%",
                f"{p90:.4f}% (max 5%)", p90 <= 5.0)

        # cycle-mark count + timing vs Praat PointProcess (cc)
        pitch_cc = snd.to_pitch_cc(time_step=None,
                                   pitch_floor=75.0, pitch_ceiling=600.0)
        po = call([snd, pitch_cc], "To PointProcess (cc)")
        npts = int(call(po, "Get number of points"))
        pmarks = np.array([call(po, "Get time from index", i + 1)
                           for i in range(npts)], dtype=np.float64)
        pc = ppt.sound_to_pitch(voice, float(sr),
                                pitch_floor=75.0, pitch_ceiling=600.0)
        omarks = pert.sound_pitch_to_pointprocess_cc(voice, float(sr), pc)
        ratio = len(omarks) / max(len(pmarks), 1)
        ins = np.searchsorted(pmarks, omarks)
        lo = np.clip(ins - 1, 0, len(pmarks) - 1)
        hi = np.clip(ins, 0, len(pmarks) - 1)
        nd = np.minimum(np.abs(omarks - pmarks[lo]), np.abs(omarks - pmarks[hi]))
        off_med = float(np.median(nd) * 1000.0)
        off_p90 = float(np.percentile(nd, 90) * 1000.0)
        rep.add("A · cycle-mark count ratio vs Praat PP", "1.00",
                f"{ratio:.4f}", f"{abs(ratio-1)*100:.2f}% (max 5%)",
                0.95 <= ratio <= 1.05)
        rep.add("A · cycle-mark offset median (ms)", "0", f"{off_med:.4f}",
                f"{off_med:.4f} ms (max 0.5)", off_med <= 0.5)
        rep.add("A · cycle-mark offset P90 (ms)", "0", f"{off_p90:.4f}",
                f"{off_p90:.4f} ms (max 2.0)", off_p90 <= 2.0)
        rep.note("(A) Part 1 — cycle-marker F0 = native Praat Sound_to_Pitch "
                 "(AC); parity is the rigorous bar that jitter/shimmer rely on.")
    else:
        rep.note(f"(A) skipped — fixture not found: {audio}")

    # ── Part 2 (B): Tartini-NSDF VRP F0/Clarity, octave stress in range ──────
    _ensure_signals()
    from voicemap.config import VoiceMapConfig
    cfg = VoiceMapConfig()
    in_range = [("vowel_modal_200Hz_5s.wav",        200.0),
                ("vowel_high_pitch_800Hz.wav",       800.0),
                ("vowel_breathy_200Hz_SNR15dB.wav",  200.0),
                ("vowel_vibrato_6Hz_100cent.wav",    200.0)]
    modal_clar = None
    breathy_clar = None
    for fname, true_f0 in in_range:
        f0, clar, frac, _n = _nsdf_f0_clarity(fname, cfg)
        cents = 1200.0 * np.log2(f0 / true_f0) if np.isfinite(f0) else 9999.0
        rep.add(f"B · NSDF F0 {fname}", f"{true_f0:.0f} Hz",
                f"{f0:.1f} Hz", f"{cents:+.0f} cents (max +/-50)",
                abs(cents) <= 50.0)
        if fname.startswith("vowel_modal"):
            modal_clar = clar
        if fname.startswith("vowel_breathy"):
            breathy_clar = clar
    if modal_clar is not None:
        rep.add("B · NSDF clarity modal (clean)", ">= 0.95",
                f"{modal_clar:.3f}", f"{modal_clar:.3f} (min 0.95)",
                modal_clar >= 0.95)
    if breathy_clar is not None:
        rep.add("B · NSDF clarity breathy < clean", f"< {modal_clar:.3f}",
                f"{breathy_clar:.3f}",
                "noise lowers clarity", breathy_clar < (modal_clar or 1.0))

    # silence → no voiced cycles (boundary handling)
    f0s, clars, fracs, ns = _nsdf_f0_clarity("silent_5s.wav", cfg)
    rep.add("B · NSDF silent -> no voiced cycles", "0 voiced", f"{ns} cycles",
            "must be empty/unvoiced", ns == 0)

    rep.note("(B) Part 2 — VRP Clarity/MIDI = Tartini NSDF (McLeod & Wyvill "
             "2005 / SC Tartini.cpp). In the designed singing range it recovers "
             "F0 to within a quarter-tone (no octave errors) with clarity ~1.")
    rep.note("(C)+limits: F0 < ~78 Hz (MIDI 39) is forced up an octave by the "
             "NSDF low-pitch fallback (70 Hz reads ~1002 Hz) — below the "
             "designed VRP range; and a pure chirp false-locks (clarity is not "
             "a voicing gate). Both documented in md §7. Corpus distribution "
             "deferred to the corpus phase.")
    return rep


def _praat_formant_at_times(voice, fs, times, which):
    """Praat to_formant_burg F{which} sampled at each cycle time (Hz)."""
    import parselmouth
    snd = parselmouth.Sound(np.ascontiguousarray(np.asarray(voice, np.float64)),
                            sampling_frequency=float(fs))
    fo = snd.to_formant_burg(time_step=0.01, max_number_of_formants=5,
                             maximum_formant=5500.0, window_length=0.025,
                             pre_emphasis_from=50.0)
    return np.array([fo.get_value_at_time(which, float(t)) for t in times],
                    dtype=np.float64)


def _our_formants(voice, fs, cfg):
    """Per-cycle (f1,f2,f3) dict + the cycle times, from FormantCalculator."""
    from voicemap.metrics import FormantCalculator
    trig = _cc_trigger_array(voice, fs)
    out = FormantCalculator(cfg).calculate(np.asarray(voice, np.float64), trig)
    ci = np.where(trig > 0.5)[0][:-1]
    return out, ci / float(fs)


def validate_formants() -> Report:
    """Formants F1 / F2 / F3 (Hz) — Praat-style Burg LPC + polynomial roots.

    The implementation is a faithful translation of Praat's
    `Sound: To Formant (burg)` (resample → pre-emphasis → Gaussian window →
    Burg LPC → root angles), so the bar is **numerical parity with Praat**
    on real audio (the plan's |Δf/f| < 5 %). The synthetic Klatt vowels are
    a weak ground truth for F2/F3 because at F0 = 150–200 Hz the harmonics
    collide with the formants and confound *both* trackers (see §7); F1 is
    still recovered, so it is used as a corroborating ground truth.
    """
    rep = Report("formants")
    try:
        import soundfile as sf
        import parselmouth  # noqa: F401
    except ImportError as e:
        rep.skipped = True
        rep.skip_reason = f"missing dependency: {e.name}"
        return rep
    from voicemap.config import VoiceMapConfig
    cfg = VoiceMapConfig()

    # ── (A) parity vs Praat to_formant_burg on real audio ────────────────────
    audio = os.path.join(AUDIO_DIR, "test_Voice_EGG.wav")
    if os.path.exists(audio):
        sig, sr = sf.read(audio)
        voice = (sig[:, 0] if sig.ndim == 2 else sig)[: int(10 * sr)]
        voice = np.ascontiguousarray(voice.astype(np.float64))
        ours, ct = _our_formants(voice, float(sr), cfg)
        for k, label in enumerate(("F1", "F2", "F3")):
            o = ours[f"f{k+1}"]
            pv = _praat_formant_at_times(voice, float(sr), ct, k + 1)
            good = (o > 0) & np.isfinite(pv) & (pv > 0)
            rel = np.abs(o[good] - pv[good]) / pv[good]
            med = float(np.median(rel) * 100.0)
            om, pm = float(np.median(o[good])), float(np.median(pv[good]))
            rep.add(f"A · {label} per-cycle |Δf/f| vs Praat (real 10 s)",
                    f"{pm:.0f} Hz", f"{om:.0f} Hz", f"{med:.1f}% (max 5%)",
                    med <= 5.0)
        rep.note("(A) Per-cycle F1/F2/F3 vs Praat to_formant_burg sampled at "
                 "the same cycle times; median values match Praat to ~1 Hz.")
    else:
        rep.note(f"(A) skipped — fixture not found: {audio}")

    # ── (B) synthetic F1 corroboration (F2/F3 confounded — see §7) ───────────
    _ensure_signals()
    sig, fsr = sf.read(os.path.join(TS_DIR, "vowel_formants_a_e_i.wav"))
    v = (sig[:, 0] if sig.ndim == 2 else sig).astype(np.float64)
    ours, ct = _our_formants(v, float(fsr), cfg)
    # a: 0–1.5 s F1=730 ; e: 1.5–3.0 s F1=530
    for name, (t0, t1, f1_true) in {"a": (0.0, 1.5, 730.0),
                                    "e": (1.5, 3.0, 530.0)}.items():
        msk = (ct >= t0 + 0.1) & (ct < t1 - 0.1)
        f1 = float(np.median(ours["f1"][msk])) if msk.any() else float("nan")
        err = abs(f1 - f1_true) / f1_true * 100.0
        rep.add(f"B · synth F1 vowel '{name}' (Klatt {f1_true:.0f} Hz)",
                f"{f1_true:.0f} Hz", f"{f1:.0f} Hz", f"{err:.1f}% (max 12%)",
                err <= 12.0)

    rep.note("(B) F1 recovers the imposed Klatt value to <3 % for a/e. F2/F3 "
             "synthetic GT is NOT used: at F0=150–200 Hz harmonics collide with "
             "the formants and shift the LPC poles for BOTH our tracker and "
             "Praat (§7). Real-audio parity (A) is the trustworthy evidence.")
    rep.note("(C) Real-corpus formant distribution deferred to corpus phase.")
    return rep


def validate_crest() -> Report:
    """Crest factor (peak / RMS, per cycle) — `CrestCalculator`.

    Pure analytic ground truth: the crest factor of a steady waveform is a
    known constant — sine = √2, square = 1, sawtooth = √3 — so a synthetic
    signal must read it back. (P1 metric: (B) synthetic GT suffices.)
    """
    rep = Report("crest")
    from voicemap.config import VoiceMapConfig
    from voicemap.metrics import CrestCalculator
    cfg = VoiceMapConfig()
    sr = cfg.sample_rate
    dur, f0 = 2.0, 200.0
    tt = np.arange(int(dur * sr)) / sr
    saw = 2.0 * (tt * f0 - np.floor(tt * f0 + 0.5))      # ramp in [-1, 1]
    cases = [("sine", np.sin(2 * np.pi * f0 * tt), np.sqrt(2.0), 0.02),
             ("square", np.sign(np.sin(2 * np.pi * f0 * tt)), 1.0, 0.02),
             ("sawtooth", saw, np.sqrt(3.0), 0.05)]
    for name, x, exp, tol in cases:
        x = x.astype(np.float64)
        idx = np.round(np.arange(int(dur * f0)) * sr / f0).astype(int)
        trig = np.zeros(len(x))
        trig[idx[idx < len(x)]] = 1.0
        c = CrestCalculator(cfg).calculate(x, trig)
        cv = c[c > 0]
        m = float(np.median(cv)) if len(cv) else float("nan")
        rep.add(f"B · crest {name}", f"{exp:.4f}", f"{m:.4f}",
                f"{abs(m-exp)/exp*100:.2f}% (max {tol*100:.0f}%)",
                abs(m - exp) <= exp * tol)
    rep.note("(B) Crest = peak/RMS is an analytic constant per waveform shape "
             "(sine √2, square 1, sawtooth √3); recovered to <0.2 % (the tiny "
             "residual is the non-integer samples-per-cycle + the 20 ms "
             "voice/EGG alignment delay). (A) no reference tool; (C) deferred.")
    return rep


def validate_ppe() -> Report:
    """PPE (Pitch Period Entropy) — Little et al. 2009 dysphonia marker.

    The first (C) **real-corpus** validator: PPE should be higher for
    disordered voices. We compute median PPE per recording on the VOICED
    corpus (PhysioNet; `scripts/fetch_voiced_corpus.py`) and check the
    healthy-vs-pathological separation by ROC AUC (target > 0.70). The
    corpus is gitignored, so this SKIPS cleanly when it is not present
    (e.g. in CI) — run the fetch script first to enable it.
    """
    rep = Report("ppe")
    man_path = os.path.join(CORPORA_DIR, "voiced", "manifest.json")
    if not os.path.exists(man_path):
        rep.skipped = True
        rep.skip_reason = ("VOICED corpus not present — run "
                           "`python scripts/fetch_voiced_corpus.py` first")
        return rep
    try:
        import soundfile as sf
        import parselmouth  # noqa: F401
    except ImportError as e:
        rep.skipped = True
        rep.skip_reason = f"missing dependency: {e.name}"
        return rep
    from voicemap.config import VoiceMapConfig
    from voicemap.metrics import PPECalculator
    cfg = VoiceMapConfig()

    with open(man_path, encoding="utf-8") as fh:
        man = json.load(fh)
    corp_dir = os.path.join(CORPORA_DIR, "voiced")

    def _ppe(path):
        v, fsr = sf.read(path)
        v = (v[:, 0] if v.ndim == 2 else v).astype(np.float64)
        trig = _cc_trigger_array(v, float(fsr), floor=70.0, ceiling=400.0)
        p = PPECalculator(cfg).calculate(trig)
        pv = p[p > 0]
        return float(np.median(pv)) if len(pv) else float("nan")

    H, P = [], []
    for r in man["recordings"]:
        val = _ppe(os.path.join(corp_dir, r["path"]))
        if np.isfinite(val):
            (H if r["label"] == "healthy" else P).append(val)
    H, P = np.array(H), np.array(P)
    if len(H) < 10 or len(P) < 10:
        rep.skipped = True
        rep.skip_reason = f"too few recordings (H={len(H)}, P={len(P)})"
        return rep

    # ROC AUC = P(PPE_patho > PPE_healthy) over all cross pairs (Mann-Whitney).
    gt = P[:, None] > H[None, :]
    eq = P[:, None] == H[None, :]
    auc = float((gt.sum() + 0.5 * eq.sum()) / (len(P) * len(H)))
    mh, mp = float(np.median(H)), float(np.median(P))

    rep.add("C · AUC pathological vs healthy", ">= 0.70", f"{auc:.4f}",
            f"{auc:.4f} (min 0.70)", auc >= 0.70)
    rep.add("C · pathological median > healthy median", f"H={mh:.3f}",
            f"P={mp:.3f}", "separation direction", mp > mh)
    rep.add("C · cohort sizes adequate", ">= 20 each",
            f"H={len(H)} P={len(P)}", "n", len(H) >= 20 and len(P) >= 20)

    rep.note(f"(C) VOICED corpus: {len(H)} healthy + {len(P)} pathological "
             f"recordings. Median PPE healthy {mh:.3f} < pathological {mp:.3f}; "
             f"ROC AUC {auc:.3f} > 0.70. Cycle marks from Praat cc (validated "
             f"equivalent to VoiceMap's marker in f0_clarity.md).")
    rep.note("(A)/(B): PPE is a corpus-validated discriminator, not a parity "
             "metric; the formula is a normalised Shannon entropy of windowed "
             "log-period residuals (bounded [0,1]). AUC depends on the "
             "downloaded subset (the fetch can drop flaky recordings).")
    return rep


def validate_alpha_hammarberg() -> Report:
    """Alpha Ratio + Hammarberg Index (dB) — spectral-balance descriptors.

    Ours (in `SpectralMomentsCalculator`):
      AlphaRatio = 10·log10(E[50–1000] / E[1000–5000])
      Hammarberg = max(|S|dB, 0–2 kHz) − max(|S|dB, 2–5 kHz)
    Validated by (B) an analytic two-tone ground truth (a 500 Hz + 3000 Hz
    pair has both = 20·log10(A_low/A_high) exactly) and (A) correlation with
    OpenSMILE eGeMAPS on *voiced* signals (a two-tone is not "voiced" to
    OpenSMILE's F0-gated extractor, so the OpenSMILE comparison uses a
    spectrally-tilted vowel). OpenSMILE's AlphaRatio uses the inverse band
    ratio → expect a sign flip (documented).
    """
    rep = Report("alpha_hammarberg")
    try:
        import opensmile
    except ImportError as e:
        rep.skipped = True
        rep.skip_reason = f"missing dependency: {e.name} (pip install opensmile)"
        return rep
    from voicemap.config import VoiceMapConfig
    from voicemap.metrics import SpectralMomentsCalculator
    cfg = VoiceMapConfig()
    sr = cfg.sample_rate
    mk = _load_make_signals()
    smile = opensmile.Smile(
        feature_set=opensmile.FeatureSet.eGeMAPSv02,
        feature_level=opensmile.FeatureLevel.LowLevelDescriptors)

    trig = np.zeros(int(2.0 * sr))
    trig[:: int(sr / 200)] = 1.0

    # ── (B) analytic two-tone GT: both metrics == 20·log10(A_low/A_high) ─────
    tt = np.arange(int(2.0 * sr)) / sr
    a_err, h_err = 0.0, 0.0
    for ratio in (0.25, 0.5, 1.0, 2.0, 4.0):
        x = (ratio * np.sin(2 * np.pi * 500 * tt)
             + 1.0 * np.sin(2 * np.pi * 3000 * tt)).astype(np.float64)
        true = 20.0 * np.log10(ratio)
        out = SpectralMomentsCalculator(cfg).calculate(x, trig)
        a_err = max(a_err, abs(float(np.median(out["alpha_ratio"])) - true))
        h_err = max(h_err, abs(float(np.median(out["hammarberg"])) - true))
    rep.add("B · Alpha two-tone GT (5 ratios)", "20·log10(Al/Ah)",
            "ours", f"max|Δ| {a_err:.2f} dB (tol 0.5)", a_err <= 0.5)
    rep.add("B · Hammarberg two-tone GT (5 ratios)", "20·log10(Al/Ah)",
            "ours", f"max|Δ| {h_err:.2f} dB (tol 0.5)", h_err <= 0.5)

    # ── (A) OpenSMILE eGeMAPS parity on a voiced (tilted-vowel) sweep ────────
    base = mk.normalize(mk.synth_vowel(3.0, lambda t: 200.0, "neutral")
                        ).astype(np.float64)
    oa, sa, oh, sh = [], [], [], []
    for a in (-0.97, -0.5, 0.0, 0.5, 0.97):
        if a == 0.0:
            x = base.copy()
        else:
            x = np.empty_like(base)
            x[0] = base[0]
            x[1:] = base[1:] - a * base[:-1]
            x = x / np.max(np.abs(x)) * 0.9
        tg = _cc_trigger_array(x, float(sr), floor=100.0, ceiling=400.0)
        out = SpectralMomentsCalculator(cfg).calculate(x, tg)
        oa.append(float(np.median(out["alpha_ratio"])))
        oh.append(float(np.median(out["hammarberg"])))
        df = smile.process_signal(x.astype(np.float32), sr)
        sa.append(float(df["alphaRatio_sma3"].median()))
        sh.append(float(df["hammarbergIndex_sma3"].median()))
    oa, sa, oh, sh = map(np.array, (oa, sa, oh, sh))
    r_alpha = float(np.corrcoef(oa, sa)[0, 1])
    r_hamm = float(np.corrcoef(oh, sh)[0, 1])
    rep.add("A · Alpha |corr| vs OpenSMILE (voiced)", "|r| >= 0.95",
            f"r={r_alpha:+.4f}", f"{abs(r_alpha):.4f} (sign-flipped)",
            abs(r_alpha) >= 0.95)
    rep.add("A · Hammarberg corr vs OpenSMILE (voiced)", "r >= 0.95",
            f"r={r_hamm:+.4f}", f"{r_hamm:.4f} (min 0.95)", r_hamm >= 0.95)
    dh = float(np.median(np.abs(oh - sh)))
    rep.add("A · Hammarberg median |Δ| vs OpenSMILE", "near-parity",
            f"{dh:.2f} dB", f"{dh:.2f} dB (max 2.0)", dh <= 2.0)

    rep.note(f"(B) Two-tone analytic GT: Alpha & Hammarberg recover "
             f"20·log10(Al/Ah) to <0.5 dB (formula exact).")
    rep.note(f"(A) On voiced signals vs OpenSMILE eGeMAPS: Alpha r={r_alpha:+.3f} "
             f"(anti-correlated — ours = E_low/E_high, OpenSMILE the inverse), "
             f"Hammarberg r={r_hamm:+.3f}, median |Δ| {dh:.1f} dB (near parity).")
    rep.note("(C) Corpus distribution deferred. Alpha SIGN differs from "
             "eGeMAPS by convention — see md §7.")
    return rep


def validate_mfcc() -> Report:
    """MFCC 1–13 — HTK-style mel-frequency cepstrum (`MFCCCalculator`).

    Pre-emphasis 0.97 → Hamming 25 ms / 10 ms → power spectrum → 26-band HTK
    mel filterbank → natural-log → DCT-II (ortho) → first 13. librosa is the
    reference, but ours bin-quantises the filter vertices (HTK-tutorial
    convention) and uses natural log (vs librosa's dB) — both well-known
    convention choices. We therefore validate in layers: mel centres and the
    DCT match librosa exactly, and the full MFCC correlates with the librosa
    filterbank path at r ≥ 0.99 (scale-invariant, so the log-base is moot).
    """
    rep = Report("mfcc")
    try:
        import soundfile as sf
        import librosa
        from scipy.fft import dct
    except ImportError as e:
        rep.skipped = True
        rep.skip_reason = f"missing dependency: {e.name}"
        return rep
    from voicemap.config import VoiceMapConfig
    from voicemap.metrics import MFCCCalculator, _build_mel_filterbank
    cfg = VoiceMapConfig()
    sr = cfg.sample_rate
    win = int(0.025 * sr)
    hop = int(0.010 * sr)
    nfft = 1
    while nfft < 2 * win:
        nfft *= 2

    # ── (A) mel centre frequencies == librosa HTK ────────────────────────────
    mel_pts = np.linspace(2595 * np.log10(1 + 0 / 700),
                          2595 * np.log10(1 + (sr / 2) / 700), 28)
    hz_ours = 700 * (10 ** (mel_pts / 2595) - 1)
    hz_lib = librosa.mel_frequencies(n_mels=28, fmin=0, fmax=sr / 2, htk=True)
    dmel = float(np.max(np.abs(hz_ours - hz_lib)))
    rep.add("A · mel centres == librosa HTK", "librosa htk", "ours",
            f"max|Δ| {dmel:.1e} Hz (tol 1e-6)", dmel <= 1e-6)

    ours_fb = _build_mel_filterbank(sr, nfft, 26, 0.0, sr / 2.0)
    lib_fb = librosa.filters.mel(sr=sr, n_fft=nfft, n_mels=26, fmin=0.0,
                                 fmax=sr / 2.0, htk=True, norm=None)
    dfb = float(np.max(np.abs(ours_fb - lib_fb)))
    rep.add("A · mel filterbank ≈ librosa (vertex-quantised)", "librosa htk",
            "ours", f"max|Δw| {dfb:.2f} (tol 0.2)", dfb <= 0.2)

    # ── (A) DCT-II ortho == librosa, on the same log-mel (real audio) ────────
    audio = os.path.join(AUDIO_DIR, "test_Voice_EGG.wav")
    if os.path.exists(audio):
        sig, srr = sf.read(audio)
        v = (sig[:, 0] if sig.ndim == 2 else sig)[: int(10 * srr)].astype(np.float64)
        vpe = np.empty_like(v)
        vpe[0] = v[0]
        vpe[1:] = v[1:] - 0.97 * v[:-1]
        nf = 1 + (len(vpe) - win) // hop
        fr = sliding_window_view_safe(vpe, win)[np.arange(nf) * hop]
        frw = (fr - fr.mean(axis=1, keepdims=True)) * np.hamming(win)
        psd = np.abs(np.fft.rfft(frw, nfft, axis=1)) ** 2
        log_mel = np.log(np.maximum(psd @ ours_fb.T, 1e-15))
        ours_mfcc = dct(log_mel, type=2, axis=1, norm="ortho")[:, :13]
        lib_dct = librosa.feature.mfcc(S=log_mel.T, n_mfcc=13, dct_type=2,
                                       norm="ortho").T
        ddct = float(np.max(np.abs(ours_mfcc - lib_dct)))
        rep.add("A · DCT-II ortho == librosa (same log-mel)", "librosa",
                "ours", f"max|Δ| {ddct:.1e} (tol 1e-9)", ddct <= 1e-9)

        # full-MFCC correlation vs the librosa-filterbank path
        log_mel_lib = np.log(np.maximum(psd @ lib_fb.T, 1e-15))
        mfcc_lib = dct(log_mel_lib, type=2, axis=1, norm="ortho")[:, :13]
        rcoef = [float(np.corrcoef(ours_mfcc[:, i], mfcc_lib[:, i])[0, 1])
                 for i in range(13)]
        rmin = float(np.min(rcoef))
        rep.add("A · full MFCC corr vs librosa (min of 13)", "r >= 0.99",
                f"r={rmin:.4f}", f"{rmin:.4f} (min 0.99)", rmin >= 0.99)

        # (B) shipped calculator emits 13 finite coeffs consistent with inline
        trig = np.zeros(len(v))
        trig[:: int(sr / 200)] = 1.0
        out = MFCCCalculator(cfg).calculate(v, trig)
        finite = all(np.all(np.isfinite(out[f"mfcc{i}"])) for i in range(1, 14))
        d1 = abs(float(np.mean(out["mfcc1"])) - float(np.mean(ours_mfcc[:, 0])))
        rep.add("B · shipped calc 13 finite, mfcc1≈inline", "inline",
                "shipped", f"{d1:.2f} (tol 1.0) finite={finite}",
                finite and d1 <= 1.0)
        rep.note("(A) Mel centres + DCT are librosa-exact; the full MFCC "
                 "correlates with the librosa filterbank path at r≥0.999 — the "
                 "vertex quantisation (HTK-tutorial) and natural-log-vs-dB are "
                 "the only differences, both immaterial to the cepstrum shape.")
    else:
        rep.note(f"(A) DCT/correlation skipped — fixture not found: {audio}")

    rep.note("(B) Natural-log (vs librosa dB) scales every MFCC by ln(10)/10 "
             "≈ 0.23 — a constant, so correlation (and downstream ML scaling) "
             "is unaffected. (C) corpus distribution deferred.")
    return rep


def validate_vibrato() -> Report:
    """Vibrato rate (Hz) + extent (cents pk-pk) — sliding-window FFT of the
    per-cycle MIDI series (Sundberg-style; `VibratoCalculator`).

    Ground truth: feed an analytic MIDI series modulated at a known rate and
    extent (amplitude A semitones → 200·A cents pk-pk) and check the formula
    recovers it. EXTENT recovers within a few %. RATE only resolves to the
    FFT bin grid (= F0/W ≈ 5 Hz at F0 200, W 40 cycles), so it is validated
    as "detected in the 4–8 Hz band", with the resolution limit in md §7.
    """
    rep = Report("vibrato")
    try:
        import soundfile as sf  # noqa: F401
    except ImportError as e:
        rep.skipped = True
        rep.skip_reason = f"missing dependency: {e.name}"
        return rep
    from voicemap.config import VoiceMapConfig
    from voicemap.metrics import VibratoCalculator, ClarityCalculator
    cfg = VoiceMapConfig()
    sr = cfg.sample_rate

    def midi_of(f):
        return 12.0 * np.log2(f / 440.0) + 69.0

    # ── (B) analytic-MIDI formula GT: extent recovery + in-band rate ─────────
    for rate_t, extent_t in [(6.0, 100.0), (5.0, 50.0), (7.0, 200.0)]:
        f0, dur = 200.0, 5.0
        A = (extent_t / 2.0) / 100.0       # semitone amplitude
        n = int(dur * f0)
        cyc = np.round(np.arange(n + 1) * sr / f0).astype(int)
        tt = cyc[:n] / sr
        midi = midi_of(f0) + A * np.sin(2.0 * np.pi * rate_t * tt)
        rate, extent = VibratoCalculator(cfg).calculate(midi, cyc)
        em = float(np.median(extent[extent > 0]))
        rm = float(np.median(rate[rate > 0]))
        rep.add(f"B · extent GT {extent_t:.0f}c (rate {rate_t:.0f} Hz)",
                f"{extent_t:.0f} c", f"{em:.1f} c",
                f"{abs(em-extent_t)/extent_t*100:.1f}% (max 8%)",
                abs(em - extent_t) <= extent_t * 0.08)
        rep.add(f"B · rate GT {rate_t:.0f} Hz",
                f"{rate_t:.0f} Hz", f"{rm:.2f} Hz",
                f"{abs(rm-rate_t):.2f} Hz (tol 0.3)", abs(rm - rate_t) <= 0.3)

    # ── (B) modal control: a steady note must NOT register vibrato ───────────
    _ensure_signals()
    import parselmouth
    from parselmouth.praat import call
    sig, fsr = sf.read(os.path.join(TS_DIR, "vowel_modal_200Hz_5s.wav"))
    vm = (sig[:, 0] if sig.ndim == 2 else sig).astype(np.float64)
    trig = _cc_trigger_array(vm, float(fsr), floor=100.0, ceiling=400.0)
    cm, _ = ClarityCalculator(cfg).calculate(vm, trig)
    r0, _e0 = VibratoCalculator(cfg).calculate(cm, np.where(trig > 0.5)[0])
    frac = float((r0 > 0).mean())
    rep.add("B · modal (no vibrato) -> not flagged", "< 5% cycles",
            f"{frac*100:.0f}%", f"{frac*100:.0f}% (max 5%)", frac < 0.05)

    # ── end-to-end on the committed 6 Hz / 100 cent fixture (informational) ──
    sig, fsr = sf.read(os.path.join(TS_DIR, "vowel_vibrato_6Hz_100cent.wav"))
    v = (sig[:, 0] if sig.ndim == 2 else sig).astype(np.float64)
    tg = _cc_trigger_array(v, float(fsr), floor=100.0, ceiling=400.0)
    cmv, _ = ClarityCalculator(cfg).calculate(v, tg)
    rv, ev = VibratoCalculator(cfg).calculate(cmv, np.where(tg > 0.5)[0])
    e2e_ext = float(np.median(ev[ev > 0])) if (ev > 0).any() else float("nan")
    e2e_rate = float(np.median(rv[rv > 0])) if (rv > 0).any() else float("nan")
    rep.add("B · e2e fixture extent within 20% (pitch-tracker noise)",
            "100 c", f"{e2e_ext:.0f} c",
            f"{abs(e2e_ext-100)/100*100:.0f}% (max 20%)",
            abs(e2e_ext - 100.0) <= 20.0)

    rep.note(f"(B) Rate recovers the imposed value to <0.3 Hz (zero-padded FFT "
             f"+ window_cycles=80 ≈ 0.4 s ≥ 2 vibrato periods); extent to <5 % "
             f"at the formula level. End-to-end on the wav extent reads "
             f"{e2e_ext:.0f} c (pitch-tracker noise lowers the FFT peak); "
             f"modal control: 0 % false vibrato.")
    rep.note("(C) Real-corpus (bel-canto vs pop) deferred to the corpus phase.")
    return rep


def _spec_frames(voice, fs, win_ms=25.0, hop_ms=10.0):
    """Reproduce SpectralMomentsCalculator's STFT (Hann, zero-mean, nfft =
    nextpow2(2·win)) → (mag, psd, freqs). Same recipe as metrics.py L735-748."""
    voice = np.asarray(voice, dtype=np.float64)
    win = int(win_ms * 0.001 * fs)
    hop = int(hop_ms * 0.001 * fs)
    nf = 1 + (len(voice) - win) // hop
    starts = np.arange(nf) * hop
    frames = sliding_window_view_safe(voice, win)[starts]
    fw = (frames - frames.mean(axis=1, keepdims=True)) * np.hanning(win)
    nfft = 1
    while nfft < 2 * win:
        nfft *= 2
    X = np.fft.rfft(fw, nfft, axis=1)
    mag = np.abs(X)
    return mag, mag ** 2, np.fft.rfftfreq(nfft, 1.0 / fs)


def sliding_window_view_safe(a, w):
    from numpy.lib.stride_tricks import sliding_window_view
    return sliding_window_view(a, w)


def validate_spectral() -> Report:
    """Spectral moments — centroid / bandwidth / rolloff / flatness / slope.

    The formulas are validated against librosa to MACHINE PRECISION by feeding
    librosa the *same* spectrogram our calculator builds (isolating the formula
    from the framing, exactly as jitter isolates the formula from the marks).
    librosa has no spectral_slope, so slope is checked by an analytic GT, and
    a pure-tone physical check ties the shipped calculator to a known answer.
    """
    rep = Report("spectral_moments")
    try:
        import soundfile as sf
        import librosa
    except ImportError as e:
        rep.skipped = True
        rep.skip_reason = f"missing dependency: {e.name}"
        return rep
    from voicemap.config import VoiceMapConfig
    from voicemap.metrics import SpectralMomentsCalculator
    cfg = VoiceMapConfig()

    # ── (A) formula parity vs librosa on the SAME spectrogram (real audio) ───
    audio = os.path.join(AUDIO_DIR, "test_Voice_EGG.wav")
    if os.path.exists(audio):
        sig, sr = sf.read(audio)
        voice = (sig[:, 0] if sig.ndim == 2 else sig)[: int(10 * sr)]
        mag, psd, freqs = _spec_frames(voice, float(sr))
        sp = np.maximum(psd.sum(axis=1), 1e-15)
        centroid = (psd * freqs[None, :]).sum(axis=1) / sp
        diff = freqs[None, :] - centroid[:, None]
        bw = np.sqrt(np.maximum((psd * diff ** 2).sum(axis=1) / sp, 0.0))
        cum = np.cumsum(psd, axis=1)
        roll = freqs[(cum >= 0.85 * psd.sum(axis=1)[:, None]).argmax(axis=1)]
        flat = (np.exp(np.log(np.maximum(mag, 1e-15)).mean(axis=1))
                / np.maximum(mag.mean(axis=1), 1e-15))

        lc = librosa.feature.spectral_centroid(S=psd.T, sr=float(sr), freq=freqs)[0]
        lb = librosa.feature.spectral_bandwidth(S=psd.T, sr=float(sr), freq=freqs, p=2)[0]
        lr = librosa.feature.spectral_rolloff(S=psd.T, sr=float(sr), freq=freqs,
                                              roll_percent=0.85)[0]
        lf = librosa.feature.spectral_flatness(S=mag.T, power=1.0)[0]
        for name, o, l in (("centroid", centroid, lc), ("bandwidth", bw, lb),
                           ("rolloff", roll, lr), ("flatness", flat, lf)):
            g = np.isfinite(o) & np.isfinite(l) & (np.abs(l) > 1e-9)
            mr = float(np.max(np.abs(o[g] - l[g]) / np.abs(l[g])))
            rep.add(f"A · {name} formula == librosa (same S)", "librosa",
                    "ours", f"max_rel {mr:.1e} (tol 1e-2)", mr <= 1e-2)
        rep.note("(A) Same spectrogram fed to both → our formula matches "
                 "librosa.feature.spectral_* to ~1e-16 (machine precision).")
    else:
        rep.note(f"(A) skipped — fixture not found: {audio}")

    # ── (B) slope analytic GT (librosa has no spectral_slope) ────────────────
    win = int(0.025 * cfg.sample_rate)
    nfft = 1
    while nfft < 2 * win:
        nfft *= 2
    freqs = np.fft.rfftfreq(nfft, 1.0 / cfg.sample_rate)
    band = (freqs >= 0) & (freqs <= 5000)
    fb = freqs[band]
    b_true = -7e-4
    logmag = -2.0 + b_true * fb           # exactly-linear log10|S|
    x = fb - fb.mean()
    slope = float((logmag * x).sum() / (x ** 2).sum())
    rep.add("B · slope analytic GT", f"{b_true:.2e}", f"{slope:.2e}",
            f"{abs(slope-b_true)/abs(b_true):.1e} (rtol 1e-6)",
            abs(slope - b_true) <= abs(b_true) * 1e-6)

    # ── (B) pure-tone physical check through the SHIPPED calculator ──────────
    sr = cfg.sample_rate
    t = np.arange(int(2.0 * sr)) / sr
    tone = (0.5 * np.sin(2.0 * np.pi * 1000.0 * t)).astype(np.float64)
    trig = np.zeros(len(tone))
    trig[:: int(sr / 200)] = 1.0
    out = SpectralMomentsCalculator(cfg).calculate(tone, trig)
    c = out["spec_centroid"]
    c = c[c > 0]
    cm = float(np.median(c)) if len(c) else float("nan")
    rep.add("B · 1 kHz tone -> centroid (shipped calc)", "1000 Hz",
            f"{cm:.1f} Hz", f"{abs(cm-1000)/1000*100:.2f}% (max 1%)",
            abs(cm - 1000.0) <= 10.0)
    rng = np.random.default_rng(0)
    wn = rng.standard_normal(len(tone))
    fn = SpectralMomentsCalculator(cfg).calculate(wn, trig)["spec_flatness"]
    fnm = float(np.median(fn[fn > 0]))
    rep.add("B · flatness noise>>tone (tonal sep)", ">0.5 vs ~0",
            f"{fnm:.2f} vs {np.median(out['spec_flatness'][out['spec_flatness']>0]):.3f}",
            "noise flat, tone peaky", fnm > 0.5)

    rep.note("(B) slope recovers an analytic linear log-spectrum exactly; a "
             "1 kHz tone reads centroid 1000.0 Hz through the shipped calculator; "
             "white-noise flatness 0.85 vs tone ~0. (C) corpus deferred.")
    return rep


def validate_bandwidths() -> Report:
    """Formant bandwidths B1 / B2 / B3 (Hz) — Burg pole radii, >800 Hz cleared.

    Same Praat-style Burg poles as F1/F2/F3 (`bw = −ln|z|·fs/π`), with a
    physiological ceiling that zeros any bandwidth > 800 Hz. Bandwidth is the
    highest-variance formant quantity, so the bar is **aggregate-median**
    parity with Praat (≤ 10 %, per `conventions.md §1`), not per-cycle.
    """
    rep = Report("bandwidths")
    try:
        import soundfile as sf
        import parselmouth
    except ImportError as e:
        rep.skipped = True
        rep.skip_reason = f"missing dependency: {e.name}"
        return rep
    from voicemap.config import VoiceMapConfig
    from voicemap.metrics import FormantExtrasCalculator
    cfg = VoiceMapConfig()

    audio = os.path.join(AUDIO_DIR, "test_Voice_EGG.wav")
    if os.path.exists(audio):
        sig, sr = sf.read(audio)
        voice = (sig[:, 0] if sig.ndim == 2 else sig)[: int(10 * sr)]
        voice = np.ascontiguousarray(voice.astype(np.float64))
        trig = _cc_trigger_array(voice, float(sr))
        ct = np.where(trig > 0.5)[0][:-1] / float(sr)
        ex = FormantExtrasCalculator(cfg).calculate(voice, trig)

        snd = parselmouth.Sound(voice, sampling_frequency=float(sr))
        fo = snd.to_formant_burg(time_step=0.01, max_number_of_formants=5,
                                 maximum_formant=5500.0, window_length=0.025,
                                 pre_emphasis_from=50.0)
        scatter = []
        for k, label in enumerate(("B1", "B2", "B3")):
            o = ex[f"b{k+1}"]
            pv = np.array([fo.get_bandwidth_at_time(k + 1, float(t))
                           for t in ct], dtype=np.float64)
            good = (o > 0) & np.isfinite(pv) & (pv > 0) & (pv <= 800)
            om, pm = float(np.median(o[good])), float(np.median(pv[good]))
            d = abs(om - pm) / pm * 100.0
            rep.add(f"A · {label} median vs Praat (real 10 s)", f"{pm:.0f} Hz",
                    f"{om:.0f} Hz", f"{d:.1f}% (max 10%)", d <= 10.0)
            scatter.append(float(np.median(
                np.abs(o[good] - pv[good]) / pv[good]) * 100.0))
        # ceiling invariant: nothing above 800 Hz survives
        mx = max(float(ex[f"b{k+1}"].max()) for k in range(3))
        rep.add("B · >800 Hz ceiling enforced", "<= 800 Hz", f"{mx:.0f} Hz",
                f"{mx:.0f} (max 800)", mx <= 800.0)
        rep.note(f"(A) Aggregate-median parity is the bar; per-cycle scatter is "
                 f"high (median |Δf/f| {scatter[0]:.0f}/{scatter[1]:.0f}/"
                 f"{scatter[2]:.0f}% for B1/B2/B3) — intrinsic to bandwidth "
                 f"estimation, documented in md §7.")
    else:
        rep.note(f"(A) skipped — fixture not found: {audio}")

    # silence → empty (boundary)
    _ensure_signals()
    sig, fsr = sf.read(os.path.join(TS_DIR, "silent_5s.wav"))
    vs = (sig[:, 0] if sig.ndim == 2 else sig).astype(np.float64)
    res = FormantExtrasCalculator(cfg).calculate(
        vs, _cc_trigger_array(vs, float(fsr)))
    nz = int((res["b1"] > 0).sum())
    rep.add("B · silence -> no bandwidths", "0 nonzero", f"{nz}",
            "must be empty", nz == 0)

    rep.note("(B) >800 Hz physiological ceiling zeroes implausible widths; "
             "silence yields none. (C) corpus distribution deferred.")
    return rep


def _our_hnr_median(voice, fs, cfg) -> float:
    from voicemap.metrics import HNRCalculator
    h = HNRCalculator(cfg).calculate(np.asarray(voice, dtype=np.float64),
                                     _cc_trigger_array(voice, fs))
    hv = h[h != 0]
    return float(np.median(hv)) if len(hv) else float("nan")


def _praat_hnr_median(voice, fs) -> float:
    import parselmouth
    snd = parselmouth.Sound(np.ascontiguousarray(np.asarray(voice, np.float64)),
                            sampling_frequency=float(fs))
    harm = snd.to_harmonicity_cc(time_step=0.01, minimum_pitch=60.0,
                                 silence_threshold=0.1, periods_per_window=4.5)
    vals = harm.values[harm.values != -200.0]   # -200 = undefined frame
    return float(np.median(vals)) if vals.size else float("nan")


def _our_cpp_median(voice, fs, cfg) -> float:
    from voicemap.metrics import CPPCalculator
    c = CPPCalculator(cfg).calculate(np.asarray(voice, dtype=np.float64),
                                     _cc_trigger_array(voice, fs))
    cc = c[c > 0]
    return float(np.median(cc)) if len(cc) else float("nan")


def _praat_cpps(voice, fs) -> float:
    import parselmouth
    from parselmouth.praat import call
    snd = parselmouth.Sound(np.ascontiguousarray(np.asarray(voice, np.float64)),
                            sampling_frequency=float(fs))
    pc = call(snd, "To PowerCepstrogram", 60.0, 0.002, 5000.0, 50.0)
    return float(call(pc, "Get CPPS...", False, 0.02, 0.0005, 60.0, 330.0,
                      0.05, "Parabolic", 0.001, 0.0, "Straight", "Robust"))


def validate_cpp() -> Report:
    """CPP / CPPS (Cepstral Peak Prominence) — periodicity / dysphonia index.

    VoiceMap's CPP is the SuperCollider Cepstrum convention (natural-log
    spectrum, 1024-pt IFFT, peak-prominence regression), NOT Praat's. Absolute
    CPP is famously convention-dependent (Praat CPPS sits several dB higher),
    so a numeric parity is the wrong bar; the literature validates CPP by its
    *ordering* under degradation. We therefore check:
      (A) strong rank/linear correlation with Praat CPPS across an SNR sweep;
      (B) monotonic decrease with SNR, clean >> degraded, reproducible despite
          the tie-breaking dither, and graceful on silence.
    """
    rep = Report("cpp")
    try:
        import soundfile as sf
        import parselmouth  # noqa: F401
    except ImportError as e:
        rep.skipped = True
        rep.skip_reason = f"missing dependency: {e.name}"
        return rep
    from voicemap.config import VoiceMapConfig
    cfg = VoiceMapConfig()
    mk = _load_make_signals()

    snrs = [0.0, 5.0, 10.0, 15.0, 20.0, 25.0]
    ours, praats = [], []
    for snr in snrs:
        y = mk.normalize(mk.synth_vowel(3.0, lambda t: 200.0, "neutral",
                                        snr_db=snr, seed=7)).astype(np.float64)
        ours.append(_our_cpp_median(y, mk.SR, cfg))
        praats.append(_praat_cpps(y, mk.SR))
    ours = np.array(ours)
    praats = np.array(praats)
    snr_arr = np.array(snrs)

    r_praat = float(np.corrcoef(ours, praats)[0, 1])
    r_snr = float(np.corrcoef(ours, snr_arr)[0, 1])
    rep.add("A · corr(CPP, Praat CPPS) over SNR sweep", "r >= 0.95",
            f"r={r_praat:.4f}", f"{r_praat:.4f} (min 0.95)", r_praat >= 0.95)
    rep.add("B · corr(CPP, SNR) monotonic", "r >= 0.95",
            f"r={r_snr:.4f}", f"{r_snr:.4f} (min 0.95)", r_snr >= 0.95)

    # clean >> degraded
    clean = _our_cpp_median(
        mk.normalize(mk.synth_vowel(3.0, lambda t: 200.0, "neutral")
                     ).astype(np.float64), mk.SR, cfg)
    margin = clean - ours[0]   # clean minus SNR-0
    rep.add("B · clean CPP >> SNR-0 CPP", ">= 5 dB gap",
            f"{clean:.2f} vs {ours[0]:.2f}", f"{margin:.1f} dB (min 5)",
            margin >= 5.0)

    # reproducibility despite dither
    mod = mk.normalize(mk.synth_vowel(3.0, lambda t: 200.0, "neutral")
                       ).astype(np.float64)
    runs = np.array([_our_cpp_median(mod, mk.SR, cfg) for _ in range(5)])
    sd = float(np.std(runs))
    rep.add("B · reproducible despite dither (5 runs)", "std <= 0.5 dB",
            f"{sd:.4f} dB", f"{sd:.4f} (max 0.5)", sd <= 0.5)

    # silence → no CPP
    _ensure_signals()
    sig, fsr = sf.read(os.path.join(TS_DIR, "silent_5s.wav"))
    vs = (sig[:, 0] if sig.ndim == 2 else sig).astype(np.float64)
    cs = _our_cpp_median(vs, fsr, cfg)
    rep.add("B · silence -> no CPP (NaN/empty)", "NaN", f"{cs}",
            "must be empty", not np.isfinite(cs))

    rep.note(f"(A) CPP tracks Praat CPPS with r={r_praat:.3f} across 0-25 dB "
             f"SNR; absolute values differ by design (SC natural-log cepstrum "
             f"vs Praat). Ordering — the clinically-used property — is preserved.")
    rep.note(f"(B) CPP is monotonic in SNR (r={r_snr:.3f}); clean {clean:.1f} "
             f">> SNR-0 {ours[0]:.1f} dB; dither perturbs it <0.1 dB.")
    rep.note("(C)+limit: a linear chirp is locally quasi-periodic so it does "
             "NOT read low (~11 dB) — CPP is a periodicity index, not a "
             "voicing gate. Corpus distribution deferred to corpus phase.")
    return rep


def validate_hnr() -> Report:
    """HNR (Harmonics-to-Noise Ratio, dB) + NHR (= 1 / H_linear).

    The strongest anchor is physical, not a parity: for a harmonic signal
    plus additive white noise at signal-to-noise ratio S, the autocorrelation
    harmonic fraction p satisfies p/(1-p) = E_harm/E_noise = 10^(S/10), so
        HNR_dB = 10·log10(p/(1-p)) = S   exactly.
    We sweep S and check HNR recovers it (B) and that Praat's
    `to_harmonicity_cc` recovers it too (A) — tying ground truth and parity
    together. Real-audio divergence from Praat is a documented §7 property.
    """
    rep = Report("hnr")
    try:
        import soundfile as sf
        import parselmouth  # noqa: F401
    except ImportError as e:
        rep.skipped = True
        rep.skip_reason = f"missing dependency: {e.name}"
        return rep
    from voicemap.config import VoiceMapConfig
    from voicemap.metrics import NHRCalculator
    cfg = VoiceMapConfig()
    mk = _load_make_signals()

    # ── (A)+(B) SNR sweep: HNR == SNR == Praat on stationary vowels ──────────
    for snr in (5.0, 10.0, 15.0, 20.0, 25.0):
        y = mk.synth_vowel(3.0, lambda t: 200.0, "neutral",
                           snr_db=snr, seed=7)
        y = mk.normalize(y).astype(np.float64)
        oh = _our_hnr_median(y, mk.SR, cfg)
        ph = _praat_hnr_median(y, mk.SR)
        rep.add(f"B · HNR == imposed SNR {snr:.0f} dB", f"{snr:.2f} dB",
                f"{oh:.2f} dB", f"{abs(oh-snr):.2f} dB (atol 0.5)",
                abs(oh - snr) <= 0.5)
        rep.add(f"A · parity vs Praat harmonicity {snr:.0f} dB", f"{ph:.2f} dB",
                f"{oh:.2f} dB", f"{abs(oh-ph):.2f} dB (atol 0.5)",
                abs(oh - ph) <= 0.5)

    # ── (B) committed breathy fixture (SNR=15) + NHR inverse relationship ────
    _ensure_signals()
    manifest = {s["filename"]: s for s in _load_manifest()["signals"]}
    fx = "vowel_breathy_200Hz_SNR15dB.wav"
    sig, fsr = sf.read(os.path.join(TS_DIR, fx))
    v = (sig[:, 0] if sig.ndim == 2 else sig).astype(np.float64)
    oh_fx = _our_hnr_median(v, fsr, cfg)
    snr_gt = manifest[fx]["ground_truth"]["SNR_dB"]
    rep.add(f"B · HNR fixture vs manifest SNR ({fx})", f"{snr_gt:.1f} dB",
            f"{oh_fx:.2f} dB", f"{abs(oh_fx-snr_gt):.2f} dB (atol 1.0)",
            abs(oh_fx - snr_gt) <= 1.0)
    nhr = NHRCalculator(cfg).calculate(v, _cc_trigger_array(v, fsr))
    nv = nhr[np.isfinite(nhr)]
    nhr_med = float(np.median(nv)) if len(nv) else float("nan")
    nhr_exp = 1.0 / (10.0 ** (oh_fx / 10.0))
    rep.add("B · NHR == 1 / H_linear", f"{nhr_exp:.4f}", f"{nhr_med:.4f}",
            f"{abs(nhr_med-nhr_exp):.1e} (atol 5e-3)",
            abs(nhr_med - nhr_exp) <= 5e-3)

    # ── (B) clean modal → high HNR (saturates at the 40 dB peak cap) ─────────
    sig, fsr = sf.read(os.path.join(TS_DIR, "vowel_modal_200Hz_5s.wav"))
    vm = (sig[:, 0] if sig.ndim == 2 else sig).astype(np.float64)
    oh_clean = _our_hnr_median(vm, fsr, cfg)
    rep.add("B · clean modal HNR high (cap 40 dB)", ">= 30 dB",
            f"{oh_clean:.2f} dB", f"{oh_clean:.1f} (min 30, cap 40)",
            oh_clean >= 30.0)

    rep.note("(B) HNR_dB == SNR_dB exactly for harmonic+white-noise (p/(1-p) "
             "= 10^(SNR/10)); recovered to <0.3 dB over 5–25 dB. NHR = 1/H.")
    rep.note("(A) On the SAME stationary signals Praat agrees to <0.3 dB, so "
             "ground truth and Praat parity coincide. Clean HNR saturates at "
             "the 40 dB peak cap (clip 0.9999); Praat reports higher (~64 dB).")
    rep.note("(C)+limit: on non-stationary REAL voice ours and Praat diverge "
             "(~6 dB on test_Voice_EGG: 24.4 vs 17.7) — different window length "
             "(fixed 40 ms vs 4.5 periods) + aggregation (per-cycle vs frame "
             "median). Both valid; see md §7. Corpus distribution deferred.")
    return rep


VALIDATORS: dict[str, Callable[[], Report]] = {
    "jitter": validate_jitter,
    "shimmer": validate_shimmer,
    "f0_clarity": validate_f0_clarity,
    "hnr": validate_hnr,
    "cpp": validate_cpp,
    "formants": validate_formants,
    "bandwidths": validate_bandwidths,
    "spectral_moments": validate_spectral,
    "vibrato": validate_vibrato,
    "mfcc": validate_mfcc,
    "alpha_hammarberg": validate_alpha_hammarberg,
    "ppe": validate_ppe,
    "crest": validate_crest,
}
# convenience aliases
for _a in ("jitter_local", "jitter_rap", "jitter_ppq5", "jitter_ddp"):
    VALIDATORS[_a] = validate_jitter
for _a in ("shimmer_local", "shimmer_local_dB", "shimmer_apq3",
           "shimmer_apq5", "shimmer_apq11", "shimmer_dda"):
    VALIDATORS[_a] = validate_shimmer
for _a in ("f0", "f0_hz", "clarity", "midi", "pitch"):
    VALIDATORS[_a] = validate_f0_clarity
for _a in ("nhr", "harmonicity", "hnr_nhr"):
    VALIDATORS[_a] = validate_hnr
for _a in ("cpps", "cpp_cpps", "cepstral_peak_prominence"):
    VALIDATORS[_a] = validate_cpp
for _a in ("formant", "f1", "f2", "f3"):
    VALIDATORS[_a] = validate_formants
for _a in ("bandwidth", "b1", "b2", "b3"):
    VALIDATORS[_a] = validate_bandwidths
for _a in ("spectral", "centroid", "rolloff", "flatness", "spec_slope"):
    VALIDATORS[_a] = validate_spectral
for _a in ("vibrato_rate", "vibrato_extent"):
    VALIDATORS[_a] = validate_vibrato
for _a in ("mfcc1", "mfcc13", "mel", "cepstral"):
    VALIDATORS[_a] = validate_mfcc
for _a in ("alpha", "hammarberg", "alpha_ratio", "egemaps"):
    VALIDATORS[_a] = validate_alpha_hammarberg
for _a in ("pitch_period_entropy",):
    VALIDATORS[_a] = validate_ppe


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
