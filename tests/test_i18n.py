# -*- coding: utf-8 -*-
"""Smoke / regression tests for voicemap.i18n.

Goal: catch missing translations / asymmetric dicts / format-string
breakage early. Run via:
    python tests/test_i18n.py
or as part of pytest auto-discovery.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from voicemap.i18n import STRINGS, tr, set_language, get_language  # noqa: E402


class TestI18n(unittest.TestCase):

    def test_strings_dict_has_zh_and_en(self):
        self.assertIn("zh", STRINGS)
        self.assertIn("en", STRINGS)

    def test_zh_and_en_keys_match(self):
        zh = set(STRINGS["zh"].keys())
        en = set(STRINGS["en"].keys())
        missing_en = zh - en
        missing_zh = en - zh
        self.assertEqual(
            (missing_en, missing_zh), (set(), set()),
            f"asymmetric translation dicts:\n"
            f"  missing in en: {sorted(missing_en)}\n"
            f"  missing in zh: {sorted(missing_zh)}")

    def test_no_empty_translations(self):
        for lang, table in STRINGS.items():
            for key, value in table.items():
                self.assertTrue(
                    value, f"empty translation for {lang}/{key}")

    def test_tr_falls_back_for_unknown_key(self):
        # tr() should return the key itself when it's not in either dict
        # (visible enough that we'll catch missing translations on screen).
        self.assertEqual(tr("__definitely_missing_key__"),
                         "__definitely_missing_key__")

    def test_set_language_round_trip(self):
        prev = get_language()
        try:
            set_language("en")
            self.assertEqual(get_language(), "en")
            self.assertEqual(tr("menu.file"), "File")
            set_language("zh")
            self.assertEqual(get_language(), "zh")
            self.assertEqual(tr("menu.file"), "文件")
        finally:
            set_language(prev)

    def test_format_kwargs(self):
        # status.done has a {n} placeholder — make sure it renders.
        set_language("en")
        try:
            out = tr("status.done", n="12,525")
            self.assertEqual(out, "Done · 12,525 points")
        finally:
            set_language("zh")

    def test_log_message_kwargs_resolve(self):
        # Spot-check several format-string keys to make sure their
        # placeholders match between zh and en.
        keys_to_check = [
            ("log.no_file",          {"path": "x"}),
            ("log.centroid_loaded",  {"name": "x", "k": 5}),
            ("log.train_done",       {"n": 3, "file": "x"}),
            ("statusbar.file_meta",  {"name": "x", "n": 1, "dt": 1.0}),
            ("statusbar.copyright",  {"ver": "1.0.0"}),
            ("inspector.unit",       {}),     # not formatted
        ]
        for key, kw in keys_to_check:
            for lang in ("zh", "en"):
                set_language(lang)
                try:
                    out = tr(key, **kw)
                except KeyError as e:
                    self.fail(f"{lang}/{key}: missing format placeholder {e}")
                self.assertNotIn("{", out, f"{lang}/{key}: unresolved {{}}")
        set_language("zh")


if __name__ == "__main__":
    unittest.main(verbosity=2)
