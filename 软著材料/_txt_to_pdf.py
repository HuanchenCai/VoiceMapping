# -*- coding: utf-8 -*-
"""把分页的 .txt 源代码清单转成 A4 PDF，供软著申请提交。

每张 A4 一页源代码（50 行），等宽字体，底部页码。
"""

import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg
# 字体回退链：Consolas 等宽渲 ASCII / 代码，SimSun / 微软雅黑兜底
# 中文字符（注释里的汉字）。matplotlib >= 3.6 PDF backend 按 glyph
# 逐字符回退，单条 text() 调用混排中英完全没问题。
matplotlib.rcParams["font.family"] = [
    "Consolas",            # ASCII / 代码
    "SimSun",              # 中文兜底（宋体）
    "Microsoft YaHei",     # 中文兜底（雅黑）
    "Segoe UI Symbol",     # Unicode 符号 (ⓘ ⏵ ▶ ◀ ● 等)
    "DejaVu Sans Mono",
]
matplotlib.rcParams["axes.unicode_minus"] = False
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent

LINES_PER_PAGE = 50
PAGE_W_IN, PAGE_H_IN = 8.27, 11.69    # A4 portrait, inches
MARGIN_L, MARGIN_R = 0.55, 0.45       # inches
MARGIN_T, MARGIN_B = 0.55, 0.55
FONT_SIZE = 9                          # pt

# 软著申请抬头（每个 PDF 文件首页之前不另起封面，但每页底部带版本号）
HEADER_TEXT = "嗓音声学品质多维分析图谱（VoiceMap）V1.0.0"


def _split_pages(lines: list) -> list:
    """把扁平文本按 ——— 第 N 页 ——— 标记切片。

    标记行不输出到 PDF（输出的页码用 matplotlib 自己渲染）。
    返回 list[list[str]]：每个子 list = 一页内的 50 行。
    """
    pages = []
    current = []
    for line in lines:
        if line.startswith("——— 第 ") and line.endswith(" 页 ———"):
            if current:
                pages.append(current)
            current = []
            continue
        if line == "END":
            # END marker placed alone after last page; treat as
            # a final standalone page with one line.
            if current:
                pages.append(current)
                current = []
            pages.append(["END"])
            continue
        current.append(line)
    if current:
        pages.append(current)
    return pages


def _render_page(pdf: PdfPages, page_lines: list, page_no: int, total: int):
    fig = plt.figure(figsize=(PAGE_W_IN, PAGE_H_IN))
    # Body text axes: occupies the inner rect after margins.
    body_w = (PAGE_W_IN - MARGIN_L - MARGIN_R) / PAGE_W_IN
    body_h = (PAGE_H_IN - MARGIN_T - MARGIN_B) / PAGE_H_IN
    body_x = MARGIN_L / PAGE_W_IN
    body_y = MARGIN_B / PAGE_H_IN
    ax = fig.add_axes([body_x, body_y, body_w, body_h])
    ax.set_axis_off()

    body = "\n".join(page_lines)
    ax.text(0.0, 1.0, body,
            size=FONT_SIZE,
            va="top", ha="left", linespacing=1.05)

    # Footer：左侧抬头，右侧页码
    fig.text(MARGIN_L / PAGE_W_IN, MARGIN_B * 0.4 / PAGE_H_IN,
             HEADER_TEXT,
             size=7, color="#555555")
    fig.text(1 - MARGIN_R / PAGE_W_IN, MARGIN_B * 0.4 / PAGE_H_IN,
             f"第 {page_no} / {total} 页",
             size=7, color="#555555",
             ha="right")

    pdf.savefig(fig)
    plt.close(fig)


def convert(src: Path, dst: Path) -> None:
    lines = src.read_text(encoding="utf-8").splitlines()
    pages = _split_pages(lines)
    total = len(pages)
    print(f"  {src.name} → {dst.name}: {total} pages")
    with PdfPages(dst) as pdf:
        for i, page_lines in enumerate(pages, start=1):
            _render_page(pdf, page_lines, i, total)


_IMG_RE = re.compile(r"^\s*!\[[^\]]*\]\(([^)]+)\)\s*$")


