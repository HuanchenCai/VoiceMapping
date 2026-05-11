# -*- coding: utf-8 -*-
"""软著申请 PDF 生成：
- 源代码 .txt → A4 PDF（50 行/页，等宽字体）—— 走 matplotlib
- 用户手册 / 设计说明书 .md → 排版 PDF —— 走 reportlab + mistune
  支持标题、加粗、列表、表格、代码块、行内代码、分隔线、图片。
  PDF 中 Markdown 标记（``** ## - | `` 等）不再以原文出现。
"""

import re
from pathlib import Path

# ── 源代码 .txt → PDF（保持原样：matplotlib monospace 分页） ───────────
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = [
    "Consolas", "SimSun", "Microsoft YaHei", "Segoe UI Symbol",
    "DejaVu Sans Mono",
]
matplotlib.rcParams["axes.unicode_minus"] = False
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt

# ── Markdown → PDF：reportlab + mistune ────────────────────────────────
import mistune
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
    Image, Table, TableStyle, PageBreak, KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.platypus.xpreformatted import XPreformatted

from PIL import Image as PILImage

ROOT = Path(__file__).resolve().parent

# ── 字体注册 ───────────────────────────────────────────────────────────
WIN_FONTS = Path("C:/Windows/Fonts")
_FONT_REG = "ZH"
_FONT_BOLD = "ZHB"
_FONT_MONO = "Mono"
pdfmetrics.registerFont(TTFont(_FONT_REG,  str(WIN_FONTS / "msyh.ttc")))
pdfmetrics.registerFont(TTFont(_FONT_BOLD, str(WIN_FONTS / "msyhbd.ttc")))
pdfmetrics.registerFont(TTFont(_FONT_MONO, str(WIN_FONTS / "consola.ttf")))

# ── 段落 / 标题 / 代码风格 ─────────────────────────────────────────────
ACCENT = "#b8860b"      # 暖色（暗 amber 印在白底）

def _style(name, size, bold=False, leading=None, space_before=0,
           space_after=4, left=0, color="#111111", mono=False,
           align=0, word_wrap="CJK"):
    return ParagraphStyle(
        name=name,
        fontName=(_FONT_MONO if mono else (_FONT_BOLD if bold else _FONT_REG)),
        fontSize=size,
        leading=leading or (size * 1.45),
        spaceBefore=space_before,
        spaceAfter=space_after,
        leftIndent=left,
        textColor=colors.HexColor(color),
        alignment=align,
        wordWrap=word_wrap,
    )

S_H1   = _style("H1",    20, bold=True, space_before=14, space_after=12)
S_H2   = _style("H2",    15, bold=True, space_before=14, space_after=8,
                color=ACCENT)
S_H3   = _style("H3",    12, bold=True, space_before=10, space_after=4)
S_BODY = _style("Body",  10, leading=15)
S_LI   = _style("LI",    10, leading=15, left=14, space_after=2)
S_CODE = _style("Code",   9, mono=True, leading=12, space_after=4,
                word_wrap=None)
S_CELL = _style("Cell",   9, leading=12, space_after=0)
S_CELL_HEAD = _style("CellH", 9, bold=True, leading=12, space_after=0)

PAGE_W, PAGE_H = A4              # ≈ 595 × 842 pt
MARGIN_L = MARGIN_R = 1.8 * cm
MARGIN_T = 1.6 * cm
MARGIN_B = 1.8 * cm
HEADER_TEXT = "嗓音声学品质多维分析图谱（VoiceMap）V1.0.0"


