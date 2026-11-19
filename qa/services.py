"""Question-answering service shared by admin, REST API and tests."""
import logging

from rag.chain import answer_question
from rag.errors import LLMError, NoRelevantContentError, RAGError
from rag.llm import active_model_slug

logger = logging.getLogger(__name__)

# Unexpected exceptions can contain paths, SQL or provider details. Log the
# full error, but store and return this safe message instead.
UNEXPECTED_ERROR_MESSAGE = (
    "An unexpected error occurred while answering the question. "
    "Please try again or check the server logs."
)


def answer_query(query):
    """Fill an unsaved Query via the RAG chain and save it.

    Errors are stored on the record instead of raised, so question history
    never loses a failed attempt. `failure_kind` is persisted so the API can
    choose an HTTP status without a runtime-only attribute.
    """
    query.model_name = active_model_slug()
    query.failure_kind = ""

    try:
        result = answer_question(query.question)
    except RAGError as exc:
        # Expected errors already carry a user-facing message.
        _mark_failed(query, str(exc), _failure_kind(exc))
    except Exception as exc:  # noqa: BLE001 - record unexpected failures too
        logger.exception("Unexpected error while answering a question")
        _mark_failed(query, UNEXPECTED_ERROR_MESSAGE, "other")
    else:
        query.answer = result["answer"]
        query.sources = result["sources"]
        query.model_name = result["model_name"]
        query.status = query.STATUS_OK
        query.error_message = ""
        query.failure_kind = ""

    query.save()
    return query


def run_query(question: str, user=None):
    """Create and answer a new Query record owned by `user` (if given)."""
    from qa.models import Query

    return answer_query(Query(question=question, user=user))


def _failure_kind(exc: Exception) -> str:
    if isinstance(exc, NoRelevantContentError):
        return "no_content"
    if isinstance(exc, LLMError):
        return "llm"
    return "other"


def _mark_failed(query, message: str, failure_kind: str) -> None:
    logger.warning("Question failed (%s): %s", failure_kind, message)
    query.answer = ""
    query.sources = []
    query.status = query.STATUS_ERROR
    query.error_message = message
    query.failure_kind = failure_kind
