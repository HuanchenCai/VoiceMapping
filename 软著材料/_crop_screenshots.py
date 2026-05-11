# -*- coding: utf-8 -*-
"""按功能给截图做精确裁切，让用户手册 PDF 里每张图只突出对应特性。

裁切框（left, top, right, bottom）以原图像素为准。运行后**覆盖**
docs/screenshots/ 下原文件。重跑安全 —— 用户重新截图后再跑即可。

如需调试单张图，在 main() 里临时改 SAVE_BACKUP=True 会把裁切前
副本存到 _crop_backup/。
"""

from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"

# 每张图的裁切框（基于实测 1604×1227 / 1602×1227 / 1902×947）
# 缺省的 (0, 0, W, H) 表示不动整张
CROPS = {
    # 1. 概览：留下完整界面框架（菜单+录音轨+参数轨+画布+详情栏+状态栏），
    #     去掉无关 Windows 标题阴影边
    "1初始打开软件.png":  (0,   0, 1602, 1227),
    # 2. 录音轨：把焦点放到 Tracks Panel + 参数轨 那两条，
    #     底下空画布省了
    "2打开文件.png":      (0,   0, 1604,  330),
    # 3. 分析进行中：聚焦中央进度对话框 + 周围少量画布作上下文
    "3分析进行中.png":    (530, 480, 1130, 880),
    # 4. 鼠标悬浮：保留整张图（热图 + 浮动数值 + 详情栏）
    "4鼠标悬浮.png":      (0,   0, 1604, 1180),
    # 5. 标注：聚焦画布 + 标注弹窗（去掉空白详情栏右半 + 状态栏）
    "5标注功能.png":      (0,  280, 1200, 1180),
    # 6. 拟合曲线：聚焦画布上的曲线，去掉空详情栏 + 状态栏
    "6拟合曲线.png":      (0,  280, 1200, 1180),
    # 7. 日志面板：聚焦日志窗口
    "7日志面板.png":      (480, 360, 1220, 1050),
    # 8. 对比对话框：原图就是对话框本身，不动
    "8比较两段录音.png":  (0,    0, 1902,  947),
}


def main(save_backup: bool = True) -> None:
    """裁切前自动把原图入 `_original/`，可重跑且不丢原始素材。"""
    bak = SHOTS / "_original"
    if save_backup:
        bak.mkdir(exist_ok=True)
    for name, box in CROPS.items():
        path = SHOTS / name
        if not path.exists():
            print(f"  [SKIP] {name} not found")
            continue
        if save_backup:
            orig = bak / name
            # 只在备份不存在或大小不同（说明仍是裁切版）时写入
            if not orig.exists():
                orig.write_bytes(path.read_bytes())
        with Image.open(path) as im:
            left, top, right, bottom = box
            right = min(right, im.size[0])
            bottom = min(bottom, im.size[1])
            cropped = im.crop((left, top, right, bottom))
        cropped.save(path)
        print(f"  cropped {name} → {cropped.size[0]}×{cropped.size[1]}")


if __name__ == "__main__":
    main()
