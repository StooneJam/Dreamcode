"""Tests for the pdf_reader document-extraction tool -- uses the real pypdf package
for the PDF path, plain text goes through file I/O."""
from __future__ import annotations

from pathlib import Path

import pypdf
import pytest

from cca.tools.pdf_reader import UnsupportedFormat, read_file


def test_read_file_txt(tmp_path: Path) -> None:
    p = tmp_path / "note.txt"
    p.write_text("Hello 飞书\n第二行", encoding="utf-8")
    assert "飞书" in read_file(p)
    assert "第二行" in read_file(p)


def test_read_file_md(tmp_path: Path) -> None:
    p = tmp_path / "spec.md"
    p.write_text("# 标题\n内容", encoding="utf-8")
    text = read_file(p)
    assert "标题" in text
    assert "内容" in text


def test_read_file_pdf(tmp_path: Path) -> None:
    """Build a minimal readable PDF, for pypdf to extract text from."""
    pdf_path = tmp_path / "doc.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)  # a single blank page
    with pdf_path.open("wb") as f:
        writer.write(f)
    # pypdf extracts an empty string from a blank page, but the call itself should succeed without raising
    text = read_file(pdf_path)
    assert isinstance(text, str)


def test_read_file_missing_raises() -> None:
    with pytest.raises(FileNotFoundError):
        read_file("/no/such/path.pdf")


def test_read_file_unsupported_format_raises(tmp_path: Path) -> None:
    p = tmp_path / "image.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(UnsupportedFormat):
        read_file(p)


def test_read_file_accepts_str_path(tmp_path: Path) -> None:
    p = tmp_path / "note.txt"
    p.write_text("ok", encoding="utf-8")
    assert read_file(str(p)) == "ok"
