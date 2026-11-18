"""Shared document services used by both Django Admin and the REST API.

Keeping this here means admin and API can never drift apart: both call
`process_document` and `delete_document_index`.
"""
import logging

from rag.errors import DocumentExtractionError
from rag.extract import extract_text
from rag.ingest import delete_document, index_document

logger = logging.getLogger(__name__)


def process_document(document) -> int:
    """Extract the .docx text, save it, and rebuild the document's chunks.

    Returns the number of chunks. On failure the document is marked as not
    indexed and the exception is re-raised for the caller to report.
    """
    from documents.models import Document  # local import avoids a circular import

    if not document.file:
        raise DocumentExtractionError("The document has no uploaded file.")

    try:
        text = extract_text(document.file.path)
    except Exception:
        # The file cannot be read, so any old chunks no longer match the
        # document. Remove them instead of leaving unreachable stale text.
        delete_document_index(document.pk, ignore_errors=True)
        Document.objects.filter(pk=document.pk).update(full_text="", indexed=False)
        document.full_text = ""
        document.indexed = False
        raise

    # Save the text before indexing so a failure still leaves the text visible.
    Document.objects.filter(pk=document.pk).update(full_text=text, indexed=False)
    document.full_text = text

    try:
        chunks = index_document(document)
    except Exception:
        document.indexed = False
        raise

    document.indexed = chunks > 0
    Document.objects.filter(pk=document.pk).update(indexed=document.indexed)
    logger.info("Processed document %s (%s chunks)", document.pk, chunks)
    return chunks


def delete_document_index(document_id: int, *, ignore_errors: bool = False) -> int:
    """Remove a document's chunks from Chroma (safe if it was never indexed).

    By default an indexing failure is re-raised: deleting the database row
    while its chunks remain would leave unreachable vectors that still answer
    questions. Pass `ignore_errors=True` for best-effort cleanup paths.
    """
    try:
        return delete_document(document_id)
    except Exception:  # noqa: BLE001 - callers decide whether to continue
        logger.exception("Could not delete chunks for document %s", document_id)
        if ignore_errors:
            return 0
        raise
