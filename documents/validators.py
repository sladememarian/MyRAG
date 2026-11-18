"""Upload validators for document files."""
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

DOCX_CONTENT_TYPES = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)


def validate_docx_file(file) -> None:
    """Accept only .docx files that are not larger than MAX_DOCUMENT_SIZE_MB."""
    name = getattr(file, "name", "") or ""
    if Path(name).suffix.lower() != ".docx":
        raise ValidationError("Only Microsoft Word files with the .docx extension are supported.")

    size = getattr(file, "size", None)
    limit = settings.MAX_DOCUMENT_SIZE_MB * 1024 * 1024
    if size is not None and size > limit:
        raise ValidationError(
            f"File is too large ({size / (1024 * 1024):.1f} MB). "
            f"The maximum allowed size is {settings.MAX_DOCUMENT_SIZE_MB} MB."
        )
