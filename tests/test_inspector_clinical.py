# -*- coding: utf-8 -*-
"""End-to-end smoke test for `_inspector_set_clinical`.

For every metric that has a `_THRESHOLDS` entry, instantiate VoiceMapApp,
populate the clinical-bands area, and verify:
  - the call doesn't raise
  - one Label is rendered for the section heading + one Frame per band
  - in zh mode each band label string matches the threshold zh text
  - in en mode each band label is translated via _THRESHOLDS_LABEL_EN

Skips cleanly when Tk fails to init (headless CI).

Run via:
    python tests/test_inspector_clinical.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from voicemap.report import _THRESHOLDS, get_band_label  # noqa: E402


class TestInspectorClinical(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            from voicemap.gui import VoiceMapApp
            cls.app = VoiceMapApp()
            cls.app.update_idletasks()
        except Exception as e:  # noqa: BLE001
            raise unittest.SkipTest(f"Tk init failed: {e}")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:  # noqa: BLE001
            pass

    def test_all_metrics_render_without_error(self):
        """Every _THRESHOLDS entry must render cleanly. Caught us once
        when a band tuple was 3 elements instead of 4."""
        for name, bands in _THRESHOLDS.items():
            with self.subTest(metric=name):
                self.app._inspector_set_clinical(bands)
                self.app.update_idletasks()
                # heading Label + one Frame per band
                kids = self.app._inspector_cards.winfo_children()
                self.assertEqual(
                    len(kids), 1 + len(bands),
                    f"{name}: expected {1 + len(bands)} children "
                    f"(heading + {len(bands)} bands), got {len(kids)}")

    def test_zh_mode_renders_zh_labels(self):
        from voicemap.i18n import set_language
        set_language("zh")
        # VibratoExtent has 4 distinctive labels — sample one
        self.app._inspector_set_clinical(_THRESHOLDS["VibratoExtent"])
        self.app.update_idletasks()
        rows = [c for c in self.app._inspector_cards.winfo_children()
                if c.winfo_class() == "Frame"]
        labels = []
        for r in rows:
            for child in r.winfo_children():
                if child.cget("font") and "Microsoft YaHei UI" in str(child.cget("font")):
                    labels.append(child.cget("text"))
        # Expect: 颤音弱 / 颤音中等 / 颤音明显 / 颤音偏宽
        self.assertIn("颤音弱", labels)
        self.assertIn("颤音明显", labels)

    def test_en_mode_renders_translated_labels(self):
        from voicemap.i18n import set_language
        set_language("en")
        self.app._inspector_set_clinical(_THRESHOLDS["VibratoExtent"])
        self.app.update_idletasks()
        rows = [c for c in self.app._inspector_cards.winfo_children()
                if c.winfo_class() == "Frame"]
        labels = []
        for r in rows:
            for child in r.winfo_children():
                if child.cget("font") and "Microsoft YaHei UI" in str(child.cget("font")):
                    labels.append(child.cget("text"))
        # Expect: weak / moderate / strong / wide
        self.assertIn("weak vibrato", labels)
        self.assertIn("strong vibrato", labels)
        # Restore zh for downstream tests
        set_language("zh")

    def test_clearing_with_none(self):
        # No bands → heading should NOT render either
        self.app._inspector_set_clinical(None)
        self.app.update_idletasks()
        self.assertEqual(
            len(self.app._inspector_cards.winfo_children()), 0,
            "passing None should clear all clinical band widgets")


if __name__ == "__main__":
    unittest.main(verbosity=2)
