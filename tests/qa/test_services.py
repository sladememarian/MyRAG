"""Tests for the shared question-answering service."""
import pytest

from qa.models import Query
from qa.services import run_query
from rag.errors import LLMError, NoRelevantContentError


@pytest.mark.django_db
def test_run_query_saves_a_successful_answer(monkeypatch, django_user_model):
    """Requirement: every question and answer is stored in the history."""
    monkeypatch.setattr(
        "qa.services.answer_question",
        lambda question: {
            "answer": "پاسخ آزمایشی",
            "sources": [{"document_id": 1, "title": "Doc", "chunk_index": 0}],
            "model_name": "fake-model",
        },
    )

    user = django_user_model.objects.create_user(username="asker", password="x")
    query = run_query("جنگل چیست؟", user=user)

    assert query.pk is not None
    assert query.user == user
    assert query.failure_kind == ""
    assert query.status == Query.STATUS_OK
    assert query.answer == "پاسخ آزمایشی"
    assert query.sources[0]["title"] == "Doc"
    assert query.model_name == "fake-model"


@pytest.mark.django_db
def test_run_query_records_a_no_content_error(monkeypatch):
    """Requirement: failed questions are stored with an error message."""
    def raise_no_content(question):
        raise NoRelevantContentError("چیزی پیدا نشد")

    monkeypatch.setattr("qa.services.answer_question", raise_no_content)

    query = run_query("سوال بی‌ربط")

    assert query.status == Query.STATUS_ERROR
    assert query.answer == ""
    assert query.sources == []
    assert query.error_message == "چیزی پیدا نشد"
    assert query.failure_kind == "no_content"


@pytest.mark.django_db
def test_run_query_records_unexpected_errors(monkeypatch):
    """Requirement: unexpected failures never lose the question history."""
    def explode(question):
        raise RuntimeError("boom")

    monkeypatch.setattr("qa.services.answer_question", explode)

    query = run_query("سوال")

    assert query.status == Query.STATUS_ERROR
    assert "boom" not in query.error_message
    assert "unexpected error" in query.error_message.lower()
    assert query.failure_kind == "other"


@pytest.mark.django_db
def test_run_query_marks_llm_errors(monkeypatch):
    """Requirement: LLM problems are visible in the history status."""
    def fail(question):
        raise LLMError("rate limited")

    monkeypatch.setattr("qa.services.answer_question", fail)

    query = run_query("سوال")

    assert query.status == Query.STATUS_ERROR
    assert query.failure_kind == "llm"
