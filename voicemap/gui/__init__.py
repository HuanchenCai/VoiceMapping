# -*- coding: utf-8 -*-
"""VoiceMap GUI subpackage.

Re-exports the entry points used by ``voicemap.cli`` so callers can
``from voicemap.gui import main`` without depending on the internal
module layout.
"""

from voicemap.gui.app import VoiceMapApp, main

__all__ = ["VoiceMapApp", "main"]
