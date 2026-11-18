"""Tests for chunking and Chroma ingestion."""
import pytest

from documents.models import Document
from rag.ingest import delete_document, index_document, split_text
from rag.vectorstore import get_vectorstore


@pytest.mark.django_db
def test_index_document_stores_chunks_with_metadata(db):
    """Requirement: document text is split into chunks and stored with metadata."""
    document = Document.objects.create(
        title="Long document",
        full_text="این یک جمله آزمایشی است. " * 80,
    )
    count = index_document(document)

    assert count > 1
    stored = get_vectorstore().get(where={"document_id": document.pk})
    assert len(stored["ids"]) == count
    assert stored["metadatas"][0]["title"] == "Long document"
    assert stored["ids"][0] == f"doc{document.pk}-chunk0"


@pytest.mark.django_db
def test_reindex_does_not_duplicate_chunks(db):
    """Requirement: editing a document updates its chunks instead of duplicating."""
    document = Document.objects.create(title="Doc", full_text="متن کوتاه برای آزمایش.")
    first = index_document(document)
    second = index_document(document)

    assert first == second == 1
    stored = get_vectorstore().get(where={"document_id": document.pk})
    assert len(stored["ids"]) == 1


@pytest.mark.django_db
def test_delete_document_removes_all_chunks(db):
    """Requirement: deleting a document removes its vectors too."""
    document = Document.objects.create(
        title="Doc", full_text="متن آزمایشی. " * 60
    )
    count = index_document(document)
    assert count > 0

    removed = delete_document(document.pk)

    assert removed == count
    assert get_vectorstore().get(where={"document_id": document.pk})["ids"] == []


def test_split_text_respects_chunk_size(settings):
    """Requirement: chunks use a configurable size and overlap."""
    settings.CHUNK_SIZE = 50
    settings.CHUNK_OVERLAP = 10
    chunks = split_text("کلمه " * 100)
    assert len(chunks) > 1
    assert all(len(chunk) <= 50 for chunk in chunks)
