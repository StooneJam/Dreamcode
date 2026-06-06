"""Markdown → PDF 渲染工具。

渲染链：weasyprint（Linux/Mac）→ ReportLab 直出（Windows 主路径）。
中文：UnicodeCIDFont STSong-Light（宋体），英文/数字：Times-Roman/Times-Bold。
不经过 xhtml2pdf（WinAnsiEncoding 导致 CJK 白色方框）。
"""
from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from langchain_core.tools import tool

_OUTPUT_DIR = Path("output")


@tool
def render_pdf(markdown_content: str, target_product: str) -> str:
    """将完整的 Markdown 报告转换为 PDF 文件。

    在报告全部写完后调用一次，不要按章节分段调用。

    Args:
        markdown_content: 完整的报告 Markdown 文本。
        target_product: 目标产品名称，用于构建输出文件名。

    Returns:
        生成的 PDF 文件的完整路径。
    """
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # uuid 后缀：同产品多份报告不互相覆盖（路径不可猜）
    pdf_path = _OUTPUT_DIR / f"report_{target_product}_{uuid4().hex[:8]}.pdf"
    if not _try_weasyprint(markdown_content, pdf_path):
        _reportlab_pdf(markdown_content, pdf_path)
    return str(pdf_path)


# ---------------------------------------------------------------------------
# WeasyPrint 路径（Linux/Mac）
# ---------------------------------------------------------------------------

def _try_weasyprint(md: str, output_path: Path) -> bool:
    try:
        import weasyprint
        from markdown_it import MarkdownIt
        body = MarkdownIt().enable("table").render(md)
        html = (
            '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/><style>'
            'body{font-family:"Noto Sans CJK SC","Noto Serif CJK SC","Microsoft YaHei","SimHei",sans-serif;font-size:11pt;'
            'line-height:1.75;margin:48px 56px;}'
            'h1{font-size:18pt;border-bottom:2px solid #2E86AB;padding-bottom:6px;}'
            'h2{font-size:14pt;border-left:4px solid #2E86AB;padding-left:10px;margin-top:24px;}'
            'h3{font-size:12pt;margin-top:14px;}'
            'h4{font-size:11pt;margin-top:10px;font-weight:bold;color:#333;}'
            'img{max-width:100%;display:block;margin:12px 0;}'
            'table{border-collapse:collapse;width:100%;margin:12px 0;}'
            'th{background:#2E86AB;color:white;padding:6px 10px;text-align:left;font-size:10pt;}'
            'td{padding:6px 10px;border:1px solid #ddd;font-size:10pt;}'
            'tr:nth-child(even) td{background:#F2F7FA;}'
            'sup{font-size:8pt;color:#2E86AB;}'
            f'</style></head><body>{body}</body></html>'
        )
        weasyprint.HTML(string=html).write_pdf(str(output_path))
        return True
    except (ImportError, OSError):
        return False


# ---------------------------------------------------------------------------
# ReportLab 直出路径（Windows）
# ---------------------------------------------------------------------------

def _reportlab_pdf(md: str, output_path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import SimpleDocTemplate

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    styles = {
        "body":       ParagraphStyle("body",       fontName="STSong-Light", fontSize=11, leading=20, spaceAfter=6),
        "h1":         ParagraphStyle("h1",         fontName="STSong-Light", fontSize=22, leading=30, spaceBefore=16, spaceAfter=10),
        "h2":         ParagraphStyle("h2",         fontName="STSong-Light", fontSize=16, leading=24, spaceBefore=20, spaceAfter=8),
        "h3":         ParagraphStyle("h3",         fontName="STSong-Light", fontSize=13, leading=20, spaceBefore=10, spaceAfter=4),
        "h4":         ParagraphStyle("h4",         fontName="STSong-Light", fontSize=11, leading=18, spaceBefore=8,  spaceAfter=3),
        "bullet":     ParagraphStyle("bullet",     fontName="STSong-Light", fontSize=11, leading=20, leftIndent=16, spaceAfter=4),
        "sub_bullet": ParagraphStyle("sub_bullet", fontName="STSong-Light", fontSize=11, leading=18, leftIndent=32, spaceAfter=2),
    }

    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm, topMargin=2.5*cm, bottomMargin=2.5*cm,
    )
    doc.build(_md_to_elements(md, styles))


# ---------------------------------------------------------------------------
# 文本处理
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mix_latin(markup: str, lat_font: str) -> str:
    """将已有 XML markup 中不在标签内的 Latin/数字序列包裹为指定字体。"""
    parts = re.split(r'(<[^>]+>|&\w+;|&#\d+;)', markup)
    result = []
    for part in parts:
        if part.startswith("<") or part.startswith("&"):
            result.append(part)
        else:
            result.append(re.sub(
                r'[A-Za-z0-9][A-Za-z0-9 .,;:!?()\-+=%@#$]*',
                lambda m: f'<font name="{lat_font}">{m.group()}</font>',
                part,
            ))
    return "".join(result)


