"""Markdown → PDF 渲染工具。

渲染链：weasyprint（Linux/Mac）→ ReportLab 直出（Windows 主路径）。
中文：UnicodeCIDFont STSong-Light（宋体），英文/数字：Times-Roman/Times-Bold。
不经过 xhtml2pdf（WinAnsiEncoding 导致 CJK 白色方框）。
"""
from __future__ import annotations

import re
from pathlib import Path

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
    pdf_path = _OUTPUT_DIR / f"report_{target_product}.pdf"
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
        body = MarkdownIt().render(md)
        html = (
            '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/><style>'
            'body{font-family:"Microsoft YaHei","SimHei",sans-serif;font-size:11pt;'
            'line-height:1.75;margin:48px 56px;}'
            'h1{font-size:18pt;border-bottom:2px solid #2E86AB;padding-bottom:6px;}'
            'h2{font-size:14pt;border-left:4px solid #2E86AB;padding-left:10px;margin-top:24px;}'
            'h3{font-size:12pt;margin-top:14px;}'
            'img{max-width:100%;display:block;margin:12px 0;}'
            f'</style></head><body>{body}</body></html>'
        )
        weasyprint.HTML(string=html).write_pdf(str(output_path))
        return True
    except (ImportError, OSError):  # OSError: Windows 无 GTK，fallback 到 reportlab
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

    # 全部使用宋体 STSong-Light，标题以字号区分层级
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    styles = {
        "body":   ParagraphStyle("body",   fontName="STSong-Light", fontSize=11, leading=20, spaceAfter=6),
        "h1":     ParagraphStyle("h1",     fontName="STSong-Light", fontSize=22, leading=30, spaceBefore=16, spaceAfter=10),
        "h2":     ParagraphStyle("h2",     fontName="STSong-Light", fontSize=16, leading=24, spaceBefore=20, spaceAfter=8),
        "h3":     ParagraphStyle("h3",     fontName="STSong-Light", fontSize=13, leading=20, spaceBefore=10, spaceAfter=4),
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
    # 分割出 XML 标签和 HTML 实体，保留原样；对其余文字部分做字体替换
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
    """markdown inline → ReportLab XML，同时对 Latin 字符应用 lat_font。"""
    text = _esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    return _mix_latin(text, lat_font)


def _bullet_text(content: str) -> str:
    return f'<font name="Times-Roman">&#8226;</font> {content}'


def _sub_bullet_text(content: str) -> str:
    return f'<font name="Times-Roman">&#8211;</font> {content}'


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
            c.addLiteral("2 Tr")  # PDF text render mode: fill then stroke
            super().draw()
            c.restoreState()  # Q 操作符恢复 Tr=0（fill only）

    def _h(text: str, style, sw: float) -> _BoldPara:
        p = _BoldPara(text, style)
        p.stroke_width = sw
        return p

    elements: list = []

    for line in md.splitlines():
        stripped = line.strip()

        if not stripped:
            elements.append(Spacer(1, 4))
            continue

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
            continue

        if stripped.startswith("# ") and not stripped.startswith("##"):
            elements.append(_h(_inline(stripped[2:], "Times-Bold"), styles["h1"], sw=0.45))
            elements.append(HRFlowable(width="100%", thickness=1.5, color="#2E86AB", spaceAfter=6))
        elif stripped.startswith("## ") and not stripped.startswith("###"):
            elements.append(_h(_inline(stripped[3:], "Times-Bold"), styles["h2"], sw=0.38))
        elif stripped.startswith("### "):
            elements.append(_h(_inline(stripped[4:], "Times-Bold"), styles["h3"], sw=0.3))
        elif re.match(r"^[-*] ", stripped):
            indent = len(line) - len(line.lstrip(" "))
            if indent >= 2:
                elements.append(Paragraph(_sub_bullet_text(_inline(stripped[2:])), styles["sub_bullet"]))
            else:
                elements.append(Paragraph(_bullet_text(_inline(stripped[2:])), styles["bullet"]))
        else:
            elements.append(Paragraph(_inline(stripped), styles["body"]))

    return elements
