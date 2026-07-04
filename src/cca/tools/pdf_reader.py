"""Document text extraction -- PDF / TXT / MD.

D-032 revision: PM's `initial_brief_node` calls this tool to extract text from a
user-uploaded doc, feeding it into PM phase 1's prompt for GPT-5 to distill a DomainSeed.

Design tradeoffs:
- PDFs go through pypdf, **text-only extraction** (fine at demo scale; chart/layout
  info is lost, but ~90% of the information density is still in the text)
- No dependency on poppler / pdf2image (friendlier for cross-platform deployment)
- Not exposed as a @tool -- called directly by the PM node, since PM isn't a ReAct agent

Upgrade path: if image/layout info is ever needed, add a
`read_file_as_images(path) -> list[Image]` fallback branch.
"""
from __future__ import annotations

from pathlib import Path

import pypdf

_SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}


class UnsupportedFormat(ValueError):
    """The file's suffix isn't on the supported whitelist."""


def read_file(path: str | Path) -> str:
    """Extract a file's text content.

    Supported suffixes: `.pdf` / `.txt` / `.md` / `.markdown`.
    PDFs have all pages' text concatenated; plain text is read directly as UTF-8.

    Raises:
        FileNotFoundError: the path doesn't exist
        UnsupportedFormat: the suffix isn't supported
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
    """Extract and concatenate all pages' text with pypdf, skipping empty pages."""
    reader = pypdf.PdfReader(str(path))
    pages = [page.extract_text() for page in reader.pages]
    return "\n\n".join(p for p in pages if p and p.strip())
