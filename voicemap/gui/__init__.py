# -*- coding: utf-8 -*-
"""VoiceMap GUI subpackage.

Re-exports the entry points used by ``voicemap.cli`` so existing callers
``from voicemap.gui import main`` keep working transparently across the
A0-2 split.
"""

from voicemap.gui.app import VoiceMapApp, main

__all__ = ["VoiceMapApp", "main"]
