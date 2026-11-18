"""Admin wiring tests for documents (upload, re-index, delete)."""
import pytest

from documents.models import Document
from rag.vectorstore import get_vectorstore


@pytest.fixture
def admin_client(client, django_user_model):
    user = django_user_model.objects.create_superuser(
        username="admin", email="admin@example.com", password="password123"
    )
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_admin_upload_extracts_and_indexes(admin_client, docx_file):
    """Requirement: saving a document in admin extracts text and indexes chunks."""
    response = admin_client.post(
        "/admin/documents/document/add/",
        {"title": "Admin upload", "file": docx_file(paragraphs=["متن ادمین"])},
    )
    assert response.status_code == 302
    document = Document.objects.get(title="Admin upload")
    assert document.indexed is True
    assert "متن ادمین" in document.full_text
    stored = get_vectorstore().get(where={"document_id": document.pk})
    assert stored["ids"]


@pytest.mark.django_db
def test_admin_delete_removes_chunks(admin_client, indexed_document):
    """Requirement: deleting a document also removes its vector data."""
    document_id = indexed_document.pk
    response = admin_client.post(
        f"/admin/documents/document/{document_id}/delete/", {"post": "yes"}
    )
    assert response.status_code == 302
    assert not Document.objects.filter(pk=document_id).exists()
    assert get_vectorstore().get(where={"document_id": document_id})["ids"] == []


@pytest.mark.django_db
def test_admin_keeps_the_row_when_the_index_fails(
    admin_client, indexed_document, monkeypatch
):
    """Requirement: admin deletion also stops if Chroma cannot be updated."""
    def explode(document_id):
        raise RuntimeError("chroma unavailable")

    monkeypatch.setattr("documents.admin.delete_document_index", explode)

    response = admin_client.post(
        f"/admin/documents/document/{indexed_document.pk}/delete/", {"post": "yes"}
    )

    assert response.status_code == 302
    assert Document.objects.filter(pk=indexed_document.pk).exists()


@pytest.mark.django_db
def test_admin_bulk_delete_removes_chunks(admin_client, indexed_document):
    """Requirement: bulk delete from admin also cleans the vector store."""
    document_id = indexed_document.pk

    # Django admin asks for confirmation first, then deletes with post=yes.
    admin_client.post(
        "/admin/documents/document/",
        {"action": "delete_selected", "_selected_action": [document_id]},
    )
    response = admin_client.post(
        "/admin/documents/document/",
        {"action": "delete_selected", "_selected_action": [document_id], "post": "yes"},
    )

    assert response.status_code == 302
    assert get_vectorstore().get(where={"document_id": document_id})["ids"] == []


@pytest.mark.django_db
def test_admin_reindex_action(admin_client, indexed_document):
    """Requirement: re-indexing is available as an admin action."""
    from rag.ingest import delete_document

    delete_document(indexed_document.pk)
    assert get_vectorstore().get(where={"document_id": indexed_document.pk})["ids"] == []

    response = admin_client.post(
        "/admin/documents/document/",
        {
            "action": "reindex_selected",
            "_selected_action": [indexed_document.pk],
        },
    )

    assert response.status_code == 302
    stored = get_vectorstore().get(where={"document_id": indexed_document.pk})
    assert stored["ids"]
    assert any("جنگل" in text for text in stored["documents"])
