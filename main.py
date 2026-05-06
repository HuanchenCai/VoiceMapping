#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thin entry point shim. Real CLI/GUI code lives in voicemap.cli.

Exists so the user can keep typing ``python main.py [...]`` without
caring about the package layout. Ensures the project root is on
sys.path so absolute imports `from voicemap.X import Y` work
regardless of cwd.
"""
import sys
from pathlib import Path

# Project root (this file's directory) must be on sys.path so the
# `voicemap` package can be imported. Insert at index 0 so any
# accidentally-installed copy of voicemap is shadowed by the local one.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from voicemap.cli import main

if __name__ == "__main__":
    main()
