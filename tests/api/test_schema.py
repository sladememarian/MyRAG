"""OpenAPI schema and Swagger UI tests."""
from rest_framework.test import APIClient


def test_openapi_schema_is_available(db):
    """Requirement: drf-spectacular exposes a machine-readable API schema."""
    response = APIClient().get("/api/schema/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "openapi" in content.lower()
    assert "/api/ask/" in content


def test_swagger_ui_is_served(db):
    """Requirement: interactive Swagger documentation at /api/docs/."""
    response = APIClient().get("/api/docs/")

    assert response.status_code == 200
    assert b"swagger" in response.content.lower()
