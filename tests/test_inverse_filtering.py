#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit + smoke tests for the IAIF / voice-only GCI pipeline.

Covers:
  - Low-level LPC (Levinson-Durbin) degenerate inputs
  - IAIF on synthetic Liljencrants-Fant-like pulses through a single-formant
    filter → output shape, finiteness, GCI count, F0 accuracy
  - voice_to_cycle_triggers convenience wrapper format
  - End-to-end VoiceMapAnalyzer on a synthetic mono recording → all
    *_voice columns populated, all EGG-original columns zero

Run via:
    python tests/test_inverse_filtering.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf
from scipy.signal import lfilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Synthetic-signal helpers
# ---------------------------------------------------------------------------
def _synthesize_vowel(fs, duration_s, f0_hz,
                       oq=0.6,
                       formants=None,
                       noise_std=0.005,
                       seed=0):
    """Generate a voice-like signal:
       half-sine glottal pulse train (open quotient ``oq``) → radiation
       (differentiator) → vocal tract (cascade of single-formant filters)
       → additive white noise."""
    if formants is None:
        formants = [(700.0, 80.0), (1200.0, 100.0), (2600.0, 150.0)]

    rng = np.random.default_rng(seed)
    n = int(duration_s * fs)
    g = np.zeros(n, dtype=np.float64)
    period = int(round(fs / f0_hz))
    pulse_len = int(period * oq)
    pulse = np.sin(np.pi * np.arange(pulse_len) / pulse_len)
    for start in range(0, n - pulse_len, period):
        g[start:start + pulse_len] = pulse

    # Radiation: lip differentiator
    s = np.diff(g, prepend=0.0)

    # Cascade of single-pole-pair formant filters
    for f, bw in formants:
        r = np.exp(-np.pi * bw / fs)
        theta = 2.0 * np.pi * f / fs
        s = lfilter([1.0], [1.0, -2.0 * r * np.cos(theta), r * r], s)

    s = s / (np.max(np.abs(s)) + 1e-12) * 0.5
    s += noise_std * rng.standard_normal(len(s))
    return s


# ---------------------------------------------------------------------------
# Low-level LPC tests
# ---------------------------------------------------------------------------
class TestLPC(unittest.TestCase):
    def test_zero_input_returns_identity(self):
        from voicemap.inverse_filtering import _lpc_autocorr
        a = _lpc_autocorr(np.zeros(100), 8)
        self.assertEqual(a[0], 1.0)
        self.assertTrue(np.all(a[1:] == 0.0))

    def test_short_input_returns_identity(self):
        """Length <= order: refuse to fit, return identity rather than crash."""
        from voicemap.inverse_filtering import _lpc_autocorr
        a = _lpc_autocorr(np.random.randn(5), 10)
        self.assertEqual(a[0], 1.0)
        self.assertTrue(np.all(a[1:] == 0.0))

    def test_order_zero_returns_identity(self):
        from voicemap.inverse_filtering import _lpc_autocorr
        a = _lpc_autocorr(np.random.randn(100), 0)
        self.assertEqual(a.shape, (1,))
        self.assertEqual(a[0], 1.0)

    def test_known_ar_recovery(self):
        """LPC should recover AR coefficients of a pure AR process."""
        from voicemap.inverse_filtering import _lpc_autocorr
        rng = np.random.default_rng(42)
        true_a = np.array([1.0, -1.2, 0.6])
        x = lfilter([1.0], true_a, rng.standard_normal(20000))
        est = _lpc_autocorr(x, 2)
        np.testing.assert_allclose(est, true_a, atol=0.05)


# ---------------------------------------------------------------------------
# IAIF tests
# ---------------------------------------------------------------------------
class TestIAIF(unittest.TestCase):
    def test_output_shape_and_finite(self):
        from voicemap.inverse_filtering import iaif
        fs = 44100
        x = _synthesize_vowel(fs, 0.5, 180.0)
        g, dg = iaif(x, fs)
        self.assertEqual(g.shape, x.shape)
        self.assertEqual(dg.shape, x.shape)
        self.assertTrue(np.all(np.isfinite(g)))
        self.assertTrue(np.all(np.isfinite(dg)))

    def test_short_signal_returns_zeros(self):
        """Signals shorter than 50 ms can't fit IAIF — must degrade gracefully."""
        from voicemap.inverse_filtering import iaif
        fs = 44100
        x = np.random.randn(int(0.01 * fs))   # 10 ms
        g, dg = iaif(x, fs)
        self.assertEqual(g.shape, x.shape)
        self.assertTrue(np.all(g == 0.0))
        self.assertTrue(np.all(dg == 0.0))

    def test_glottal_flow_amplitude_sane(self):
        """Glottal flow shouldn't blow up to crazy magnitudes — OLA divisor
        was a real bug; this guards against regression."""
        from voicemap.inverse_filtering import iaif
        fs = 44100
        x = _synthesize_vowel(fs, 1.0, 200.0)
        g, dg = iaif(x, fs)
        # Guards against the win**2 OLA divisor bug that produced
        # ~30 000× input amplitude. 500× catches that easily while
        # leaving headroom for the legitimate gain from integrating dg.
        x_peak = float(np.max(np.abs(x)))
        self.assertLess(float(np.max(np.abs(g))), 500.0 * x_peak)
        self.assertLess(float(np.max(np.abs(dg))), 500.0 * x_peak)


