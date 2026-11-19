"""Upload validators for document files."""
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

DOCX_CONTENT_TYPES = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)
# A .docx is a ZIP; refuse archives that expand to hundreds of times the upload
# limit (a small file could otherwise exhaust memory inside python-docx).
MAX_UNCOMPRESSED_FACTOR = 20


def validate_docx_file(file) -> None:
    """Accept only real .docx files that are not larger than the size limit."""
    name = getattr(file, "name", "") or ""
    if Path(name).suffix.lower() != ".docx":
        raise ValidationError(
            "Only Microsoft Word files with the .docx extension are supported."
        )

    size = getattr(file, "size", None)
    limit = settings.MAX_DOCUMENT_SIZE_MB * 1024 * 1024
    if size is not None and size > limit:
        raise ValidationError(
            f"File is too large ({size / (1024 * 1024):.1f} MB). "
            f"The maximum allowed size is {settings.MAX_DOCUMENT_SIZE_MB} MB."
        )

    _validate_archive(file, limit)


def _validate_archive(file, limit: int) -> None:
    """Reject renamed files and zip bombs before python-docx parses them."""
    try:
        position = file.tell()
    except (AttributeError, OSError):
        position = 0
    try:
        if file.read(2) != b"PK":
            raise ValidationError(
                "This file is not a valid .docx document (not a ZIP archive)."
            )
        file.seek(0)
        try:
            with zipfile.ZipFile(file) as archive:
                names = set(archive.namelist())
                if "word/document.xml" not in names:
                    raise ValidationError(
                        "This ZIP file is not a Word document (.docx)."
                    )
                expanded = sum(info.file_size for info in archive.infolist())
        except zipfile.BadZipFile as exc:
            raise ValidationError(
                "This file is not a valid .docx document (damaged archive)."
            ) from exc
    except (AttributeError, OSError):
        # A stream that cannot be rewound is left to python-docx to validate.
        return
    finally:
        try:
            file.seek(position)
        except (AttributeError, OSError):
            pass

    if expanded > limit * MAX_UNCOMPRESSED_FACTOR:
        raise ValidationError(
            "This .docx expands to an unexpectedly large size and was rejected."
        )
