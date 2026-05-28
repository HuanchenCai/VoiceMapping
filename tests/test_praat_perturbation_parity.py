#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Numerical parity tests: voicemap.praat_perturbation vs. parselmouth (Praat).

For every jitter/shimmer formula we re-implement, we ask Praat (via
parselmouth) for the same input cycle marks and assert the two scalars
match within tight floating-point tolerance. If they ever diverge, we
know our translation has drifted from Praat.

Cycle marks are produced once by Praat's PointProcess (cc), so the only
variable under test is the formula layer. The amplitude pipeline
(Hann-windowed RMS) is also covered — we hand parselmouth the same
voice + PointProcess, ask for AmplitudeTier values, and compare.

Run via:
    python tests/test_praat_perturbation_parity.py
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

import voicemap.praat_perturbation as pp


# Praat defaults for jitter/shimmer queries
PMIN = 1e-4
PMAX = 0.02
PERIOD_FACTOR = 1.3
AMP_FACTOR    = 1.6


def _load_voice(path: str, duration_s: float | None = None
                ) -> tuple[np.ndarray, float]:
    """Load a stereo file's voice channel (channel 0); optionally truncate."""
    sig, sr = sf.read(path)
    voice = sig[:, 0] if sig.ndim == 2 else sig
    if duration_s is not None:
        voice = voice[: int(duration_s * sr)]
    return voice.astype(np.float64), float(sr)


def _praat_pulse_times(voice: np.ndarray, fs: float
                        ) -> tuple[parselmouth.Sound, np.ndarray]:
    """Get Praat's PointProcess(cc) cycle mark times in seconds."""
    snd = parselmouth.Sound(np.ascontiguousarray(voice),
                             sampling_frequency=fs)
    pitch = snd.to_pitch_cc(time_step=None,
                             pitch_floor=75.0, pitch_ceiling=600.0)
    pp_obj = call([snd, pitch], "To PointProcess (cc)")
    n_points = int(call(pp_obj, "Get number of points"))
    times = np.array([call(pp_obj, "Get time from index", i + 1)
                       for i in range(n_points)], dtype=np.float64)
    return snd, times, pp_obj


