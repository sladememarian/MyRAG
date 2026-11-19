"""Tests for grounded answer generation (LLM mocked)."""
import pytest
from langchain_core.documents import Document as LangchainDocument

from rag.chain import answer_question, build_context
from rag.errors import LLMError, NoRelevantContentError


@pytest.mark.django_db
def test_answer_question_returns_answer_and_sources(indexed_document, fake_llm, settings):
    """Requirement: generate an answer grounded in the documents, with sources."""
    fake_llm("جنگل جایی است که درختان زیادی دارد.")

    result = answer_question("جنگل چیست؟")

    assert result["answer"] == "جنگل جایی است که درختان زیادی دارد."
    assert result["model_name"] == settings.OPENROUTER_MODEL
    assert result["sources"]
    source = result["sources"][0]
    assert source["document_id"] == indexed_document.pk
    assert source["title"] == indexed_document.title
    assert "chunk_index" in source
    assert "snippet" in source


@pytest.mark.django_db
def test_answer_question_without_documents_raises(db):
    """Requirement: answer honestly when the documents contain nothing."""
    with pytest.raises(NoRelevantContentError):
        answer_question("جنگل چیست؟")


@pytest.mark.django_db
def test_answer_question_reports_llm_errors(indexed_document, monkeypatch, broken_llm):
    """Requirement: rate limits and API failures produce clear messages."""
    monkeypatch.setattr("rag.chain.get_llm", lambda *args, **kwargs: broken_llm())

    with pytest.raises(LLMError, match="rate-limited"):
        answer_question("جنگل چیست؟")


@pytest.mark.django_db
def test_empty_llm_answer_is_an_error(indexed_document, fake_llm):
    """Requirement: empty model output is handled explicitly."""
    fake_llm("   ")

    with pytest.raises(LLMError, match="empty answer"):
        answer_question("جنگل چیست؟")


@pytest.mark.django_db
def test_empty_question_is_rejected(indexed_document):
    """Requirement: the API/service requires a real question."""
    with pytest.raises(ValueError):
        answer_question("   ")


def test_build_context_respects_the_character_limit(settings):
    """Requirement: prompts stay within a configurable context budget."""
    settings.CONTEXT_MAX_CHARS = 200
    settings.SNIPPET_CHARS = 50
    documents = [
        LangchainDocument(
            page_content="متن " * 200,
            metadata={
                "document_id": 1,
                "title": "Doc",
                "chunk_index": 0,
                "score": 0.9,
            },
        )
    ]

    context, sources = build_context(documents)

    assert len(context) <= 200
    assert len(sources) == 1
    assert len(sources[0]["snippet"]) <= 50


def test_plain_text_strips_markdown_marks():
    """Requirement: answers read cleanly in the admin, which does not render Markdown."""
    from rag.chain import plain_text

    raw = "**1. Investment:** see [1]\n\n## Pay\n* 5 x 3h\n* `total` = **95%**\n\n\n\nEnd"

    assert plain_text(raw) == "1. Investment: see [1]\n\nPay\n- 5 x 3h\n- total = 95%\n\nEnd"
