"""Small, explicit exception types so each layer can report a clear message."""


class RAGError(Exception):
    """Base class for all expected pipeline errors."""


class DocumentExtractionError(RAGError):
    """The .docx file could not be read or contains no usable text."""


class RetrievalError(RAGError):
    """The vector store or embedding model could not be queried."""


class NoRelevantContentError(RAGError):
    """No chunks were retrieved for the question."""


class LLMError(RAGError):
    """The OpenRouter call failed (network, timeout, rate limit, empty answer)."""


class LLMConfigurationError(LLMError):
    """The LLM is not configured (for example a missing API key)."""
