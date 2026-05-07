# -*- coding: utf-8 -*-
"""Smoke tests for TrackEntry + Tracks Panel state.

Imports VoiceMapApp to verify the multi-file workflow plumbing
(append / set-active / cached state) without spinning up a full
analysis. Run via:
    python tests/test_tracks.py
"""

import os
import sys
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# Skip cleanly when no audio sample is present (CI without test fixture)
SAMPLE = Path(ROOT) / "audio" / "test_Voice_EGG.wav"


@unittest.skipUnless(SAMPLE.exists(), f"sample WAV missing at {SAMPLE}")
class TestTrackEntry(unittest.TestCase):

    def test_track_entry_reads_wav_header(self):
        from voicemap.gui.app import TrackEntry
        e = TrackEntry(SAMPLE)
        # test_Voice_EGG.wav is 44.1 kHz stereo
        self.assertEqual(e.sr, 44100)
        self.assertEqual(e.channels, 2)
        self.assertGreater(e.duration, 1.0, "duration should be > 1s")
        self.assertEqual(e.state, "queued")
        self.assertIsNone(e.df)
        self.assertEqual(e.cells, 0)

    def test_waveform_amps_returns_normalised_array(self):
        """Replaced the old Unicode-block sketch with a tk.Canvas
        bar chart driven by `_track_waveform_amps`. The amps array is
        normalised to [0, 1] and the cache is a (n_buckets, amps) tuple."""
        import numpy as np
        from voicemap.gui.app import TrackEntry, VoiceMapApp
        e = TrackEntry(SAMPLE)
        amps = VoiceMapApp._track_waveform_amps(e, n_buckets=64)
        self.assertIsNotNone(amps)
        self.assertEqual(len(amps), 64)
        self.assertGreaterEqual(amps.min(), 0.0)
        self.assertLessEqual(amps.max(), 1.0)
        # Cached on second call (tuple keyed by n_buckets)
        amps2 = VoiceMapApp._track_waveform_amps(e, n_buckets=64)
        self.assertTrue(np.array_equal(amps, amps2))
        self.assertEqual(e._waveform_cache[0], 64)
        self.assertTrue(np.array_equal(e._waveform_cache[1], amps))


@unittest.skipUnless(SAMPLE.exists(), f"sample WAV missing at {SAMPLE}")
class TestTracksPanel(unittest.TestCase):
    """Need a real Tk app to test the Tracks Panel state machine.
    Skip if Tk fails to init (e.g. headless CI without xvfb)."""

    @classmethod
    def setUpClass(cls):
        try:
            from voicemap.gui import VoiceMapApp
            cls.app = VoiceMapApp()
            cls.app.update_idletasks()
        except Exception as e:
            raise unittest.SkipTest(f"Tk init failed: {e}")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass

    def test_empty_state_shows_drop_zone(self):
        self.assertEqual(self.app._active_track, -1)
        self.assertEqual(self.app._tracks, [])
        self.assertTrue(bool(self.app.drop_zone.winfo_manager()))

    def test_add_track_swaps_to_list_view(self):
        idx = self.app._tracks_add(SAMPLE)
        self.assertEqual(idx, 0)
        self.assertEqual(len(self.app._tracks), 1)
        # drop zone hidden, list frame shown
        self.app.update_idletasks()
        self.assertFalse(bool(self.app.drop_zone.winfo_manager()))
        self.assertIsNotNone(self.app._tracks_list_frame)
        self.assertEqual(len(self.app._track_row_widgets), 1)
        # Cleanup so other tests start fresh
        self.app._tracks.clear()
        self.app._active_track = -1
        self.app._tracks_render()


if __name__ == "__main__":
    unittest.main(verbosity=2)
