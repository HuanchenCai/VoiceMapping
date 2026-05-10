# -*- coding: utf-8 -*-
"""Build the 软著申请 source-code listing.

Produces three artifacts under 软著材料/:
  * 源代码_全集.txt     —— 完整源码 concat（备查）
  * 源代码_前30页.txt   —— 前 1500 行
  * 源代码_后30页.txt   —— 后 1500 行

Lines/page = 50（中国版权保护中心要求 60 页时常用规格）。
File banners 把每个模块开头标记清楚，方便审核员定位。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 阅读顺序：从基础设施 → 计算 → 编排 → 输出 → GUI
ORDER = [
    "voicemap/__init__.py",
    "voicemap/__version__.py",
    "voicemap/config.py",
    "voicemap/logger.py",
    "voicemap/i18n.py",
    "voicemap/metrics_registry.py",
    "voicemap/metrics.py",
    "voicemap/analyzer.py",
    "voicemap/csv_writer.py",
    "voicemap/excel_export.py",
    "voicemap/report.py",
    "voicemap/plotter.py",
    "voicemap/plot_overlay.py",
    "voicemap/cli.py",
    "voicemap/gui/__init__.py",
    "voicemap/gui/theme.py",
    "voicemap/gui/widgets.py",
    "voicemap/gui/modern_menu.py",
    "voicemap/gui/dialogs.py",
    "voicemap/gui/app.py",
    "main.py",
]

LINES_PER_PAGE = 50
PAGES = 30

OUT_DIR = ROOT / "软著材料"
OUT_DIR.mkdir(exist_ok=True)


def banner(rel_path: str) -> str:
    """File header line shown at the start of each module."""
    line = f"#  {rel_path}  "
    return "# " + "=" * 76 + "\n" + line + "\n" + "# " + "=" * 76


def build_concat() -> list:
    """Return list[str] of all source lines in ORDER."""
    out = []
    for rel in ORDER:
        full = ROOT / rel
        if not full.exists():
            print(f"  [WARN] missing: {rel}")
            continue
        out.append(banner(rel))
        for line in full.read_text(encoding="utf-8").splitlines():
            out.append(line.rstrip())
    return out


def write_paginated(lines, dst: Path, take_first: int | None = None,
                    take_last: int | None = None):
    """Slice + paginate + page-header decoration."""
    if take_first is not None:
        sliced = lines[:take_first]
    elif take_last is not None:
        sliced = lines[-take_last:]
    else:
        sliced = lines

    rendered = []
    for page_no in range(PAGES if (take_first or take_last) else
                         (len(sliced) + LINES_PER_PAGE - 1) // LINES_PER_PAGE):
        start = page_no * LINES_PER_PAGE
        end = start + LINES_PER_PAGE
        chunk = sliced[start:end]
        if not chunk:
            break
        if page_no > 0:
            rendered.append("")    # blank line between pages
        rendered.append(f"——— 第 {page_no + 1} 页 ———")
        rendered.extend(chunk)

    dst.write_text("\n".join(rendered) + "\n", encoding="utf-8")
    print(f"  wrote {dst.name}: {len(rendered)} lines")


def main():
    print("Building source listing from", ROOT)
    all_lines = build_concat()
    print(f"  total: {len(all_lines)} lines from {len(ORDER)} files")

    write_paginated(all_lines, OUT_DIR / "源代码_全集.txt")
    write_paginated(all_lines, OUT_DIR / "源代码_前30页.txt",
                    take_first=LINES_PER_PAGE * PAGES)
    write_paginated(all_lines, OUT_DIR / "源代码_后30页.txt",
                    take_last=LINES_PER_PAGE * PAGES)


if __name__ == "__main__":
    main()
