"""Shared pytest fixtures.

Tests are deterministic and offline:
- embeddings use a fake deterministic backend (no model download),
- Chroma lives in a per-test temporary directory,
- the LLM is monkeypatched in the individual tests.
"""
import io
import uuid

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from docx import Document as DocxDocument

from documents.models import Document
from rag.services import process_document
from rag.vectorstore import _build_embeddings

DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

SAMPLE_PARAGRAPHS = [
    "جنگل مکانی است که در آن درختان بسیاری رشد می‌کنند.",
    "جنگل‌های شمال ایران به دلیل بارندگی فراوان سرسبز هستند.",
    "حیوانات زیادی مانند خرس و گرگ در جنگل زندگی می‌کنند.",
]

SAMPLE_TABLE = [
    ["نام جنگل", "استان"],
    ["جنگل هیرکانی", "گلستان"],
]


def build_docx(paragraphs=None, table_rows=None) -> bytes:
    """Create a small .docx in memory (text and optional table, in order).

    When a table is requested it is placed between the first and the second
    paragraph (or after the only paragraph), so tests can check that extraction
    keeps the original document order.
    """
    paragraphs = list(paragraphs or ["متن نمونه برای آزمایش."])
    document = DocxDocument()
    for index, paragraph in enumerate(paragraphs):
        if table_rows and index == 1:
            _add_table(document, table_rows)
        document.add_paragraph(paragraph)
    if table_rows and len(paragraphs) < 2:
        _add_table(document, table_rows)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _add_table(document, table_rows) -> None:
    table = document.add_table(rows=len(table_rows), cols=len(table_rows[0]))
    for row_index, row in enumerate(table_rows):
        for column_index, value in enumerate(row):
            table.cell(row_index, column_index).text = value



@pytest.fixture(autouse=True)
def clear_rate_limit_cache():
    """Throttle counters must not leak between tests (users reuse pks)."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def rag_test_environment(settings, tmp_path):
    """Isolate every test: fake embeddings, temp Chroma dir and media dir."""
    settings.EMBEDDING_BACKEND = "fake"
    settings.EMBEDDING_FAKE_DIM = 48
    settings.CHROMA_DIR = str(tmp_path / "chroma")
    settings.CHROMA_COLLECTION = f"test_{uuid.uuid4().hex[:12]}"
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.RETRIEVAL_USE_MULTI_QUERY = False
    # Fake embeddings do not carry real semantic similarity; keep every result
    # unless a test explicitly exercises the relevance threshold.
    settings.RETRIEVAL_MIN_SCORE = 0.0
    _build_embeddings.cache_clear()
    yield
    _build_embeddings.cache_clear()


@pytest.fixture
def docx_bytes():
    return build_docx


@pytest.fixture
def docx_file():
    """Factory: docx_file(paragraphs=[...], table_rows=[...], name="x.docx")."""

    def factory(paragraphs=None, table_rows=None, name="sample.docx"):
        data = build_docx(paragraphs, table_rows)
        return SimpleUploadedFile(name, data, content_type=DOCX_CONTENT_TYPE)

    return factory


@pytest.fixture
def indexed_document(db, docx_file):
    """A real document processed through the real ingestion pipeline."""
    document = Document.objects.create(
        title="جنگل‌های ایران",
        file=docx_file(paragraphs=SAMPLE_PARAGRAPHS, table_rows=SAMPLE_TABLE),
    )
    process_document(document)
    document.refresh_from_db()
    return document


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a fake chat model for both answer generation and query rewriting."""

    def install(*responses):
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        model = FakeListChatModel(responses=list(responses))
        monkeypatch.setattr("rag.chain.get_llm", lambda *args, **kwargs: model)
        monkeypatch.setattr("rag.retrieval.get_llm", lambda *args, **kwargs: model)
        return model

    return install


class BrokenLLM:
    """A chat model that always fails, used to test error handling."""

    def __init__(self, message="429 rate limit exceeded"):
        self.message = message

    def invoke(self, *args, **kwargs):
        raise RuntimeError(self.message)


@pytest.fixture
def broken_llm():
    return BrokenLLM
