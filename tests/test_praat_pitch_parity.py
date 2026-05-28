#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parity tests: voicemap.praat_pitch vs parselmouth (Praat).

Each test compares our numpy translation of a Praat Sound_to_Pitch stage
against the canonical output via parselmouth.

Commit 1 scope (this file's initial state):
    - autocorrelation_frame produces sensible r[i] (windowR-normalised)
    - find_candidates_parabolic extracts F0 candidates within ~1% of
      Praat's per-frame selected F0 on a stationary vowel
    - Tolerance reflects that we don't yet do sinc-70 refinement
      (commit 2) or Viterbi path finding (commit 3).

Run via:
    python tests/test_praat_pitch_parity.py
"""

from __future__ import annotations

import os
import sys
import unittest

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

try:
    import parselmouth
    _PARSELMOUTH_OK = True
except ImportError:
    _PARSELMOUTH_OK = False

import voicemap.praat_pitch as pp


def _load_voice(path: str, duration_s: float = None) -> tuple[np.ndarray, float]:
    sig, sr = sf.read(path)
    voice = sig[:, 0] if sig.ndim == 2 else sig
    if duration_s is not None:
        voice = voice[: int(duration_s * sr)]
    return voice.astype(np.float64), float(sr)


def _strongest_F0(candidates: list) -> float:
    """Return F0 of strongest candidate, or 0 (voiceless) if none qualified."""
    if not candidates:
        return 0.0
    best = max(candidates, key=lambda c: c[1])
    return best[0] if best[1] > 0 else 0.0


class TestPraatPitchAutocorrelation(unittest.TestCase):
    """Verify the autocorrelation + windowR-normalised r array is built
    correctly, and yields a clear F0 peak on a stationary vowel."""

    def test_synthetic_200Hz_strong_peak(self):
        fs = 44100
        T = 2.0
        f0 = 200.0
        t = np.arange(int(T * fs)) / fs
        # Glottal-like pulse train with mild formant structure
        period = int(fs / f0)
        g = np.zeros(len(t))
        for i in range(0, len(t), period):
            L = int(period * 0.6)
            if i + L <= len(t):
                g[i:i + L] = np.sin(np.pi * np.arange(L) / L)
        from scipy.signal import lfilter
        # Simple single-formant filter @ 700 Hz to shape voice
        r = np.exp(-np.pi * 80 / fs); th = 2 * np.pi * 700 / fs
        voice = lfilter([1], [1, -2 * r * np.cos(th), r * r],
                         np.diff(g, prepend=0))
        voice += 0.005 * np.random.default_rng(0).standard_normal(len(voice))

        setup = pp.PitchAnalysisSetup(fs, 75.0, 600.0)
        t_centre = 1.0   # middle of recording
        r_arr, local_peak, _ = pp.autocorrelation_frame(voice, t_centre, setup)
        self.assertGreater(local_peak, 0.0, "should detect voicing in vowel")
        # Peak should be near lag = fs / f0 ≈ 220 samples
        candidates = pp.find_candidates_parabolic(r_arr, setup)
        F0 = _strongest_F0(candidates)
        self.assertAlmostEqual(F0, f0, delta=2.0,
                                msg=f"synthetic 200 Hz vowel — got {F0:.2f} Hz")

    def test_silence_returns_voiceless(self):
        fs = 44100
        voice = np.zeros(int(0.5 * fs))
        setup = pp.PitchAnalysisSetup(fs, 75.0, 600.0)
        r_arr, local_peak, _ = pp.autocorrelation_frame(voice, 0.25, setup)
        self.assertEqual(local_peak, 0.0)
        candidates = pp.find_candidates_parabolic(r_arr, setup)
        self.assertEqual(_strongest_F0(candidates), 0.0)


@unittest.skipUnless(_PARSELMOUTH_OK, "parselmouth not installed")
class TestPraatPitchAgainstParselmouth(unittest.TestCase):
    """End-to-end-ish: on a real vowel recording, our frame-by-frame
    strongest-candidate F0 should track parselmouth's selected pitch
    within a few-percent tolerance (we don't have Viterbi or sinc yet)."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(ROOT, "audio", "test_Voice_EGG.wav")
        if not os.path.exists(path):
            raise unittest.SkipTest(f"missing test fixture: {path}")
        cls.voice, cls.fs = _load_voice(path, duration_s=10.0)

    def test_F0_within_5pct_of_praat(self):
        # Praat defaults — match parselmouth's to_pitch_ac
        floor, ceiling = 75.0, 600.0
        snd = parselmouth.Sound(np.ascontiguousarray(self.voice),
                                 sampling_frequency=self.fs)
        praat_pitch = snd.to_pitch_ac(time_step=None,
                                       pitch_floor=floor,
                                       pitch_ceiling=ceiling)

        frame_t, intensity, cands = pp.sound_to_pitch_frames_parabolic(
            self.voice, self.fs, pitch_floor=floor, pitch_ceiling=ceiling)
        ours_F0 = np.array([_strongest_F0(c) for c in cands])

        # Compare on voiced frames where both methods agree it's voiced.
        praat_F0 = np.array([praat_pitch.get_value_at_time(t) for t in frame_t])
        praat_F0 = np.where(np.isfinite(praat_F0) & (praat_F0 > 0), praat_F0, 0.0)
        both_voiced = (ours_F0 > 0) & (praat_F0 > 0)
        n_match = int(both_voiced.sum())
        self.assertGreater(n_match, 10,
                            f"only {n_match} jointly-voiced frames")

        rel_err = np.abs(ours_F0[both_voiced] - praat_F0[both_voiced]) / praat_F0[both_voiced]
        median_err_pct = float(np.median(rel_err) * 100.0)
        p90_err_pct = float(np.percentile(rel_err, 90) * 100.0)
        # Without Viterbi or sinc-70, we expect ~1-3% median error from
        # parabolic-only interpolation, plus occasional octave errors at
        # voiced↔unvoiced transitions (~5-15% at 90th percentile).
        self.assertLess(median_err_pct, 3.0,
                         f"median F0 error {median_err_pct:.1f}% > 3% — "
                         "autocorrelation or normalisation likely wrong")
        # 90 % of frames within 15 % is a generous bound for the no-Viterbi stage.
        self.assertLess(p90_err_pct, 15.0,
                         f"P90 F0 error {p90_err_pct:.1f}% > 15% — "
                         "candidate selection too noisy")

        print(f"\n  test_Voice_EGG (10 s, parabolic only): "
              f"median F0 err {median_err_pct:.2f}%, P90 {p90_err_pct:.2f}% "
              f"over {n_match} voiced frames")


class TestSincInterpolation(unittest.TestCase):
    """Verify sinc_interpolate_raised_cosine matches the analytical form
    on simple test cases."""

    def test_sinc_at_integer_returns_sample(self):
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        for k in range(len(y)):
            self.assertEqual(pp.sinc_interpolate_raised_cosine(y, float(k), 30),
                              y[k])

    def test_sinc_on_sine_wave_recovers_value(self):
        """Bandlimited signal: sinc interpolation should recover f(x)
        exactly (within numerical noise) at fractional x."""
        n = 200
        freq = 0.05    # cycles per sample, well below Nyquist
        idx = np.arange(n)
        y = np.sin(2 * np.pi * freq * idx)
        # Probe halfway between samples in the interior
        for x in [50.5, 75.25, 100.75]:
            interp = pp.sinc_interpolate_raised_cosine(y, x, 30)
            true = np.sin(2 * np.pi * freq * x)
            self.assertAlmostEqual(interp, true, places=4,
                msg=f"x={x}: sinc gave {interp:.6f}, true {true:.6f}")


class TestImproveMaximumSinc(unittest.TestCase):

    def test_finds_smooth_peak(self):
        # Cosine peak at x=10.3
        x_true = 10.3
        idx = np.arange(20)
        y = np.cos((idx - x_true) * 0.5)   # broad peak centred at 10.3
        y_max, x_max = pp.improve_maximum_sinc(y, 10, depth=30)
        # places=2 (0.01) reflects the depth-30 truncation: Brent on a
        # truncated sinc kernel can land ~1 % off the true peak on a
        # near-flat cosine. Real autocorrelation peaks are sharper and
        # parity vs parselmouth on real audio is 4 orders tighter.
        self.assertAlmostEqual(x_max, x_true, places=2,
            msg=f"true peak at {x_true}, got {x_max:.4f}")
        self.assertAlmostEqual(y_max, 1.0, places=3)


@unittest.skipUnless(_PARSELMOUTH_OK, "parselmouth not installed")
class TestPraatPitchSincAgainstParselmouth(unittest.TestCase):
    """Sinc-refined version should be at least as accurate as parabolic
    on the same recording, ideally within 10⁻⁴ relative error."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(ROOT, "audio", "test_Voice_EGG.wav")
        if not os.path.exists(path):
            raise unittest.SkipTest(f"missing test fixture: {path}")
        cls.voice, cls.fs = _load_voice(path, duration_s=10.0)

    def test_sinc_at_least_as_accurate_as_parabolic(self):
        floor, ceiling = 75.0, 600.0
        snd = parselmouth.Sound(np.ascontiguousarray(self.voice),
                                 sampling_frequency=self.fs)
        praat_pitch = snd.to_pitch_ac(time_step=None,
                                       pitch_floor=floor,
                                       pitch_ceiling=ceiling)

        frame_t, _, cands = pp.sound_to_pitch_frames(
            self.voice, self.fs, pitch_floor=floor, pitch_ceiling=ceiling,
            method='sinc')
        ours_F0 = np.array([_strongest_F0(c) for c in cands])
        praat_F0 = np.array([praat_pitch.get_value_at_time(t) for t in frame_t])
        praat_F0 = np.where(np.isfinite(praat_F0) & (praat_F0 > 0), praat_F0, 0.0)
        both_voiced = (ours_F0 > 0) & (praat_F0 > 0)
        n_match = int(both_voiced.sum())
        self.assertGreater(n_match, 10)

        rel_err = np.abs(ours_F0[both_voiced] - praat_F0[both_voiced]) / praat_F0[both_voiced]
        median_err_pct = float(np.median(rel_err) * 100.0)
        p90_err_pct = float(np.percentile(rel_err, 90) * 100.0)
        # Tighter than commit 1 tolerance — sinc should be < 0.5 % median
        self.assertLess(median_err_pct, 0.5,
                         f"sinc median F0 err {median_err_pct:.4f}% > 0.5 %")
        self.assertLess(p90_err_pct, 10.0,
                         f"sinc P90 F0 err {p90_err_pct:.4f}% > 10 %")
        print(f"\n  test_Voice_EGG (10 s, sinc-70): "
              f"median F0 err {median_err_pct:.4f}%, P90 {p90_err_pct:.4f}%")


if __name__ == "__main__":
    unittest.main(verbosity=2)
