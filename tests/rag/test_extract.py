"""Tests for .docx text extraction."""
import pytest

from rag.errors import DocumentExtractionError
from rag.extract import clean_text, extract_text


def test_extracts_paragraphs_and_table_cells_in_order(docx_bytes, tmp_path):
    """Requirement: store the full text, including text inside tables."""
    paragraphs = ["پاراگراف اول", "پاراگراف دوم"]
    rows = [["نام", "مقدار"], ["جنگل", "سبز"]]
    path = tmp_path / "order.docx"
    path.write_bytes(docx_bytes(paragraphs, rows))

    text = extract_text(path)

    assert "پاراگراف اول" in text
    assert "جنگل | سبز" in text
    assert text.index("پاراگراف اول") < text.index("جنگل | سبز")
    assert text.index("جنگل | سبز") < text.index("پاراگراف دوم")


def test_rejects_non_docx_file(tmp_path):
    """Requirement: only Word .docx files are processed."""
    path = tmp_path / "notes.txt"
    path.write_text("hello", encoding="utf-8")
    with pytest.raises(DocumentExtractionError):
        extract_text(path)


def test_empty_document_raises(docx_bytes, tmp_path):
    """Requirement: unreadable documents are reported, not silently indexed."""
    path = tmp_path / "empty.docx"
    path.write_bytes(docx_bytes(paragraphs=["   "]))
    with pytest.raises(DocumentExtractionError, match="readable text"):
        extract_text(path)


def test_clean_text_removes_bidi_controls_and_keeps_zwnj():
    """Requirement: Persian/RTL text is handled safely."""
    assert clean_text("\u200eمتن\u200f") == "متن"
    assert clean_text("می\u200cخواهم") == "می\u200cخواهم"
    assert clean_text("a\r\n\r\n\r\n\r\nb") == "a\n\nb"
