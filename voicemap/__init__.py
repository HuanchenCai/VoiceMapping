#!/usr/bin/env python3
"""
VoiceMap Python Package
Voice Range Profile Analysis Tool
"""

__version__ = "1.0.0"
__author__ = "VoiceMap Python Implementation"
__email__ = "contact@voicemap.org"

from .analyzer import VoiceMapAnalyzer
from .config import VoiceMapConfig, DEFAULT_CONFIG
from .metrics import (
    SPLCalculator, ClarityCalculator, CPPCalculator, SpecBalCalculator,
    CrestCalculator, QcontactCalculator, EntropyCalculator, HRFCalculator
)

__all__ = [
    "VoiceMapAnalyzer",
    "VoiceMapConfig", 
    "DEFAULT_CONFIG",
    "SPLCalculator",
    "ClarityCalculator", 
    "CPPCalculator",
    "SpecBalCalculator",
    "CrestCalculator",
    "QcontactCalculator",
    "EntropyCalculator",
    "HRFCalculator"
]
