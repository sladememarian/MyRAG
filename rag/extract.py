"""Extract plain text from a .docx file, keeping paragraphs and tables in order.

python-docx already returns Unicode, which is what Persian/RTL text needs. We
only normalise the text (NFC) and drop invisible bidi control characters that
would otherwise end up inside prompts and search queries.
"""
import re
import unicodedata
from pathlib import Path

from docx import Document as load_docx
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from rag.errors import DocumentExtractionError

# Invisible direction marks / embedding controls (keep ZWNJ = U+200C).
_BIDI_CONTROLS = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_MANY_BLANKS = re.compile(r"\n{3,}")


def extract_text(path: str | Path) -> str:
    """Return the cleaned full text of a .docx file."""
    try:
        document = load_docx(str(path))
    except Exception as exc:  # noqa: BLE001 - python-docx raises several types
        raise DocumentExtractionError(f"Could not open the .docx file: {exc}") from exc

    blocks: list[str] = []
    for block in _iter_blocks(document):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                blocks.append(text)
        else:  # Table: one line per row, cells separated by " | "
            for row in block.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    blocks.append(" | ".join(cells))

    text = clean_text("\n\n".join(blocks))
    if not text:
        raise DocumentExtractionError("The document does not contain any readable text.")
    return text


def clean_text(text: str) -> str:
    """Normalise Unicode, remove bidi controls and collapse blank lines."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _BIDI_CONTROLS.sub("", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return _MANY_BLANKS.sub("\n\n", text).strip()


def _iter_blocks(document):
    """Yield paragraphs and tables in the order they appear in the file."""
    body = document.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)