def _inline(text: str, lat_font: str = "Times-Roman") -> str:
    """Markdown inline → ReportLab XML，同时对 Latin 字符应用 lat_font。"""
    text = _esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    # [N] 角标 → 上标
    text = re.sub(r"\[(\d+)\]", r'<super><font size="8">[\1]</font></super>', text)
    return _mix_latin(text, lat_font)


def _bullet_text(content: str) -> str:
    return f'<font name="Times-Roman">&#8226;</font> {content}'


def _sub_bullet_text(content: str) -> str:
    return f'<font name="Times-Roman">&#8211;</font> {content}'


# ---------------------------------------------------------------------------
# 表格渲染
# ---------------------------------------------------------------------------

def _render_table(table_lines: list[str], styles: dict) -> list:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    rows: list[list[str]] = []
    for line in table_lines:
        if re.match(r"^\|[-| :]+\|$", line):   # 分隔行，跳过
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if cells:
            rows.append(cells)

    if not rows:
        return []

    num_cols = max(len(r) for r in rows)
    rows = [r + [""] * (num_cols - len(r)) for r in rows]   # 补齐列数

    cell_style = ParagraphStyle("tc", parent=styles["body"], fontSize=9, leading=14, spaceAfter=0)
    hdr_style  = ParagraphStyle("th", parent=cell_style, textColor=colors.white)

    para_rows = [
        [Paragraph(_inline(cell), hdr_style if ri == 0 else cell_style) for cell in row]
        for ri, row in enumerate(rows)
    ]

    col_w = 15 * cm / num_cols
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E86AB")),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]
    for ri in range(1, len(para_rows)):
        if ri % 2 == 0:
            cmds.append(("BACKGROUND", (0, ri), (-1, ri), colors.HexColor("#F2F7FA")))

    t = Table(para_rows, colWidths=[col_w] * num_cols, repeatRows=1)
    t.setStyle(TableStyle(cmds))
    return [t, Spacer(1, 10)]


# ---------------------------------------------------------------------------
# Markdown → Platypus 元素
# ---------------------------------------------------------------------------

def _md_to_elements(md: str, styles: dict) -> list:
    from reportlab.lib.units import cm
    from reportlab.platypus import HRFlowable, Image, Paragraph, Spacer

    class _BoldPara(Paragraph):
        """STSong-Light 无粗体变体，用 PDF fill+stroke（Tr=2）合成粗体。"""
        stroke_width: float = 0.3

        def draw(self) -> None:
            c = self.canv
            c.saveState()
            c.setLineWidth(self.stroke_width)
            c.setStrokeColor(self.style.textColor)
            c.addLiteral("2 Tr")
            super().draw()
            c.restoreState()

    def _h(text: str, style, sw: float) -> _BoldPara:
        p = _BoldPara(text, style)
        p.stroke_width = sw
        return p

    elements: list = []
    lines = md.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            elements.append(Spacer(1, 4))
            i += 1
            continue

        # 图片
        img_m = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if img_m:
            img_path = Path(img_m.group(2))
            if img_path.exists():
                try:
                    img = Image(str(img_path))
                    max_w = 14 * cm
                    if img.drawWidth > max_w:
                        img.drawHeight = img.drawHeight * max_w / img.drawWidth
                        img.drawWidth = max_w
                    elements.append(img)
                    elements.append(Spacer(1, 8))
                except Exception:
                    pass
            i += 1
            continue

        # 表格：收集连续的 | 开头行
        if stripped.startswith("|"):
            table_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            elements.extend(_render_table(table_lines, styles))
            continue

        # 标题
        if stripped.startswith("# ") and not stripped.startswith("##"):
            elements.append(_h(_inline(stripped[2:], "Times-Bold"), styles["h1"], sw=0.45))
            elements.append(HRFlowable(width="100%", thickness=1.5, color="#2E86AB", spaceAfter=6))
        elif stripped.startswith("## ") and not stripped.startswith("###"):
            elements.append(_h(_inline(stripped[3:], "Times-Bold"), styles["h2"], sw=0.38))
        elif stripped.startswith("### ") and not stripped.startswith("####"):
            elements.append(_h(_inline(stripped[4:], "Times-Bold"), styles["h3"], sw=0.3))
        elif stripped.startswith("#### "):
            elements.append(_h(_inline(stripped[5:], "Times-Bold"), styles["h4"], sw=0.25))
        elif re.match(r"^[-*] ", stripped):
            indent = len(line) - len(line.lstrip(" "))
            if indent >= 2:
                elements.append(Paragraph(_sub_bullet_text(_inline(stripped[2:])), styles["sub_bullet"]))
            else:
                elements.append(Paragraph(_bullet_text(_inline(stripped[2:])), styles["bullet"]))
        else:
            elements.append(Paragraph(_inline(stripped), styles["body"]))

        i += 1

    return elements
