"""Split document text into chunks and keep Chroma in sync with the database."""
import logging

from django.conf import settings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.vectorstore import get_vectorstore

logger = logging.getLogger(__name__)

# Persian-aware separators: paragraph, line, sentence enders, comma, space.
SEPARATORS = ["\n\n", "\n", "۔ ", ". ", "؟ ", "? ", "! ", "؛ ", "، ", " ", ""]


def split_text(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=SEPARATORS,
        keep_separator=False,
    )
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]


def index_document(document) -> int:
    """Delete old chunks for this document, then store fresh ones.

    Chunk ids are deterministic (`doc<id>-chunk<n>`), and old chunks are
    removed first, so editing a document never creates duplicates.
    Returns the number of stored chunks.
    """
    delete_document(document.pk)

    chunks = split_text(document.full_text or "")
    if not chunks:
        logger.warning("Document %s has no text to index", document.pk)
        return 0

    ids = [f"doc{document.pk}-chunk{index}" for index in range(len(chunks))]
    metadatas = [
        {
            "document_id": document.pk,
            "title": document.title,
            "chunk_index": index,
        }
        for index in range(len(chunks))
    ]
    get_vectorstore().add_texts(texts=chunks, metadatas=metadatas, ids=ids)
    logger.info("Indexed document %s into %s chunk(s)", document.pk, len(chunks))
    return len(chunks)


def delete_document(document_id: int) -> int:
    """Remove every chunk that belongs to a document. Returns chunks removed."""
    store = get_vectorstore()
    existing = store.get(where={"document_id": document_id}, include=["metadatas"])
    ids = existing.get("ids") or []
    if ids:
        store.delete(ids=ids)
    logger.info("Removed %s chunk(s) for document %s", len(ids), document_id)
    return len(ids)
