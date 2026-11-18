"""Tests for advanced retrieval (MMR + multi-query + de-duplication)."""
import pytest

from rag.retrieval import retrieve


@pytest.mark.django_db
def test_retrieve_returns_scored_chunks(indexed_document, settings):
    """Requirement: find content relevant to the question with scores."""
    settings.RETRIEVAL_K = 2
    documents = retrieve("جنگل چیست؟")

    assert 1 <= len(documents) <= 2
    metadata = documents[0].metadata
    assert metadata["document_id"] == indexed_document.pk
    assert "chunk_index" in metadata
    assert "score" in metadata
    assert metadata["title"] == indexed_document.title


@pytest.mark.django_db
def test_retrieve_merges_multi_query_without_duplicates(
    indexed_document, settings, fake_llm
):
    """Requirement: question rewriting improves recall without duplicate chunks."""
    settings.RETRIEVAL_USE_MULTI_QUERY = True
    settings.RETRIEVAL_K = 5
    fake_llm("درختان جنگل\nحیوانات جنگل\nبارندگی شمال")

    documents = retrieve("جنگل چیست؟")

    assert documents
    keys = [(doc.metadata["document_id"], doc.metadata["chunk_index"]) for doc in documents]
    assert len(keys) == len(set(keys))


@pytest.mark.django_db
def test_retrieve_falls_back_when_llm_fails(indexed_document, settings, monkeypatch, broken_llm):
    """Requirement: retrieval keeps working (plain MMR) if rewriting fails."""
    settings.RETRIEVAL_USE_MULTI_QUERY = True
    monkeypatch.setattr("rag.retrieval.get_llm", lambda *a, **k: broken_llm())

    documents = retrieve("جنگل چیست؟")

    assert documents
    assert documents[0].metadata["document_id"] == indexed_document.pk


@pytest.mark.django_db
def test_retrieve_drops_chunks_below_the_relevance_threshold(indexed_document, settings):
    """Requirement: unrelated chunks are filtered by RETRIEVAL_MIN_SCORE."""
    settings.RETRIEVAL_MIN_SCORE = 1.1  # no chunk can reach this score

    assert retrieve("جنگل چیست؟") == []


@pytest.mark.django_db
def test_retrieve_empty_question_returns_nothing(indexed_document):
    """Requirement: empty questions are rejected without querying the store."""
    assert retrieve("   ") == []
