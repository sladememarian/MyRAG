"""REST API tests for documents."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from documents.models import Document
from rag.vectorstore import get_vectorstore


@pytest.fixture
def api_client_with_user(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="api-user", password="password123"
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_documents_require_authentication(db):
    """Requirement: the REST API is protected."""
    response = APIClient().get("/api/documents/")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_upload_document_indexes_it(api_client_with_user, docx_file):
    """Requirement: upload a document through the API and make it searchable."""
    response = api_client_with_user.post(
        "/api/documents/",
        {"title": "سند آزمایشی", "file": docx_file(paragraphs=["متن سند آزمایشی"])},
        format="multipart",
    )

    assert response.status_code == 201, response.data
    document = Document.objects.get(pk=response.data["id"])
    assert document.indexed is True
    assert "متن سند آزمایشی" in document.full_text
    assert get_vectorstore().get(where={"document_id": document.pk})["ids"]


@pytest.mark.django_db
def test_upload_hides_processing_error_details(
    api_client_with_user, docx_file, monkeypatch
):
    """Requirement: extraction failures return a safe message, not internals."""
    def explode(document):
        raise RuntimeError("internal path C:/secret")

    monkeypatch.setattr("documents.views.process_document", explode)

    response = api_client_with_user.post(
        "/api/documents/",
        {"title": "Broken", "file": docx_file()},
        format="multipart",
    )

    assert response.status_code == 400
    assert "internal path" not in str(response.data)
    assert Document.objects.count() == 0


@pytest.mark.django_db
def test_upload_rejects_non_docx(api_client_with_user):
    """Requirement: the API validates that uploads are .docx files."""
    response = api_client_with_user.post(
        "/api/documents/",
        {
            "title": "Bad",
            "file": SimpleUploadedFile("bad.pdf", b"%PDF-1.4", content_type="application/pdf"),
        },
        format="multipart",
    )

    assert response.status_code == 400
    assert "file" in response.data
    assert Document.objects.count() == 0


@pytest.mark.django_db
def test_upload_rejects_oversized_file(api_client_with_user, docx_file, settings):
    """Requirement: the API enforces the file size limit."""
    settings.MAX_DOCUMENT_SIZE_MB = 0

    response = api_client_with_user.post(
        "/api/documents/",
        {"title": "Too big", "file": docx_file()},
        format="multipart",
    )

    assert response.status_code == 400
    assert Document.objects.count() == 0


@pytest.mark.django_db
def test_update_reindexes_without_duplicates(api_client_with_user, indexed_document):
    """Requirement: editing a document updates its chunks (no duplicates)."""
    document_id = indexed_document.pk
    before = get_vectorstore().get(where={"document_id": document_id})["ids"]

    response = api_client_with_user.patch(
        f"/api/documents/{document_id}/", {"title": "عنوان تازه"}, format="json"
    )

    assert response.status_code == 200, response.data
    indexed_document.refresh_from_db()
    assert indexed_document.title == "عنوان تازه"
    stored = get_vectorstore().get(where={"document_id": document_id})
    assert len(stored["ids"]) == len(before)
    assert stored["metadatas"][0]["title"] == "عنوان تازه"


@pytest.mark.django_db
def test_delete_is_blocked_when_the_index_cannot_be_updated(
    api_client_with_user, indexed_document, monkeypatch
):
    """Requirement: never delete a row while its chunks remain in Chroma."""
    def explode(document_id):
        raise RuntimeError("chroma unavailable")

    monkeypatch.setattr("documents.views.delete_document_index", explode)

    response = api_client_with_user.delete(f"/api/documents/{indexed_document.pk}/")

    assert response.status_code == 503
    assert Document.objects.filter(pk=indexed_document.pk).exists()
    assert get_vectorstore().get(where={"document_id": indexed_document.pk})["ids"]


@pytest.mark.django_db
def test_delete_document_removes_chunks(api_client_with_user, indexed_document):
    """Requirement: deleting through the API also deletes vector data."""
    document_id = indexed_document.pk

    response = api_client_with_user.delete(f"/api/documents/{document_id}/")

    assert response.status_code == 204
    assert not Document.objects.filter(pk=document_id).exists()
    assert get_vectorstore().get(where={"document_id": document_id})["ids"] == []
