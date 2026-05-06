# -*- coding: utf-8 -*-
"""VoiceMap — 嗓音声学品质多维分析图谱 / Voice Range Profile Analyzer.

The package re-exports only the high-level facade. Calculator classes
and helper functions are intentionally NOT re-exported — import them
from their submodules (``voicemap.metrics``, ``voicemap.plotter`` …)
to keep this surface small and stable.
"""

from voicemap.__version__ import (
    __version__,
    __title_zh__,
    __title_en__,
    __author__,
    __email__,
    __license__,
    __copyright__,
)

from voicemap.config import VoiceMapConfig, DEFAULT_CONFIG
from voicemap.analyzer import VoiceMapAnalyzer

__all__ = [
    "__version__",
    "__title_zh__",
    "__title_en__",
    "__author__",
    "__email__",
    "__license__",
    "__copyright__",
    "VoiceMapAnalyzer",
    "VoiceMapConfig",
    "DEFAULT_CONFIG",
]
