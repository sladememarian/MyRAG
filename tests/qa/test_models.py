"""Query model tests."""
import pytest

from qa.models import Query


@pytest.mark.django_db
def test_query_defaults_and_string(db):
    """Requirement: store the history of questions and answers."""
    query = Query.objects.create(question="جنگل چیست؟")

    assert query.status == Query.STATUS_OK
    assert query.sources == []
    assert query.answer == ""
    assert query.created_at is not None
    assert str(query) == "جنگل چیست؟"


@pytest.mark.django_db
def test_query_string_is_truncated(db):
    """Requirement: history rows stay readable in the admin list."""
    query = Query.objects.create(question="س" * 100)
    assert len(str(query)) == 61
    assert str(query).endswith("…")
