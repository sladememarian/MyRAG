"""Admin tests for the Query history."""
import pytest

from qa.admin import QueryAdmin
from qa.models import Query


@pytest.fixture
def admin_client(client, django_user_model):
    user = django_user_model.objects.create_superuser(
        username="admin", email="admin@example.com", password="password123"
    )
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_admin_add_query_answers_and_saves(admin_client, monkeypatch):
    """Requirement: asking a question in admin generates and stores the answer."""
    monkeypatch.setattr(
        "qa.services.answer_question",
        lambda question: {
            "answer": "پاسخ ادمین",
            "sources": [
                {
                    "document_id": 7,
                    "title": "جنگل",
                    "chunk_index": 0,
                    "score": 0.5,
                    "snippet": "متن",
                }
            ],
            "model_name": "fake-model",
        },
    )

    response = admin_client.post(
        "/admin/qa/query/add/", {"question": "جنگل چیست؟"}
    )

    assert response.status_code == 302
    query = Query.objects.get()
    assert query.answer == "پاسخ ادمین"
    assert query.status == Query.STATUS_OK
    assert query.sources[0]["title"] == "جنگل"
    # The admin question is owned by the administrator who asked it.
    assert query.user.username == "admin"


@pytest.mark.django_db
def test_admin_add_query_stores_errors(admin_client, monkeypatch):
    """Requirement: the admin shows failures without losing the question."""
    from rag.errors import LLMError

    def fail(question):
        raise LLMError("The language model is rate-limited right now.")

    monkeypatch.setattr("qa.services.answer_question", fail)

    response = admin_client.post("/admin/qa/query/add/", {"question": "سوال"})

    assert response.status_code == 302
    query = Query.objects.get()
    assert query.status == Query.STATUS_ERROR
    assert query.failure_kind == Query.FAILURE_LLM
    assert "rate-limited" in query.error_message


@pytest.mark.django_db
def test_question_is_read_only_after_creation(admin_client):
    """Requirement: history is immutable; only new questions can be typed."""
    query = Query.objects.create(question="قبلی", answer="پاسخ")

    add_page = admin_client.get("/admin/qa/query/add/")
    change_page = admin_client.get(f"/admin/qa/query/{query.pk}/change/")

    assert "question" in add_page.context["adminform"].form.fields
    assert "question" not in change_page.context["adminform"].form.fields
    assert "answer" not in change_page.context["adminform"].form.fields


@pytest.mark.django_db
def test_sources_are_rendered_readably():
    """Requirement: sources are shown in a readable format in admin."""
    query = Query(question="q", sources=[{"title": "سند", "document_id": 1}])
    html = QueryAdmin(Query, None).sources_display(query)
    assert "سند" in html
    assert "<pre" in html


@pytest.mark.django_db
def test_answer_is_visible_in_list_and_detail():
    """Requirement: the stored answer is visible in the question history."""
    query = Query.objects.create(question="q", answer="خط اول\nخط دوم")
    admin_view = QueryAdmin(Query, None)

    assert "خط اول" in admin_view.answer_preview(query)
    html = admin_view.answer_display(query)
    assert "خط اول" in html and "خط دوم" in html
    assert "pre-wrap" in html


@pytest.mark.django_db
def test_answer_preview_links_to_the_full_answer(admin_client):
    """Requirement: clicking the answer in the list opens the full answer."""
    query = Query.objects.create(question="question", answer="first line\nsecond line")
    change_url = f"/admin/qa/query/{query.pk}/change/"

    list_html = admin_client.get("/admin/qa/query/").content.decode()
    assert list_html.count(f'href="{change_url}"') == 2  # question + answer

    detail_html = admin_client.get(change_url).content.decode()
    assert "first line" in detail_html and "second line" in detail_html


def test_answer_display_handles_empty_answer():
    """Requirement: a query without an answer renders cleanly."""
    assert QueryAdmin(Query, None).answer_display(Query()) == "—"


def test_sources_display_handles_empty_sources():
    """Requirement: empty source lists render cleanly."""
    assert QueryAdmin(Query, None).sources_display(Query()) == "—"


@pytest.mark.django_db
def test_failed_query_row_shows_state_and_retry_button(admin_client):
    """Requirement: a failed query is marked failed in the list and gets a retry button."""
    Query.objects.create(
        question="سوال ناموفق",
        status=Query.STATUS_ERROR,
        failure_kind=Query.FAILURE_LLM,
        error_message="rate limited",
    )

    html = admin_client.get("/admin/qa/query/").content.decode()

    assert "Failed" in html
    assert "Language model error" in html
    assert "/retry/" in html
    assert "Retry" in html


@pytest.mark.django_db
def test_successful_query_row_has_no_retry_button(admin_client):
    """Requirement: only failed questions offer a retry."""
    Query.objects.create(question="سوال موفق", answer="پاسخ")

    html = admin_client.get("/admin/qa/query/").content.decode()

    assert "Succeeded" in html
    assert "/retry/" not in html


@pytest.mark.django_db
def test_retry_reruns_a_failed_query(admin_client, monkeypatch):
    """Requirement: the retry button asks the question again and saves the result."""
    query = Query.objects.create(
        question="سوال",
        status=Query.STATUS_ERROR,
        failure_kind=Query.FAILURE_LLM,
        error_message="rate limited",
    )
    monkeypatch.setattr(
        "qa.services.answer_question",
        lambda question: {
            "answer": "پاسخ دوباره",
            "sources": [],
            "model_name": "fake-model",
        },
    )

    response = admin_client.post(f"/admin/qa/query/{query.pk}/retry/")

    assert response.status_code == 302
    query.refresh_from_db()
    assert query.status == Query.STATUS_OK
    assert query.answer == "پاسخ دوباره"
    assert query.error_message == ""


@pytest.mark.django_db
def test_retry_keeps_the_failure_when_it_fails_again(admin_client, monkeypatch):
    """Requirement: a failed retry is stored, not swallowed."""
    from rag.errors import LLMError

    query = Query.objects.create(question="سوال", status=Query.STATUS_ERROR)

    def fail(question):
        raise LLMError("still rate-limited")

    monkeypatch.setattr("qa.services.answer_question", fail)

    response = admin_client.post(f"/admin/qa/query/{query.pk}/retry/")

    assert response.status_code == 302
    query.refresh_from_db()
    assert query.status == Query.STATUS_ERROR
    assert query.failure_kind == Query.FAILURE_LLM
    assert "still rate-limited" in query.error_message


@pytest.mark.django_db
def test_retry_rejects_get_requests(admin_client):
    """Requirement: retrying costs an LLM call, so it must be a POST."""
    query = Query.objects.create(question="سوال", status=Query.STATUS_ERROR)

    response = admin_client.get(f"/admin/qa/query/{query.pk}/retry/")

    assert response.status_code == 405


@pytest.mark.django_db
def test_model_management_is_a_separate_admin_section(admin_client):
    """Requirement: model configuration lives in its own Model Management section."""
    response = admin_client.get("/admin/")
    apps = {app["app_label"]: app for app in response.context["available_apps"]}

    assert [model["object_name"] for model in apps["qa"]["models"]] == ["Query"]
    assert apps["providers"]["name"] == "Model Management"
    # The provider page is the tabbed configuration screen, not a history list.
    assert [model["object_name"] for model in apps["providers"]["models"]] == [
        "Provider"
    ]
