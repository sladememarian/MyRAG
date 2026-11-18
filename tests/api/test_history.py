"""REST API tests for the history endpoints and authentication."""
import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from qa.models import Query


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
def test_history_list_is_paginated(api_client_with_user, api_user):
    """Requirement: history is exposed through a paginated REST endpoint."""
    for index in range(25):
        Query.objects.create(question=f"سوال {index}", user=api_user)

    response = api_client_with_user.get("/api/history/")

    assert response.status_code == 200
    assert response.data["count"] == 25
    assert len(response.data["results"]) == 20
    assert response.data["next"] is not None


@pytest.mark.django_db
def test_history_detail(api_client_with_user, api_user):
    """Requirement: a single history entry can be retrieved."""
    query = Query.objects.create(question="سوال", answer="پاسخ", user=api_user)

    response = api_client_with_user.get(f"/api/history/{query.pk}/")

    assert response.status_code == 200
    assert response.data["question"] == "سوال"
    assert response.data["answer"] == "پاسخ"


@pytest.mark.django_db
def test_token_authentication_works(db, django_user_model):
    """Requirement: scripts can authenticate with a DRF token."""
    user = django_user_model.objects.create_user(username="token-user", password="x")
    token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    response = client.get("/api/history/")

    assert response.status_code == 200


def test_history_requires_authentication(db):
    """Requirement: history is private."""
    response = APIClient().get("/api/history/")
    assert response.status_code in (401, 403)


def test_history_is_private_to_its_owner(api_user, django_user_model):
    """Requirement: one user cannot read another user's history."""
    other = django_user_model.objects.create_user(username="other", password="x")
    own_query = Query.objects.create(question="مال من", user=api_user)
    other_query = Query.objects.create(question="مال دیگری", user=other)
    client = APIClient()
    client.force_authenticate(user=api_user)

    listing = client.get("/api/history/")

    assert listing.data["count"] == 1
    assert listing.data["results"][0]["id"] == own_query.pk
    assert client.get(f"/api/history/{other_query.pk}/").status_code == 404


def test_health_endpoint_is_public(db):
    """Requirement: a simple liveness endpoint for containers."""
    response = APIClient().get("/api/health/")
    assert response.status_code == 200
    assert response.data == {"status": "ok"}
