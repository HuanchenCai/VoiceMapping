#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AVQI tests: coefficient formula + Praat parity of the native inputs.

  1. avqi_from_components reproduces the AVQI Praat scripts' formulas
     (v03.01 and v02.02) on a fixed input vector.
  2. AVQICalculator's CPPS (Praat PowerCepstrogram convention) agrees with
     parselmouth `Get CPPS` on segments of the test recording.
  3. The LTAS slope / tilt definitions agree with Praat `Ltas: Get slope`
     and `Compute trend line` when fed a long-term spectrum.

Parity tests skip when parselmouth is not installed.

Run via:
    python tests/test_avqi.py
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
    from parselmouth.praat import call
    _PARSELMOUTH_OK = True
except ImportError:
    _PARSELMOUTH_OK = False

from voicemap.config import VoiceMapConfig
from voicemap.metrics import AVQICalculator, avqi_from_components

AUDIO = os.path.join(ROOT, "audio", "test_Voice_EGG.wav")
SEGMENTS_S = (0.0, 30.0, 60.0)
SEG_LEN_S = 6.0


def _segment(start_s: float) -> tuple[np.ndarray, int]:
    data, sr = sf.read(AUDIO, always_2d=True)
    a = int(start_s * sr)
    return data[a:a + int(SEG_LEN_S * sr), 0], sr


class TestAVQIFormula(unittest.TestCase):

    def test_v0301_matches_script(self):
        cpps, hnr, shim, shdb, slope, tilt = 14.0, 22.0, 3.5, 0.32, -25.0, -10.0
        expected = (4.152 - 0.177 * cpps - 0.006 * hnr - 0.037 * shim
                    + 0.941 * shdb + 0.01 * slope + 0.093 * tilt) * 2.8902
        got = avqi_from_components(cpps, hnr, shim, shdb, slope, tilt, "03.01")
        self.assertAlmostEqual(float(got), expected, places=10)

    def test_v0202_matches_script(self):
        cpps, hnr, shim, shdb, slope, tilt = 14.0, 22.0, 3.5, 0.32, -25.0, -10.0
        expected = ((3.295 - 0.111 * cpps - 0.073 * hnr - 0.213 * shim
                     + 2.789 * shdb - 0.032 * slope + 0.077 * tilt) * 2.208) + 1.797
        got = avqi_from_components(cpps, hnr, shim, shdb, slope, tilt, "02.02")
        self.assertAlmostEqual(float(got), expected, places=10)

    def test_vectorised_and_unknown_version(self):
        out = avqi_from_components(np.array([10.0, 20.0]), 20.0, 2.0, 0.2,
                                   -25.0, -10.0)
        self.assertEqual(out.shape, (2,))
        self.assertGreater(out[0], out[1])   # higher CPPS → better voice
        with self.assertRaises(ValueError):
            avqi_from_components(1, 1, 1, 1, 1, 1, version="9.99")


@unittest.skipUnless(_PARSELMOUTH_OK, "parselmouth not installed")
class TestAVQIPraatParity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.calc = AVQICalculator(VoiceMapConfig())

    def test_cpps_matches_praat(self):
        # Residual ~0.2-0.4 dB comes from Praat's robust trend fit
        # (see docs/validation/metrics/avqi.md §7).
        for s0 in SEGMENTS_S:
            x, sr = _segment(s0)
            pc = call(parselmouth.Sound(x, sr), "To PowerCepstrogram",
                      60, 0.002, 5000, 50)
            ref = call(pc, "Get CPPS", "no", 0.01, 0.001, 60, 330, 0.05,
                       "Parabolic", 0.001, 0, "Straight", "Robust")
            _, ours = self.calc._cpps_frames(x)
            self.assertLess(abs(ours.mean() - ref), 0.6,
                            f"{s0}s: ours {ours.mean():.2f} vs Praat {ref:.2f}")

    def test_ltas_slope_tilt_definition(self):
        # Feed a long-term spectrum (average of all frames) so the comparison
        # isolates the slope / tilt definitions from the local-LTAS window.
        calc = AVQICalculator(VoiceMapConfig(), ltas_avg_frames=1)
        for s0 in SEGMENTS_S:
            x, sr = _segment(s0)
            ltas = call(parselmouth.Sound(x, sr), "To Ltas", 1)
            ref_slope = call(ltas, "Get slope", 0, 1000, 1000, 10000, "energy")
            trend = call(ltas, "Compute trend line", 1, 10000)
            ref_tilt = call(trend, "Get slope", 0, 1000, 1000, 10000, "energy")

            slope, tilt = self._longterm_slope_tilt(calc, x, sr)
            self.assertLess(abs(slope - ref_slope), 0.5,
                            f"{s0}s slope: ours {slope:.2f} vs Praat {ref_slope:.2f}")
            self.assertLess(abs(tilt - ref_tilt), 0.6,
                            f"{s0}s tilt: ours {tilt:.2f} vs Praat {ref_tilt:.2f}")

    @staticmethod
    def _longterm_slope_tilt(calc, x, sr):
        from numpy.lib.stride_tricks import sliding_window_view
        win = int(calc.ltas_win_ms * 0.001 * sr)
        hop = int(calc.ltas_hop_ms * 0.001 * sr)
        fr = sliding_window_view(x, win)[::hop]
        fr = (fr - fr.mean(axis=1, keepdims=True)) * np.hanning(win)
        nfft = 1
        while nfft < win:
            nfft *= 2
        psd = (np.abs(np.fft.rfft(fr, nfft, axis=1)) ** 2).mean(axis=0)
        f = np.fft.rfftfreq(nfft, 1.0 / sr)
        lo = f <= 1000
        hi = (f >= 1000) & (f <= 10000)
        slope = 10 * np.log10(psd[hi].mean() / psd[lo].mean())
        b, a = np.polyfit(f[hi], 10 * np.log10(psd[hi]), 1)
        line = 10 ** ((a + b * f) / 10)
        tilt = 10 * np.log10(line[hi].mean() / line[lo].mean())
        return slope, tilt


class TestAVQICalculatorShape(unittest.TestCase):

    def test_per_cycle_alignment(self):
        sr = 44100
        t = np.arange(int(2.0 * sr)) / sr
        # Harmonic-rich 200 Hz source with -12 dB/oct roll-off
        clean = sum(np.sin(2 * np.pi * 200 * k * t) / k ** 2 for k in range(1, 40))
        noise = np.random.default_rng(0).standard_normal(len(t))
        trig = np.zeros(len(t))
        trig[::sr // 200] = 1.0
        n_cycles = int(trig.sum()) - 1
        calc = AVQICalculator(VoiceMapConfig())
        out = calc.calculate(clean + 0.001 * noise, trig)
        noisy = calc.calculate(clean + 0.2 * noise, trig)
        for k in AVQICalculator.KEYS:
            self.assertEqual(len(out[k]), n_cycles, k)
            self.assertTrue(np.all(np.isfinite(out[k])), k)
        # Added noise lowers CPPS and lifts the high band (flatter slope)
        self.assertGreater(out["cpps_praat"].mean(), noisy["cpps_praat"].mean() + 3.0)
        self.assertLess(out["ltas_slope"].mean(), noisy["ltas_slope"].mean())


if __name__ == "__main__":
    unittest.main(verbosity=2)
