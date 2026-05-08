# -*- coding: utf-8 -*-
"""Regression tests for the metric description / tooltip i18n contract.

Three layers:
  1. metrics_registry.REGISTRY — MetricSpec.description (English literal,
     baked into the spec)
  2. i18n: metric.desc.<NAME> — short blurb shown in Inspector card
  3. i18n: metric.tooltip.<NAME> — long detailed prose shown on hover

Inspector first looks up tooltip → falls back to desc → falls back to
spec.description. We must guarantee:
  - every registry-listed metric has a metric.desc.<NAME> entry in
    BOTH zh and en (otherwise zh users see English when no key exists);
  - every metric.desc.<NAME> exists in zh ⇔ exists in en (no asymmetry);
  - every metric.tooltip.<NAME> exists in zh ⇔ exists in en;
  - description prose is formula-free (per user spec — formulas live
    in tooltips only).

Run via:
    python tests/test_metric_descriptions.py
"""

import os
import sys
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from voicemap.metrics_registry import REGISTRY  # noqa: E402
from voicemap.i18n import STRINGS  # noqa: E402


class TestMetricDescriptions(unittest.TestCase):

    def test_every_registered_metric_has_zh_desc(self):
        zh = STRINGS["zh"]
        missing = []
        for name in REGISTRY:
            if f"metric.desc.{name}" not in zh:
                missing.append(name)
        self.assertEqual(
            missing, [],
            f"{len(missing)} registered metrics lack metric.desc.<NAME> "
            f"in zh: {missing[:10]}")

    def test_every_registered_metric_has_en_desc(self):
        en = STRINGS["en"]
        missing = []
        for name in REGISTRY:
            if f"metric.desc.{name}" not in en:
                missing.append(name)
        self.assertEqual(
            missing, [],
            f"{len(missing)} registered metrics lack metric.desc.<NAME> "
            f"in en: {missing[:10]}")

    def test_desc_zh_en_symmetric(self):
        zh_keys = {k for k in STRINGS["zh"] if k.startswith("metric.desc.")}
        en_keys = {k for k in STRINGS["en"] if k.startswith("metric.desc.")}
        missing_en = zh_keys - en_keys
        missing_zh = en_keys - zh_keys
        self.assertEqual(
            (missing_en, missing_zh), (set(), set()),
            f"desc i18n asymmetry — zh missing en: {sorted(missing_en)}; "
            f"en missing zh: {sorted(missing_zh)}")

    def test_tooltip_zh_en_symmetric(self):
        zh_keys = {k for k in STRINGS["zh"] if k.startswith("metric.tooltip.")}
        en_keys = {k for k in STRINGS["en"] if k.startswith("metric.tooltip.")}
        missing_en = zh_keys - en_keys
        missing_zh = en_keys - zh_keys
        self.assertEqual(
            (missing_en, missing_zh), (set(), set()),
            f"tooltip i18n asymmetry — zh missing en: {sorted(missing_en)}; "
            f"en missing zh: {sorted(missing_zh)}")

    # User spec: descriptions are formula-free; only tooltips include math.
    # Heuristic: flag descriptions that contain summation Σ, log10/log2,
    # or arithmetic equality/division forms ('= mean(', '/ mean(', etc).
    _FORMULA_PATTERNS = (
        re.compile(r"\bΣ\b"),
        re.compile(r"\blog10\b|\blog2\b"),
        re.compile(r"·log\d"),
        re.compile(r"\bGCI\b|\bGOI\b"),       # acronym dump = formula leak
        re.compile(r"\barg\(z\)"),
    )

    def test_descriptions_are_formula_free(self):
        offenders = []
        for k, v in STRINGS["zh"].items():
            if not k.startswith("metric.desc."):
                continue
            for pat in self._FORMULA_PATTERNS:
                if pat.search(v):
                    offenders.append((k, pat.pattern, v[:60]))
                    break
        self.assertEqual(
            offenders, [],
            f"{len(offenders)} zh descriptions still contain formula tokens "
            f"(formulas belong in metric.tooltip.X, not metric.desc.X): "
            f"{offenders[:5]}")

    def test_tooltip_keys_have_corresponding_desc(self):
        """Every tooltip MUST have a desc — Inspector falls back to desc
        when tooltip is missing, but a tooltip without desc is broken
        navigation (the popover shows but the card stays empty)."""
        zh = STRINGS["zh"]
        offenders = []
        for k in zh:
            if not k.startswith("metric.tooltip."):
                continue
            name = k[len("metric.tooltip."):]
            if f"metric.desc.{name}" not in zh:
                offenders.append(name)
        self.assertEqual(
            offenders, [],
            f"{len(offenders)} tooltips lack a sibling desc: {offenders}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
