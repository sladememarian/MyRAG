"""Tests for LLM configuration and friendly error messages."""
import pytest

from rag.chain import friendly_llm_error
from rag.errors import LLMConfigurationError
from rag.llm import _chat_base_url, get_llm


def test_base_url_strips_the_responses_endpoint(settings):
    """Requirement: OpenRouter is called with the correct OpenAI-compatible root."""
    settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/responses"
    assert _chat_base_url() == "https://openrouter.ai/api/v1"


def test_base_url_strips_a_full_chat_completions_url(settings):
    """Requirement: misconfigured base URLs are corrected instead of 404ing."""
    settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions/"
    assert _chat_base_url() == "https://openrouter.ai/api/v1"


def test_missing_api_key_is_reported(settings):
    """Requirement: the API key comes from env and is validated."""
    settings.OPENROUTER_API_KEY = ""
    with pytest.raises(LLMConfigurationError, match="OPENROUTER_API_KEY"):
        get_llm()


def test_llm_is_configured_from_settings(settings):
    """Requirement: model, base URL and timeout come from configuration."""
    settings.OPENROUTER_API_KEY = "test-key"
    settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    settings.OPENROUTER_MODEL = "provider/model:free"

    llm = get_llm()

    assert llm.model_name == "provider/model:free"


def test_rate_limit_message_is_actionable():
    """Requirement: rate limit failures produce a clear message."""
    message = friendly_llm_error(RuntimeError("Error code: 429 - rate limit"))
    assert "rate-limited" in message
    assert "OPENROUTER_MODEL" in message


def test_timeout_and_auth_messages_are_specific():
    """Requirement: timeouts and bad keys are distinguished."""
    assert "did not answer in time" in friendly_llm_error(RuntimeError("timed out"))
    assert "rejected the API key" in friendly_llm_error(RuntimeError("401 Unauthorized"))
