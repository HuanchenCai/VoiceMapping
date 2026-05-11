# -*- coding: utf-8 -*-
"""自动剪掉截图四周的深色 / 单色窗口边框，让图嵌入 PDF 后干净。

判定: 从外向内逐行扫描，遇到"标准差很小且亮度低"的整行 / 整列
就当作边框剥掉。背景大多是白底 (255) 或深灰 (0-30)，正常内容
方差大，因此 std < 20 + mean < 80 是"纯深色边框"信号。
"""

from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"


def _is_border_row(row, dark_threshold: int = 80,
                   std_threshold: int = 20) -> bool:
    mean = row.mean()
    std = row.std()
    # 纯深色 = 既暗又一致
    return mean < dark_threshold and std < std_threshold


def trim(im: Image.Image) -> Image.Image:
    arr = np.array(im.convert("RGB"))
    h, w = arr.shape[:2]
    # 从四个方向向内推进
    top = 0
    while top < h and _is_border_row(arr[top]):
        top += 1
    bot = h
    while bot > top and _is_border_row(arr[bot - 1]):
        bot -= 1
    left = 0
    while left < w and _is_border_row(arr[top:bot, left]):
        left += 1
    right = w
    while right > left and _is_border_row(arr[top:bot, right - 1]):
        right -= 1
    return im.crop((left, top, right, bot))


def main() -> None:
    for p in sorted(SHOTS.glob("*")):
        if p.suffix.lower() not in (".png", ".jpeg", ".jpg"):
            continue
        with Image.open(p) as im:
            w0, h0 = im.size
            cropped = trim(im)
        if cropped.size != (w0, h0):
            cropped.save(p)
            print(f"  trimmed {p.name}: {w0}×{h0} → {cropped.size[0]}×{cropped.size[1]}")
        else:
            print(f"  {p.name}: no border")


if __name__ == "__main__":
    main()
