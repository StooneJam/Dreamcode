"""文档文本抽取工具 —— PDF / TXT / MD。

D-032 修订版：PM `initial_brief_node` 调本工具把用户上传文档抽成文本，
拼进 PM phase 1 prompt 让 GPT-5 蒸馏 DomainSeed。

设计取舍：
- PDF 走 pypdf 抽**文本主导**（demo 规模够用；图表/版式信息丢失但 90% 信息密度仍在文本）
- 不依赖 poppler / pdf2image（跨平台部署友好）
- 不暴露为 @tool —— 由 PM 节点直接调用，PM 不是 ReAct agent

升级路径：未来若需要图像/版式信息，加 `read_file_as_images(path) -> list[Image]` 兜底分支。
"""
from __future__ import annotations

from pathlib import Path

import pypdf

_SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}


class UnsupportedFormat(ValueError):
    """文件后缀不在支持白名单内。"""


def read_file(path: str | Path) -> str:
    """抽取文件文本内容。

    支持后缀：`.pdf` / `.txt` / `.md` / `.markdown`。
    PDF 拼接所有页文本；纯文本直读为 UTF-8。

    Raises:
        FileNotFoundError: 路径不存在
        UnsupportedFormat: 后缀不支持
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"找不到文件: {p}")

    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(p)
    if suffix in _SUPPORTED_TEXT_SUFFIXES:
        return p.read_text(encoding="utf-8")
    raise UnsupportedFormat(
        f"不支持的文件格式 {suffix!r}（支持: .pdf / .txt / .md / .markdown）"
    )


def _read_pdf(path: Path) -> str:
    """用 pypdf 抽全部页文本并拼接，空页跳过。"""
    reader = pypdf.PdfReader(str(path))
    pages = [page.extract_text() for page in reader.pages]
    return "\n\n".join(p for p in pages if p and p.strip())