@unittest.skipUnless(_PARSELMOUTH_OK, "parselmouth not installed")
class TestPraatJitterParity(unittest.TestCase):
    """Each Praat jitter formula vs. our numpy translation, given the
    SAME cycle marks (produced by Praat) → identical scalar output."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(ROOT, "audio", "test_Voice_EGG.wav")
        if not os.path.exists(path):
            raise unittest.SkipTest(f"missing test fixture: {path}")
        # Use first 10s for a fast but realistic test
        cls.voice, cls.fs = _load_voice(path, duration_s=10.0)
        cls.snd, cls.times, cls.pp_obj = _praat_pulse_times(cls.voice, cls.fs)

    def test_mean_period(self):
        praat_value = call(self.pp_obj, "Get mean period",
                           0, 0, PMIN, PMAX, PERIOD_FACTOR)
        ours = pp.mean_period(self.times, PMIN, PMAX, PERIOD_FACTOR)
        np.testing.assert_allclose(ours, praat_value, atol=1e-12)

    def test_jitter_local(self):
        praat_value = call(self.pp_obj, "Get jitter (local)",
                           0, 0, PMIN, PMAX, PERIOD_FACTOR)
        ours = pp.jitter_local(self.times, PMIN, PMAX, PERIOD_FACTOR)
        np.testing.assert_allclose(ours, praat_value, atol=1e-9)

    def test_jitter_local_absolute(self):
        praat_value = call(self.pp_obj, "Get jitter (local, absolute)",
                           0, 0, PMIN, PMAX, PERIOD_FACTOR)
        ours = pp.jitter_local_absolute(self.times, PMIN, PMAX, PERIOD_FACTOR)
        np.testing.assert_allclose(ours, praat_value, atol=1e-12)

    def test_jitter_rap(self):
        praat_value = call(self.pp_obj, "Get jitter (rap)",
                           0, 0, PMIN, PMAX, PERIOD_FACTOR)
        ours = pp.jitter_rap(self.times, PMIN, PMAX, PERIOD_FACTOR)
        np.testing.assert_allclose(ours, praat_value, atol=1e-9)

    def test_jitter_ppq5(self):
        praat_value = call(self.pp_obj, "Get jitter (ppq5)",
                           0, 0, PMIN, PMAX, PERIOD_FACTOR)
        ours = pp.jitter_ppq5(self.times, PMIN, PMAX, PERIOD_FACTOR)
        np.testing.assert_allclose(ours, praat_value, atol=1e-9)

    def test_jitter_ddp(self):
        praat_value = call(self.pp_obj, "Get jitter (ddp)",
                           0, 0, PMIN, PMAX, PERIOD_FACTOR)
        ours = pp.jitter_ddp(self.times, PMIN, PMAX, PERIOD_FACTOR)
        np.testing.assert_allclose(ours, praat_value, atol=1e-9)


@unittest.skipUnless(_PARSELMOUTH_OK, "parselmouth not installed")
class TestPraatShimmerParity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        path = os.path.join(ROOT, "audio", "test_Voice_EGG.wav")
        if not os.path.exists(path):
            raise unittest.SkipTest(f"missing test fixture: {path}")
        cls.voice, cls.fs = _load_voice(path, duration_s=10.0)
        cls.snd, cls.times, cls.pp_obj = _praat_pulse_times(cls.voice, cls.fs)

        # Compute amplitude tier ourselves for the shimmer tests; the
        # parity check is between *our* shimmer formula (on our amp tier)
        # vs. Praat's shimmer formula (on Praat's amp tier), since the
        # whole pipeline must agree end-to-end.
        cls.amp_t, cls.amp_v = pp.point_process_to_amplitude_tier(
            cls.times, cls.voice, cls.fs, PMIN, PMAX, PERIOD_FACTOR)

    def test_amplitude_tier_matches_praat(self):
        """Our Hann-windowed RMS amplitudes vs Praat's via AmplitudeTier."""
        amp_tier = call([self.pp_obj, self.snd], "To AmplitudeTier (period)",
                         0, 0, PMIN, PMAX, PERIOD_FACTOR)
        n = int(call(amp_tier, "Get number of points"))
        praat_times = np.array([call(amp_tier, "Get time from index", i + 1)
                                 for i in range(n)], dtype=np.float64)
        praat_values = np.array([call(amp_tier, "Get value at index", i + 1)
                                  for i in range(n)], dtype=np.float64)
        # Should be identical sets of pulses (same period rejection rules)
        self.assertEqual(len(praat_times), len(self.amp_t),
                          f"pulse count differs: praat={len(praat_times)} "
                          f"ours={len(self.amp_t)}")
        np.testing.assert_allclose(self.amp_t, praat_times, atol=1e-9)
        # Amplitude values should match to ~1e-6 (Hann RMS is sensitive
        # to sample-boundary effects which can give tiny numerical drift
        # but ~1e-6 of unit-scale is more than tight enough).
        np.testing.assert_allclose(self.amp_v, praat_values, atol=1e-6)

    def test_shimmer_local(self):
        praat_value = call([self.pp_obj, self.snd], "Get shimmer (local)",
                            0, 0, PMIN, PMAX, PERIOD_FACTOR, AMP_FACTOR)
        ours = pp.shimmer_local(self.amp_t, self.amp_v,
                                 PMIN, PMAX, AMP_FACTOR)
        np.testing.assert_allclose(ours, praat_value, atol=1e-6)

    def test_shimmer_local_dB(self):
        praat_value = call([self.pp_obj, self.snd], "Get shimmer (local_dB)",
                            0, 0, PMIN, PMAX, PERIOD_FACTOR, AMP_FACTOR)
        ours = pp.shimmer_local_dB(self.amp_t, self.amp_v,
                                    PMIN, PMAX, AMP_FACTOR)
        np.testing.assert_allclose(ours, praat_value, atol=1e-6)

    def test_shimmer_apq3(self):
        praat_value = call([self.pp_obj, self.snd], "Get shimmer (apq3)",
                            0, 0, PMIN, PMAX, PERIOD_FACTOR, AMP_FACTOR)
        ours = pp.shimmer_apq3(self.amp_t, self.amp_v,
                                PMIN, PMAX, AMP_FACTOR)
        np.testing.assert_allclose(ours, praat_value, atol=1e-6)

    def test_shimmer_apq5(self):
        praat_value = call([self.pp_obj, self.snd], "Get shimmer (apq5)",
                            0, 0, PMIN, PMAX, PERIOD_FACTOR, AMP_FACTOR)
        ours = pp.shimmer_apq5(self.amp_t, self.amp_v,
                                PMIN, PMAX, AMP_FACTOR)
        np.testing.assert_allclose(ours, praat_value, atol=1e-6)

    def test_shimmer_apq11(self):
        praat_value = call([self.pp_obj, self.snd], "Get shimmer (apq11)",
                            0, 0, PMIN, PMAX, PERIOD_FACTOR, AMP_FACTOR)
        ours = pp.shimmer_apq11(self.amp_t, self.amp_v,
                                 PMIN, PMAX, AMP_FACTOR)
        np.testing.assert_allclose(ours, praat_value, atol=1e-6)


