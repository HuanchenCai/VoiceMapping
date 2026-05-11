# -*- coding: utf-8 -*-
"""Screenshot helper：抓取 VoiceMap 主窗口并裁剪保存。

Usage:
    python _capture_window.py <output_filename>

会自动找标题含 "嗓音" 或 "VoiceMap" 的窗口，crop 截图保存到
docs/screenshots/<output_filename>。
"""

import sys
from pathlib import Path

from PIL import ImageGrab
import win32gui

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def find_voicemap_hwnd():
    target = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if "嗓音" in title or title.startswith("VoiceMap"):
            target.append((hwnd, title))

    win32gui.EnumWindows(callback, None)
    if not target:
        raise RuntimeError("VoiceMap window not found")
    return target[0]


def main():
    if len(sys.argv) != 2:
        print("usage: _capture_window.py <output_filename>")
        sys.exit(1)
    name = sys.argv[1]
    hwnd, title = find_voicemap_hwnd()
    rect = win32gui.GetWindowRect(hwnd)
    # Trim Windows 11 shadow padding (~7 px on left/right/bottom on Win11)
    pad = 7
    bbox = (rect[0] + pad, rect[1], rect[2] - pad, rect[3] - pad)
    img = ImageGrab.grab(bbox=bbox, all_screens=False)
    dst = OUT_DIR / name
    img.save(dst)
    print(f"  wrote {dst.relative_to(ROOT)} ({img.size[0]}×{img.size[1]})  '{title}'")


if __name__ == "__main__":
    main()