# ─── Mistune 自定义渲染器：返回 reportlab flowables ────────────────────
class _PDFRenderer:
    """Walk mistune AST → list of reportlab Flowable objects."""

    def __init__(self, base_dir: Path):
        self.base = base_dir
        self.flow: list = []

    # ── 入口
    def render(self, ast: list) -> list:
        for node in ast:
            self._dispatch(node)
        return self.flow

    def _dispatch(self, node: dict) -> None:
        t = node.get("type")
        fn = getattr(self, f"_n_{t}", None)
        if fn:
            fn(node)
        # 未识别的节点静默忽略（如 blank_line）

    # ── 行内：返回 HTML-style 字符串（用 reportlab Paragraph 解析）
    def _inline(self, children) -> str:
        out = []
        for c in children or []:
            t = c.get("type")
            if t == "text":
                out.append(self._escape(c.get("raw", c.get("text", ""))))
            elif t == "strong":
                out.append(f"<b>{self._inline(c.get('children'))}</b>")
            elif t == "emphasis":
                out.append(f"<i>{self._inline(c.get('children'))}</i>")
            elif t == "codespan":
                # Consolas 不含 CJK 字形：纯 ASCII 才用等宽，含中文则
                # 回到正文字体 + 暖色 + 9pt 模拟"代码"质感；否则
                # `用户手册.md` 这种里面的"用户手册"会渲染成空白宽度，
                # 导致看上去 ".md" 漂在长空格后面。
                raw = c.get("raw", "")
                font_name = (_FONT_MONO if all(ord(ch) < 128 for ch in raw)
                             else _FONT_REG)
                out.append(
                    f'<font face="{font_name}" size="9" color="#5b3a00">'
                    f'{self._escape(raw)}</font>')
            elif t == "linebreak":
                out.append("<br/>")
            elif t == "softbreak":
                # 中文为主的文档不希望软换行被插一个空格变成
                # "时域波形 在每次..."。直接吃掉换行，ReportLab
                # 自己会按字宽断行。英文文档若因此粘连，作者改
                # 用显式空格即可。
                out.append("")
            elif t == "link":
                text = self._inline(c.get("children"))
                href = c.get("attrs", {}).get("url", "")
                out.append(f'<link href="{self._escape(href)}" color="#1a73e8">{text}</link>')
            elif t == "image":
                # 行内图片极少；标准处理是块级；这里把 alt 文字落下
                out.append(self._inline(c.get("children")))
            else:
                out.append(self._inline(c.get("children")))
        return "".join(out)

    @staticmethod
    def _escape(text: str) -> str:
        return (text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))

    # ── 节点处理
    def _n_heading(self, node):
        level = node.get("attrs", {}).get("level", 1)
        text = self._inline(node.get("children"))
        style = {1: S_H1, 2: S_H2, 3: S_H3}.get(level, S_H3)
        self.flow.append(Paragraph(text, style))

    def _n_paragraph(self, node):
        # 单一段落里若只有一张图，单独走块级图片
        kids = node.get("children", [])
        if len(kids) == 1 and kids[0].get("type") == "image":
            self._render_image_node(kids[0])
            return
        text = self._inline(kids)
        if text.strip():
            self.flow.append(Paragraph(text, S_BODY))

    def _n_block_code(self, node):
        code = node.get("raw", "")
        # Consolas 不含 CJK 字形：把 ASCII 段保留等宽（Consolas），CJK
        # 段回退到 _FONT_REG（雅黑），否则代码块里的中文注释会渲染成
        # 空白，导致 ASCII 之间出现"巨型空格"的视觉错位。
        # Preformatted 接受 XML markup 同时保留换行/空格。
        out: list[str] = []
        buf: list[str] = []
        in_cjk = False

        def _flush():
            if not buf:
                return
            text = self._escape("".join(buf))
            if in_cjk:
                out.append(f'<font face="{_FONT_REG}">{text}</font>')
            else:
                out.append(text)
            buf.clear()

        for ch in code:
            cjk = ord(ch) >= 128
            if cjk != in_cjk:
                _flush()
                in_cjk = cjk
            buf.append(ch)
        _flush()
        # XPreformatted 解析 XML 标记同时保留换行 / 空格
        self.flow.append(XPreformatted("".join(out), S_CODE))

    def _n_block_quote(self, node):
        for child in node.get("children", []):
            self._dispatch(child)

    def _n_thematic_break(self, _node):
        self.flow.append(Spacer(1, 4))
        self.flow.append(HRFlowable(
            width="100%", thickness=0.6, color=colors.HexColor("#999999"),
            spaceBefore=2, spaceAfter=6))

    def _n_list(self, node):
        ordered = node.get("attrs", {}).get("ordered", False)
        idx = 1
        for item in node.get("children", []):
            marker = f"{idx}." if ordered else "•"
            # 项内子节点：可能是 block_text / paragraph，再混 nested list
            text_chunks = []
            sub_lists = []
            for sub in item.get("children", []):
                st = sub.get("type")
                if st in ("block_text", "paragraph"):
                    text_chunks.append(self._inline(sub.get("children")))
                elif st == "list":
                    sub_lists.append(sub)
            joined = " ".join(text_chunks)
            self.flow.append(Paragraph(f"{marker}&nbsp;&nbsp;{joined}", S_LI))
            for sub in sub_lists:
                # 缩进嵌套列表
                saved = S_LI.leftIndent
                S_LI.leftIndent = saved + 18
                self._n_list(sub)
                S_LI.leftIndent = saved
            idx += 1

    def _n_table(self, node):
        # mistune v3 table AST:
        #   table.children = [table_head, table_body]
        #   table_head.children = list of table_cell  (一行 header，
        #     不再外套 table_row —— 这是 mistune 的特殊处理)
        #   table_body.children = list of table_row,
        #     table_row.children = list of table_cell
        rows = []
        styles = []
        for section in node.get("children", []):
            stype = section.get("type")
            if stype == "table_head":
                # 直接把 head 的 cells 作为一行 header
                row_cells = [
                    Paragraph(self._inline(c.get("children")), S_CELL_HEAD)
                    for c in section.get("children", [])
                ]
                if row_cells:
                    rows.append(row_cells)
                    styles.append((
                        "BACKGROUND", (0, len(rows) - 1),
                        (-1, len(rows) - 1),
                        colors.HexColor("#f5f5f5")))
            elif stype == "table_body":
                for row in section.get("children", []):
                    row_cells = [
                        Paragraph(self._inline(c.get("children")), S_CELL)
                        for c in row.get("children", [])
                    ]
                    rows.append(row_cells)

        if not rows:
            return
        n_cols = len(rows[0])
        # 列宽：均分整页可用宽度
        avail = PAGE_W - MARGIN_L - MARGIN_R
        col_widths = [avail / n_cols] * n_cols

        tbl = Table(rows, colWidths=col_widths, repeatRows=1)
        ts = [
            ("FONTNAME", (0, 0), (-1, -1), _FONT_REG),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ] + styles
        tbl.setStyle(TableStyle(ts))
        self.flow.append(Spacer(1, 4))
        self.flow.append(tbl)
        self.flow.append(Spacer(1, 6))

    def _render_image_node(self, node):
        import urllib.parse
        url = node.get("attrs", {}).get("url", "")
        # mistune 把中文路径 URL-encode 了，反编码回来
        url = urllib.parse.unquote(url)
        path = (self.base / url).resolve()
        if not path.exists():
            self.flow.append(Paragraph(
                f"[图片缺失: {url}]", S_BODY))
            return
        # 通过 PIL 取真实像素尺寸 → 算 PDF 显示尺寸（按页宽 fit）
        with PILImage.open(path) as im:
            iw, ih = im.size
        avail_w = PAGE_W - MARGIN_L - MARGIN_R
        # 限高：不超过单页 70%，避免单张图把整页占爆又因 footer 溢出
        avail_h = (PAGE_H - MARGIN_T - MARGIN_B) * 0.78
        scale = min(avail_w / iw, avail_h / ih)
        w = iw * scale
        h = ih * scale
        img = Image(str(path), width=w, height=h)
        img.hAlign = "CENTER"
        # alt 文字（如果有）作为图注
        alt = "".join(c.get("raw", c.get("text", ""))
                       for c in node.get("children") or [])
        caption_parts = [Spacer(1, 6), img]
        if alt:
            caption = Paragraph(
                f'<font color="#666666" size="9">图：{self._escape(alt)}</font>',
                _style("Cap", 9, color="#666666", align=1))
            caption_parts.append(caption)
        caption_parts.append(Spacer(1, 6))
        # 整组保留在一页内
        self.flow.append(KeepTogether(caption_parts))


