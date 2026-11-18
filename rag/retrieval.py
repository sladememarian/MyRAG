"""Retrieval: MMR for diversity + multi-query rewriting for recall.

Why this is "advanced": a single similarity search often misses chunks that use
different wording, and returns several near-identical chunks. Multi-query
rewriting asks the LLM for a few paraphrases of the question (better recall),
MMR then picks chunks that are both relevant and different from each other
(less redundancy). A cross-encoder reranker would add a second, more precise
relevance pass on top of these candidates, but is intentionally out of scope.
"""
import logging

from django.conf import settings
from langchain_core.documents import Document as LangchainDocument
from langchain_core.prompts import PromptTemplate
from langchain.retrievers.multi_query import MultiQueryRetriever

from rag.llm import get_llm
from rag.vectorstore import get_vectorstore

logger = logging.getLogger(__name__)


def retrieve(question: str, k: int | None = None, fetch_k: int | None = None) -> list[LangchainDocument]:
    """Return relevant chunks (with a `score` in metadata) for a question."""
    question = (question or "").strip()
    if not question:
        return []

    k = k or settings.RETRIEVAL_K
    fetch_k = max(fetch_k or settings.RETRIEVAL_FETCH_K, k)

    store = get_vectorstore()
    base_retriever = store.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": k,
            "fetch_k": fetch_k,
            "lambda_mult": settings.RETRIEVAL_LAMBDA,
        },
    )

    if settings.RETRIEVAL_USE_MULTI_QUERY:
        documents = _search_with_multi_query(question, base_retriever)
    else:
        documents = base_retriever.invoke(question)

    documents = _deduplicate(documents)[:k]
    return _attach_relevance_scores(question, documents, store, fetch_k)


def _search_with_multi_query(question: str, base_retriever) -> list[LangchainDocument]:
    """Rewrite the question with the LLM; fall back to plain MMR on any error."""
    try:
        prompt = PromptTemplate.from_template(
            "Rewrite the following question into "
            f"{settings.MULTI_QUERY_COUNT} different, short search queries. "
            "Use synonyms and different wording, but keep the original language. "
            "Return one query per line, with no numbering and no extra text.\n\n"
            "Question: {question}\nQueries:"
        )
        retriever = MultiQueryRetriever.from_llm(
            llm=get_llm(temperature=0),
            retriever=base_retriever,
            prompt=prompt,
            include_original=True,
        )
        return retriever.invoke(question)
    except Exception as exc:  # noqa: BLE001 - retrieval must still work
        logger.warning("Multi-query rewriting failed, using plain MMR: %s", exc)
        return base_retriever.invoke(question)


def _chunk_key(document: LangchainDocument) -> tuple:
    metadata = document.metadata or {}
    return (metadata.get("document_id"), metadata.get("chunk_index"), document.page_content[:40])


def _deduplicate(documents: list[LangchainDocument]) -> list[LangchainDocument]:
    """Keep the first occurrence of each chunk, preserving relevance order."""
    seen: set[tuple] = set()
    unique: list[LangchainDocument] = []
    for document in documents:
        key = _chunk_key(document)
        if key not in seen:
            seen.add(key)
            unique.append(document)
    return unique


def _attach_relevance_scores(question, documents, store, fetch_k):
    """Score the selected chunks and drop ones below the relevance threshold.

    MMR optimises diversity and does not expose per-document scores, so we run
    one extra cheap similarity query and look the scores up by chunk identity.
    If scoring fails, every document is kept: a missing score must not hide
    valid evidence.
    """
    if not documents:
        return []

    scores: dict[tuple, float] = {}
    try:
        scored = store.similarity_search_with_score(
            question, k=max(fetch_k, len(documents))
        )
        scores = {
            _chunk_key(document): _relevance_from_cosine_distance(float(distance))
            for document, distance in scored
        }
    except Exception as exc:  # noqa: BLE001 - scores are informative, not critical
        logger.warning("Could not compute relevance scores: %s", exc)

    enriched = []
    for document in documents:
        metadata = dict(document.metadata or {})
        metadata["score"] = round(scores.get(_chunk_key(document), 0.0), 4)
        enriched.append(
            LangchainDocument(page_content=document.page_content, metadata=metadata)
        )

    if not scores:
        return enriched

    threshold = settings.RETRIEVAL_MIN_SCORE
    return [doc for doc in enriched if doc.metadata["score"] >= threshold]


def _relevance_from_cosine_distance(distance: float) -> float:
    """Turn a Chroma cosine distance into an intuitive 0..1 relevance score.

    Cosine distance is 0 for identical vectors and 2 for opposite ones, so
    ``1 - distance`` is the cosine similarity, clamped to 0 (unrelated) .. 1.
    """
    return round(min(1.0, max(0.0, 1.0 - distance)), 4)