# ---------------------------------------------------------------------------
# GCI detection tests
# ---------------------------------------------------------------------------
class TestGCIDetection(unittest.TestCase):
    def test_constant_f0_cycle_count(self):
        """200 Hz vowel for 1 s should produce roughly 200 GCIs (±5%)."""
        from voicemap.inverse_filtering import voice_to_cycle_triggers
        fs = 44100
        f0 = 200.0
        duration = 1.0
        x = _synthesize_vowel(fs, duration, f0)
        triggers, _, _ = voice_to_cycle_triggers(x, fs)
        n = int(triggers.sum())
        expected = int(duration * f0)
        rel_err = abs(n - expected) / expected
        self.assertLess(rel_err, 0.05,
                        f"expected ~{expected} cycles, got {n}")

    def test_estimated_f0_accurate(self):
        from voicemap.inverse_filtering import voice_to_cycle_triggers
        fs = 44100
        for f0_true in (120.0, 200.0, 350.0):
            x = _synthesize_vowel(fs, 1.0, f0_true)
            triggers, _, _ = voice_to_cycle_triggers(
                x, fs, min_f0_hz=50.0, max_f0_hz=800.0)
            gci = np.where(triggers > 0.5)[0]
            self.assertGreaterEqual(len(gci), 2,
                                     f"no cycles detected for F0={f0_true}")
            f0_est = fs / np.diff(gci).mean()
            err_pct = abs(f0_est - f0_true) / f0_true * 100
            self.assertLess(err_pct, 3.0,
                f"F0={f0_true}: estimated {f0_est:.1f} Hz (err {err_pct:.1f}%)")

    def test_silent_input_returns_no_cycles(self):
        from voicemap.inverse_filtering import voice_to_cycle_triggers
        fs = 44100
        x = np.zeros(int(fs * 0.5))
        triggers, _, _ = voice_to_cycle_triggers(x, fs)
        self.assertEqual(int(triggers.sum()), 0)


# ---------------------------------------------------------------------------
# Analyzer integration: branch + cache state + _voice columns end-to-end.
# ---------------------------------------------------------------------------
class TestAnalyzerIntegration(unittest.TestCase):
    def test_voice_only_detection_caches_flow(self):
        from voicemap.analyzer import VoiceMapAnalyzer
        a = VoiceMapAnalyzer()
        x = _synthesize_vowel(a.config.sample_rate, 1.0, 180.0)
        triggers = a.voice_only_cycle_detection(x)
        self.assertEqual(triggers.shape, x.shape)
        self.assertIsNotNone(a._glottal_flow)
        self.assertIsNotNone(a._glottal_flow_derivative)
        self.assertEqual(len(a._glottal_flow), len(x))

    def test_end_to_end_mono_csv(self):
        """Full pipeline on synthetic mono → CSV with populated _voice columns
        and zero EGG-original columns."""
        import pandas as pd
        from voicemap.analyzer import VoiceMapAnalyzer
        from voicemap.config import VoiceMapConfig

        fs = 44100
        x = _synthesize_vowel(fs, 3.0, 180.0)

        with tempfile.TemporaryDirectory() as td:
            mono_file = os.path.join(td, "synthetic_mono.wav")
            sf.write(mono_file, x, fs)

            cfg = VoiceMapConfig()
            cfg.output_dir = td
            a = VoiceMapAnalyzer(cfg)
            result = a.analyze_and_output_vrp(mono_file, plot_mode="none")
            out_file = result[1]
            self.assertTrue(os.path.exists(out_file))

            df = pd.read_csv(out_file, sep=';')

            for col in ('Qcontact_voice', 'dEGGmax_voice', 'Icontact_voice',
                        'Entropy_voice', 'HRFegg_voice',
                        'OQ_voice', 'SPQ_voice', 'CIQ_voice'):
                self.assertIn(col, df.columns, f"{col} missing from CSV")
                self.assertTrue((df[col] != 0).any(),
                                f"{col} is all zero — IAIF didn't run?")

            for col in ('Qcontact', 'dEGGmax', 'Icontact',
                        'Entropy', 'HRFegg', 'OQ', 'SPQ', 'CIQ'):
                self.assertTrue((df[col] == 0).all(),
                    f"mono mode but EGG-original {col} is non-zero")

            qc_mean = df['Qcontact_voice'].mean()
            self.assertTrue(0.2 < qc_mean < 0.9,
                f"Qcontact_voice mean {qc_mean:.3f} outside plausible range")


if __name__ == "__main__":
    unittest.main()