# ─── 页眉 / 页脚回调 ───────────────────────────────────────────────────
def _make_page_decorator(title: str):
    def _decorate(canvas, doc):
        canvas.saveState()
        canvas.setFont(_FONT_REG, 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        # 页脚左：抬头；右：第 X / Y 页
        y_foot = MARGIN_B * 0.45
        canvas.drawString(MARGIN_L, y_foot, title)
        canvas.drawRightString(
            PAGE_W - MARGIN_R, y_foot,
            f"第 {doc.page} 页")
        canvas.restoreState()
    return _decorate


# ─── 主 .md → PDF 入口 ─────────────────────────────────────────────────
def convert_markdown(src: Path, dst: Path, title: str) -> None:
    text = src.read_text(encoding="utf-8")
    # plugins=['table'] 让 GFM 风格的 | a | b | 表格被识别为 table 节点，
    # 否则 mistune 默认只把它当 paragraph 文本。
    md = mistune.create_markdown(renderer=None, plugins=["table"])
    ast = md(text)

    flow = _PDFRenderer(src.parent).render(ast)

    doc = BaseDocTemplate(
        str(dst), pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title=title)
    frame = Frame(MARGIN_L, MARGIN_B,
                  PAGE_W - MARGIN_L - MARGIN_R,
                  PAGE_H - MARGIN_T - MARGIN_B,
                  showBoundary=0)
    doc.addPageTemplates([PageTemplate(
        id="main", frames=[frame],
        onPage=_make_page_decorator(title))])

    doc.build(flow)
    # ReportLab 不在构建过程中给页数；事后估算页数
    try:
        import pypdf
        n_pages = len(pypdf.PdfReader(str(dst)).pages)
        print(f"  {src.name} → {dst.name}: {n_pages} pages")
    except ImportError:
        print(f"  {src.name} → {dst.name}: ok")


# ─── 源代码 .txt → PDF（保持 matplotlib 实现）──────────────────────────
LINES_PER_PAGE = 50
PAGE_W_IN, PAGE_H_IN = 8.27, 11.69
MAT_MARGIN_L, MAT_MARGIN_R = 0.55, 0.45
MAT_MARGIN_T, MAT_MARGIN_B = 0.55, 0.55
MAT_FONT_SIZE = 9


def _mat_split_pages(lines: list) -> list:
    pages, current = [], []
    for line in lines:
        if line.startswith("——— 第 ") and line.endswith(" 页 ———"):
            if current:
                pages.append(current)
            current = []
            continue
        if line == "END":
            if current:
                pages.append(current)
                current = []
            pages.append(["END"])
            continue
        current.append(line)
    if current:
        pages.append(current)
    return pages


def _mat_render_page(pdf: PdfPages, page_lines: list,
                     page_no: int, total: int, header: str):
    fig = plt.figure(figsize=(PAGE_W_IN, PAGE_H_IN))
    body_w = (PAGE_W_IN - MAT_MARGIN_L - MAT_MARGIN_R) / PAGE_W_IN
    body_h = (PAGE_H_IN - MAT_MARGIN_T - MAT_MARGIN_B) / PAGE_H_IN
    body_x = MAT_MARGIN_L / PAGE_W_IN
    body_y = MAT_MARGIN_B / PAGE_H_IN
    ax = fig.add_axes([body_x, body_y, body_w, body_h])
    ax.set_axis_off()
    ax.text(0.0, 1.0, "\n".join(page_lines),
            size=MAT_FONT_SIZE, va="top", ha="left", linespacing=1.05)
    fig.text(body_x, MAT_MARGIN_B * 0.4 / PAGE_H_IN,
             header, size=7, color="#555555")
    fig.text(1 - MAT_MARGIN_R / PAGE_W_IN,
             MAT_MARGIN_B * 0.4 / PAGE_H_IN,
             f"第 {page_no} / {total} 页", size=7, color="#555555",
             ha="right")
    pdf.savefig(fig)
    plt.close(fig)


def convert_source_listing(src: Path, dst: Path) -> None:
    lines = src.read_text(encoding="utf-8").splitlines()
    pages = _mat_split_pages(lines)
    total = len(pages)
    print(f"  {src.name} → {dst.name}: {total} pages")
    with PdfPages(dst) as pdf:
        for i, page_lines in enumerate(pages, start=1):
            _mat_render_page(pdf, page_lines, i, total, HEADER_TEXT)


def main():
    # 源代码 .txt → PDF
    for src_name, dst_name in (
        ("源代码_前30页.txt", "源代码_前30页.pdf"),
        ("源代码_后30页.txt", "源代码_后30页.pdf"),
    ):
        src = ROOT / src_name
        if not src.exists():
            print(f"  [SKIP] {src_name} not found")
            continue
        convert_source_listing(src, ROOT / dst_name)

    # 用户手册 / 设计说明书 .md → 排版 PDF
    docs_dir = ROOT.parent / "docs"
    for md_name, pdf_name, title in (
        ("用户手册.md",   "用户手册.pdf",
         "VoiceMap V1.0.0 · 用户手册"),
        ("设计说明书.md", "设计说明书.pdf",
         "VoiceMap V1.0.0 · 设计说明书"),
    ):
        src = docs_dir / md_name
        if not src.exists():
            continue
        convert_markdown(src, ROOT / pdf_name, title)


if __name__ == "__main__":
    main()
