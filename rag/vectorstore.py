"""Embedding model and persistent Chroma vector store factories."""
import logging
import os
from functools import lru_cache

from django.conf import settings
from langchain_chroma import Chroma

logger = logging.getLogger(__name__)


def get_embeddings():
    """Return the configured embeddings object.

    The fake backend produces deterministic vectors, which keeps the test suite
    fast and completely offline. The real backend is a local multilingual
    sentence-transformers model (documents may be Persian).
    """
    return _build_embeddings(
        settings.EMBEDDING_BACKEND,
        settings.EMBEDDING_MODEL,
        settings.EMBEDDING_DEVICE,
        settings.EMBEDDING_FAKE_DIM,
    )


@lru_cache(maxsize=4)
def _build_embeddings(backend: str, model_name: str, device: str, fake_dim: int):
    if backend == "fake":
        from langchain_core.embeddings.fake import DeterministicFakeEmbedding

        logger.info("Using deterministic fake embeddings (dim=%s)", fake_dim)
        return DeterministicFakeEmbedding(size=fake_dim)

    from langchain_huggingface import HuggingFaceEmbeddings

    logger.info("Loading local embedding model %s on %s", model_name, device)
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True},
    )


def get_vectorstore() -> Chroma:
    """Open (creating it if needed) the persistent Chroma collection."""
    import chromadb.config

    os.makedirs(settings.CHROMA_DIR, exist_ok=True)
    return Chroma(
        collection_name=settings.CHROMA_COLLECTION,
        embedding_function=get_embeddings(),
        persist_directory=settings.CHROMA_DIR,
        collection_metadata={"hnsw:space": "cosine"},
        # No telemetry: keeps tests offline and startup quiet.
        client_settings=chromadb.config.Settings(anonymized_telemetry=False),
    )
