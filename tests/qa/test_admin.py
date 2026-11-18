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
