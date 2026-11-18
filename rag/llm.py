"""OpenRouter chat model factory (OpenAI-compatible endpoint)."""
import logging

import httpx
from django.conf import settings
from langchain_openai import ChatOpenAI

from rag.errors import LLMConfigurationError

logger = logging.getLogger(__name__)


def _chat_base_url() -> str:
    """Return the API root expected by ChatOpenAI.

    ChatOpenAI uses the chat-completions protocol. If someone configures the
    OpenRouter /responses endpoint (or a full /chat/completions URL), strip the
    suffix instead of failing with a confusing 404.
    """
    base_url = settings.OPENROUTER_BASE_URL.rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if base_url.endswith(suffix):
            logger.warning(
                "OPENROUTER_BASE_URL should be the API root; removing '%s'", suffix
            )
            base_url = base_url[: -len(suffix)]
    return base_url


def get_llm(temperature: float | None = None) -> ChatOpenAI:
    """Build a ChatOpenAI client pointed at OpenRouter.

    OPENROUTER_BASE_URL must be the API root (https://openrouter.ai/api/v1),
    not the /responses endpoint: LangChain here uses chat completions.
    """
    if not settings.OPENROUTER_API_KEY:
        raise LLMConfigurationError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file and restart."
        )

    kwargs = {
        "model": settings.OPENROUTER_MODEL,
        "api_key": settings.OPENROUTER_API_KEY,
        "base_url": _chat_base_url(),
        "temperature": settings.OPENROUTER_TEMPERATURE if temperature is None else temperature,
        "timeout": settings.OPENROUTER_TIMEOUT,
        "max_tokens": settings.OPENROUTER_MAX_TOKENS,
        "max_retries": 2,
        "default_headers": {"X-Title": settings.OPENROUTER_APP_NAME},
    }

    if settings.OPENROUTER_PROXY:
        # Optional proxy for restricted networks. Use host.docker.internal
        # instead of 127.0.0.1 when the app runs inside Docker.
        kwargs["http_client"] = httpx.Client(
            proxy=settings.OPENROUTER_PROXY, timeout=settings.OPENROUTER_TIMEOUT
        )
        kwargs["http_async_client"] = httpx.AsyncClient(
            proxy=settings.OPENROUTER_PROXY, timeout=settings.OPENROUTER_TIMEOUT
        )

    return ChatOpenAI(**kwargs)
