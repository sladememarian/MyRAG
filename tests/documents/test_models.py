"""Document model and upload validator tests."""
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError

from documents.models import Document
from documents.validators import validate_docx_file


@pytest.mark.django_db
def test_document_defaults_and_string(db, docx_file):
    """Requirement: add documents with title, .docx file and stored full text."""
    document = Document.objects.create(title="Sample", file=docx_file())
    assert document.full_text == ""
    assert document.indexed is False
    assert str(document) == "Sample"
    assert document.created_at is not None


@pytest.mark.django_db
def test_deleting_a_document_deletes_its_file(docx_file):
    """Requirement: deleting a row does not leave an orphan .docx in media."""
    document = Document.objects.create(title="Temp", file=docx_file(name="temp.docx"))
    path = Path(document.file.path)
    assert path.exists()

    document.delete()

    assert not path.exists()


@pytest.mark.django_db
def test_replacing_a_file_deletes_the_old_one(docx_file):
    """Requirement: editing the upload removes the replaced file."""
    document = Document.objects.create(title="Temp", file=docx_file(name="old.docx"))
    old_path = Path(document.file.path)

    document.file = docx_file(name="new.docx")
    document.save()

    assert not old_path.exists()
    assert Path(document.file.path).exists()


def test_validator_rejects_non_docx():
    """Requirement: only .docx documents are accepted."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    with pytest.raises(ValidationError, match=".docx"):
        validate_docx_file(SimpleUploadedFile("notes.pdf", b"%PDF-1.4"))


def test_validator_accepts_docx(docx_file):
    """Requirement: .docx uploads pass validation."""
    validate_docx_file(docx_file(name="REPORT.DOCX"))  # extension is case-insensitive


def test_validator_rejects_oversized_file(settings, docx_file):
    """Requirement: uploads have a file size limit."""
    settings.MAX_DOCUMENT_SIZE_MB = 0
    with pytest.raises(ValidationError, match="too large"):
        validate_docx_file(docx_file())


def _zip_bytes(entries):
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_validator_rejects_a_renamed_file():
    """Requirement: a .docx name is not enough; the file must be a ZIP."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    with pytest.raises(ValidationError, match="not a ZIP archive"):
        validate_docx_file(SimpleUploadedFile("fake.docx", b"not a zip at all"))


def test_validator_rejects_a_zip_that_is_not_a_word_document():
    """Requirement: ordinary ZIP archives are not accepted as documents."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    data = _zip_bytes({"readme.txt": "hello"})
    with pytest.raises(ValidationError, match="not a Word document"):
        validate_docx_file(SimpleUploadedFile("archive.docx", data))


def test_validator_rejects_a_zip_bomb(settings):
    """Requirement: a tiny upload cannot expand into a huge document."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.MAX_DOCUMENT_SIZE_MB = 0.05  # 50 KiB -> 1 MiB expanded allowance
    data = _zip_bytes({"word/document.xml": b"\0" * 2_000_000})
    with pytest.raises(ValidationError, match="unexpectedly large"):
        validate_docx_file(SimpleUploadedFile("bomb.docx", data))
