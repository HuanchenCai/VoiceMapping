# -*- coding: utf-8 -*-
"""Regression tests for `_THRESHOLDS_LABEL_EN` / `get_band_label`.

GUI Inspector swaps zh band labels for en at render time via
`get_band_label(zh_label, lang)`. We must guarantee:
  - every zh label in `_THRESHOLDS` has an en mapping (otherwise en
    users see a sudden zh leak on certain metrics);
  - `get_band_label` falls back to the original string when no mapping
    exists, never returns None / raises;
  - lang='zh' / unknown lang returns the input unchanged.

Run via:
    python tests/test_band_labels.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from voicemap.report import (  # noqa: E402
    _THRESHOLDS, _THRESHOLDS_LABEL_EN, get_band_label,
)


class TestBandLabels(unittest.TestCase):

    def test_every_zh_label_has_en_translation(self):
        """No metric should regress from full bilingual coverage."""
        zh_labels = set()
        for _metric, bands in _THRESHOLDS.items():
            for _lo, _hi, label, _sev in bands:
                zh_labels.add(label)
        missing = zh_labels - set(_THRESHOLDS_LABEL_EN.keys())
        self.assertFalse(
            missing,
            f"{len(missing)} zh labels lack EN mapping: {sorted(missing)}")

    def test_no_orphan_en_translations(self):
        """Catch translations for labels that no longer exist anywhere
        in `_THRESHOLDS` — keeps the table from drifting into
        unmaintained dead entries."""
        zh_labels = set()
        for _metric, bands in _THRESHOLDS.items():
            for _lo, _hi, label, _sev in bands:
                zh_labels.add(label)
        orphans = set(_THRESHOLDS_LABEL_EN.keys()) - zh_labels
        self.assertFalse(
            orphans,
            f"{len(orphans)} EN entries no longer used: {sorted(orphans)}")

    def test_get_band_label_zh_passthrough(self):
        for zh in _THRESHOLDS_LABEL_EN:
            self.assertEqual(get_band_label(zh, "zh"), zh)
        # Unknown lang behaves like zh (graceful)
        self.assertEqual(get_band_label("正常", "fr"), "正常")
        self.assertEqual(get_band_label("正常", ""), "正常")

    def test_get_band_label_en_translates(self):
        # Sample concrete mappings — guards against accidental edits.
        cases = [
            ("正常",       "normal"),
            ("病理",       "pathological"),
            ("健康",       "healthy"),
            ("接触不足，气声型",  "under-contact, breathy"),
            ("典型嗓音",   "typical voice"),
            ("强烈歌者共振",  "strong singer's formant"),
        ]
        for zh, expected_en in cases:
            self.assertEqual(get_band_label(zh, "en"), expected_en)

    def test_get_band_label_falls_back_when_missing(self):
        """Unmapped zh string returns unchanged (never crashes / returns None)."""
        unknown = "完全不存在的标签 NotInTable"
        self.assertEqual(get_band_label(unknown, "en"), unknown)


class TestThresholdsCoverage(unittest.TestCase):
    """Make sure metrics we added in batch-2 actually shipped."""

    REQUIRED_METRICS = (
        "Crest", "SpecBal", "SpectralFlatness", "AlphaRatio",
        "HammarbergIndex", "DUV", "Entropy", "SPR",
    )

    def test_required_metrics_present(self):
        for m in self.REQUIRED_METRICS:
            self.assertIn(m, _THRESHOLDS,
                f"{m} reference range went missing — DEV_LOG promised it")
            self.assertGreaterEqual(len(_THRESHOLDS[m]), 2,
                f"{m} should have at least 2 bands")


if __name__ == "__main__":
    unittest.main(verbosity=2)