def _render_image_page(pdf: PdfPages, img_path: Path,
                       page_no: int, total: int) -> None:
    """Render an embedded image as a dedicated A4 page."""
    fig = plt.figure(figsize=(PAGE_W_IN, PAGE_H_IN))
    body_w = (PAGE_W_IN - MARGIN_L - MARGIN_R) / PAGE_W_IN
    body_h = (PAGE_H_IN - MARGIN_T - MARGIN_B) / PAGE_H_IN
    body_x = MARGIN_L / PAGE_W_IN
    body_y = MARGIN_B / PAGE_H_IN
    ax = fig.add_axes([body_x, body_y, body_w, body_h])
    ax.set_axis_off()
    try:
        img = mpimg.imread(str(img_path))
        ax.imshow(img)
    except Exception as e:
        ax.text(0.5, 0.5, f"[图片加载失败: {img_path.name} — {e}]",
                ha="center", va="center", color="red")

    fig.text(MARGIN_L / PAGE_W_IN, MARGIN_B * 0.4 / PAGE_H_IN,
             HEADER_TEXT, size=7, color="#555555")
    fig.text(1 - MARGIN_R / PAGE_W_IN, MARGIN_B * 0.4 / PAGE_H_IN,
             f"第 {page_no} / {total} 页", size=7, color="#555555",
             ha="right")
    pdf.savefig(fig)
    plt.close(fig)


def _split_markdown_into_blocks(lines: list, base_dir: Path) -> list:
    """Walk markdown lines, splitting into a sequence of blocks where
    each block is either:
      - ("text", [50-line page]) — regular text
      - ("image", Path)          — markdown ![](...) line → own page

    Image lines break the current text accumulator so they always
    land on their own dedicated PDF page (previous text page may be
    shorter than 50 lines).
    """
    blocks = []
    buf = []
    for line in lines:
        m = _IMG_RE.match(line)
        if m:
            # Flush any pending text buffer
            for i in range(0, len(buf), LINES_PER_PAGE):
                blocks.append(("text", buf[i:i + LINES_PER_PAGE]))
            buf = []
            blocks.append(("image", (base_dir / m.group(1)).resolve()))
        else:
            buf.append(line)
    for i in range(0, len(buf), LINES_PER_PAGE):
        blocks.append(("text", buf[i:i + LINES_PER_PAGE]))
    return blocks


def convert_markdown(src: Path, dst: Path, title: str) -> None:
    """Render a markdown source as A4 PDF: monospace text, 50 lines/page,
    with `![](path)` image lines materialised as full-page figures.
    """
    text = src.read_text(encoding="utf-8")
    lines = text.splitlines()
    blocks = _split_markdown_into_blocks(lines, src.parent)
    total = len(blocks)
    print(f"  {src.name} → {dst.name}: {total} pages")
    global HEADER_TEXT
    saved = HEADER_TEXT
    HEADER_TEXT = title
    try:
        with PdfPages(dst) as pdf:
            for i, (kind, content) in enumerate(blocks, start=1):
                if kind == "image":
                    _render_image_page(pdf, content, i, total)
                else:
                    _render_page(pdf, content, i, total)
    finally:
        HEADER_TEXT = saved


def main():
    pairs = [
        ("源代码_前30页.txt", "源代码_前30页.pdf"),
        ("源代码_后30页.txt", "源代码_后30页.pdf"),
    ]
    for src_name, dst_name in pairs:
        src = ROOT / src_name
        if not src.exists():
            print(f"  [SKIP] {src_name} not found — run _build_source_listing.py first")
            continue
        convert(src, ROOT / dst_name)

    # 软件说明书 / 设计说明书 同样转 PDF，方便申请系统上传
    docs_dir = ROOT.parent / "docs"
    for md_name, pdf_name, title in (
        ("用户手册.md",     "用户手册.pdf",
         "嗓音声学品质多维分析图谱（VoiceMap）V1.0.0 · 用户手册"),
        ("设计说明书.md",   "设计说明书.pdf",
         "嗓音声学品质多维分析图谱（VoiceMap）V1.0.0 · 设计说明书"),
    ):
        src = docs_dir / md_name
        if not src.exists():
            continue
        convert_markdown(src, ROOT / pdf_name, title)


if __name__ == "__main__":
    main()