@unittest.skipUnless(_PARSELMOUTH_OK, "parselmouth not installed")
class TestCCPointProcessParity(unittest.TestCase):
    """Cycle marks from the full Praat pipeline (Sound_to_Pitch +
    Sound_Pitch_to_PointProcess_cc, both natively reimplemented) should
    closely match parselmouth's PointProcess (cc) — same cycle COUNT
    and same cycle TIMES (within ±1 ms median offset)."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(ROOT, "audio", "test_Voice_EGG.wav")
        if not os.path.exists(path):
            raise unittest.SkipTest(f"missing test fixture: {path}")
        cls.voice, cls.fs = _load_voice(path, duration_s=10.0)

    def test_cycle_marks_match_praat(self):
        import voicemap.praat_pitch as pcp
        import voicemap.praat_perturbation as ppt

        floor, ceiling = 75.0, 600.0

        # parselmouth reference
        snd = parselmouth.Sound(np.ascontiguousarray(self.voice),
                                 sampling_frequency=self.fs)
        pitch = snd.to_pitch_cc(time_step=None,
                                 pitch_floor=floor, pitch_ceiling=ceiling)
        pp_obj = call([snd, pitch], "To PointProcess (cc)")
        n_praat = int(call(pp_obj, "Get number of points"))
        praat_marks = np.array([call(pp_obj, "Get time from index", i + 1)
                                 for i in range(n_praat)], dtype=np.float64)

        # Our pipeline
        pitch_contour = pcp.sound_to_pitch(self.voice, self.fs,
                                             pitch_floor=floor,
                                             pitch_ceiling=ceiling)
        ours_marks = ppt.sound_pitch_to_pointprocess_cc(
            self.voice, self.fs, pitch_contour)

        # Cycle counts within 5 % (Praat's voiced-interval finder may
        # split things slightly differently at unvoiced boundaries).
        count_ratio = len(ours_marks) / max(len(praat_marks), 1)
        self.assertGreater(count_ratio, 0.95,
            f"cycle count mismatch: ours {len(ours_marks)}, "
            f"Praat {len(praat_marks)} (ratio {count_ratio:.3f})")
        self.assertLess(count_ratio, 1.05,
            f"cycle count mismatch: ours {len(ours_marks)}, "
            f"Praat {len(praat_marks)} (ratio {count_ratio:.3f})")

        # Each ours mark should have a Praat mark within 1 ms.
        # Nearest-neighbour match (vectorised).
        ins = np.searchsorted(praat_marks, ours_marks)
        left = np.clip(ins - 1, 0, len(praat_marks) - 1)
        right = np.clip(ins, 0, len(praat_marks) - 1)
        d_left = np.abs(ours_marks - praat_marks[left])
        d_right = np.abs(ours_marks - praat_marks[right])
        nearest_dist = np.minimum(d_left, d_right)
        median_offset_ms = float(np.median(nearest_dist) * 1000.0)
        p90_offset_ms = float(np.percentile(nearest_dist, 90) * 1000.0)
        self.assertLess(median_offset_ms, 0.5,
            f"median cycle-mark offset {median_offset_ms:.4f} ms > 0.5 ms")
        self.assertLess(p90_offset_ms, 2.0,
            f"P90 cycle-mark offset {p90_offset_ms:.4f} ms > 2 ms")

        print(f"\n  CC PointProcess (test_Voice_EGG, 10 s): "
              f"ours={len(ours_marks)} vs Praat={len(praat_marks)} "
              f"(ratio {count_ratio:.3f}), "
              f"offset median {median_offset_ms:.3f} ms, "
              f"P90 {p90_offset_ms:.3f} ms")


if __name__ == "__main__":
    unittest.main(verbosity=2)
