# -*- coding: utf-8 -*-
"""Regression tests for voicemap.report._THRESHOLDS.

The Inspector / report rendering rely on the threshold table being
well-formed:
- Each entry's bands must cover continuously from -inf to +inf so any
  measured value falls into exactly one band.
- Severity tags must be from a fixed set (good / normal / watch / abnormal).
- Bands must be in lo→hi monotonic order (else the in-band lookup
  returns the wrong cell).

Run via:
    python tests/test_report_thresholds.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from voicemap.report import _THRESHOLDS  # noqa: E402

VALID_SEVERITY = {"good", "normal", "watch", "abnormal"}


class TestThresholds(unittest.TestCase):

    def test_severities_are_valid(self):
        for metric, bands in _THRESHOLDS.items():
            for lo, hi, label, sev in bands:
                self.assertIn(
                    sev, VALID_SEVERITY,
                    f"{metric}: invalid severity {sev!r} (band {label!r})")

    def test_bands_have_lo_le_hi(self):
        """Within each band, lo ≤ hi. Otherwise the in-band lookup
        ``lo <= value < hi`` is unsatisfiable."""
        for metric, bands in _THRESHOLDS.items():
            for i, (lo, hi, _label, _sev) in enumerate(bands):
                self.assertLessEqual(
                    lo, hi, f"{metric}: band {i} has lo {lo} > hi {hi}")

    def test_bands_dont_overlap(self):
        """No value falls into two bands at once. Sort by lo and check
        consecutive ranges don't overlap."""
        for metric, bands in _THRESHOLDS.items():
            sorted_bands = sorted(bands, key=lambda b: b[0])
            for i in range(len(sorted_bands) - 1):
                cur_hi = sorted_bands[i][1]
                next_lo = sorted_bands[i + 1][0]
                self.assertLessEqual(
                    cur_hi, next_lo,
                    f"{metric}: band {i} (..., {cur_hi}) overlaps with "
                    f"band {i+1} ({next_lo}, ...)")

    def test_band_label_nonempty(self):
        for metric, bands in _THRESHOLDS.items():
            for lo, hi, label, _sev in bands:
                self.assertTrue(
                    label, f"{metric}: empty label in band ({lo}, {hi})")


if __name__ == "__main__":
    unittest.main(verbosity=2)
