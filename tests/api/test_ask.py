"""REST API tests for /api/ask/."""
import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from qa.models import Query
from qa.services import UNEXPECTED_ERROR_MESSAGE


@pytest.fixture
def api_user(db, django_user_model):
    return django_user_model.objects.create_user(
        username="api-user", password="password123"
    )


@pytest.fixture
def api_client_with_user(api_user):
    client = APIClient()
    client.force_authenticate(user=api_user)
    return client


@pytest.mark.django_db
def test_ask_returns_answer_sources_and_saves_history(
    api_client_with_user, api_user, indexed_document, fake_llm
):
    """Requirement: POST /api/ask/ answers from documents and stores history."""
    fake_llm("جنگل مکانی سرسبز با درختان بسیار است.")

    response = api_client_with_user.post(
        "/api/ask/", {"question": "جنگل چیست؟"}, format="json"
    )

    assert response.status_code == 200, response.data
    assert response.data["answer"] == "جنگل مکانی سرسبز با درختان بسیار است."
    assert response.data["sources"]
    assert response.data["sources"][0]["document_id"] == indexed_document.pk
    assert response.data["status"] == Query.STATUS_OK

    query = Query.objects.get(pk=response.data["query_id"])
    assert query.question == "جنگل چیست؟"
    assert query.answer == response.data["answer"]
    # The history record is owned by the authenticated caller.
    assert query.user == api_user


@pytest.mark.django_db
def test_ask_without_documents_returns_404(api_client_with_user, fake_llm):
    """Requirement: a clear error when nothing relevant is indexed."""
    fake_llm("unused")

    response = api_client_with_user.post(
        "/api/ask/", {"question": "جنگل چیست؟"}, format="json"
    )

    assert response.status_code == 404
    query = Query.objects.get()
    assert query.status == Query.STATUS_ERROR
    assert query.failure_kind == Query.FAILURE_NO_CONTENT


@pytest.mark.django_db
def test_ask_reports_llm_failure_as_503(
    api_client_with_user, indexed_document, monkeypatch, broken_llm
):
    """Requirement: LLM/rate-limit failures are reported clearly."""
    monkeypatch.setattr("rag.chain.get_llm", lambda *args, **kwargs: broken_llm())

    response = api_client_with_user.post(
        "/api/ask/", {"question": "جنگل چیست؟"}, format="json"
    )

    assert response.status_code == 503
    assert "rate-limited" in response.data["detail"]
    query = Query.objects.get(pk=response.data["query_id"])
    assert query.status == Query.STATUS_ERROR
    assert query.failure_kind == Query.FAILURE_LLM


@pytest.mark.django_db
def test_ask_hides_unexpected_error_details(
    api_client_with_user, indexed_document, monkeypatch
):
    """Requirement: internal errors are logged, not sent to API clients."""
    def explode(question):
        raise RuntimeError("database password=secret")

    monkeypatch.setattr("qa.services.answer_question", explode)

    response = api_client_with_user.post(
        "/api/ask/", {"question": "جنگل چیست؟"}, format="json"
    )

    assert response.status_code == 400
    assert "password=secret" not in str(response.data)
    query = Query.objects.get(pk=response.data["query_id"])
    assert query.error_message == UNEXPECTED_ERROR_MESSAGE
    assert query.failure_kind == Query.FAILURE_OTHER


@pytest.mark.django_db
def test_ask_is_rate_limited_per_user(
    api_client_with_user, indexed_document, fake_llm, settings
):
    """Requirement: the expensive ask endpoint has a per-user rate limit."""
    settings.ASK_THROTTLE_RATE = "1/min"
    cache.clear()
    fake_llm("پاسخ")

    first = api_client_with_user.post(
        "/api/ask/", {"question": "جنگل چیست؟"}, format="json"
    )
    second = api_client_with_user.post(
        "/api/ask/", {"question": "جنگل چیست؟"}, format="json"
    )

    assert first.status_code == 200, first.data
    assert second.status_code == 429


@pytest.mark.django_db
def test_ask_validates_the_question(api_client_with_user):
    """Requirement: serializers validate API input."""
    response = api_client_with_user.post("/api/ask/", {"question": "?"}, format="json")
    assert response.status_code == 400
    assert "question" in response.data
