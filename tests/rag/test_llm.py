"""Tests for LLM provider selection, proxy resolution and key failover."""
import pytest

from rag.chain import friendly_llm_error
from rag.errors import LLMConfigurationError
from rag.llm import (
    FailoverChatModel,
    LLMTarget,
    _chat_base_url,
    active_model_label,
    active_model_slug,
    candidate_targets,
    get_llm,
    proxy_url,
)


def _target(name: str) -> LLMTarget:
    return LLMTarget(
        provider="openrouter",
        model=name,
        base_url="https://openrouter.ai/api/v1",
        api_key=f"key-{name}",
        key_label=name,
    )


def test_base_url_strips_the_responses_endpoint(settings):
    """Requirement: fixed provider roots stop at /v1, not at /responses."""
    settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/responses"
    assert _chat_base_url() == "https://openrouter.ai/api/v1"


def test_base_url_strips_a_full_chat_completions_url(settings):
    """Requirement: misconfigured base URLs are corrected instead of 404ing."""
    settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions/"
    assert _chat_base_url() == "https://openrouter.ai/api/v1"


@pytest.mark.django_db
def test_missing_api_key_is_reported(settings):
    """Requirement: a provider without any key is rejected with instructions."""
    settings.OPENROUTER_API_KEY = ""
    settings.ITERACOMPUTE_API_KEY = ""
    with pytest.raises(LLMConfigurationError, match="OPENROUTER_API_KEY"):
        get_llm()


@pytest.mark.django_db
def test_llm_is_configured_from_settings(settings):
    """Requirement: model, base URL and timeout come from configuration."""
    settings.OPENROUTER_API_KEY = "test-key"
    settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    settings.OPENROUTER_MODEL = "provider/model:free"

    llm = get_llm()

    assert llm.model_name == "provider/model:free"


@pytest.mark.django_db
def test_admin_selected_model_overrides_the_configured_default(settings):
    """Requirement: the model chosen in Model Management answers questions."""
    from providers.models import LLMModel, Provider

    settings.OPENROUTER_API_KEY = "test-key"
    settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    settings.OPENROUTER_MODEL = "provider/default:free"
    openrouter = Provider.objects.get(slug="openrouter")
    LLMModel.objects.create(
        provider=openrouter, slug="provider/picked:free", is_active=True
    )

    assert active_model_slug() == "provider/picked:free"
    assert get_llm().model_name == "provider/picked:free"


@pytest.mark.django_db
def test_inactive_models_are_ignored(settings):
    """Requirement: only the selected model changes the pipeline."""
    from providers.models import LLMModel, Provider

    settings.OPENROUTER_MODEL = "provider/default:free"
    openrouter = Provider.objects.get(slug="openrouter")
    LLMModel.objects.create(provider=openrouter, slug="provider/spare:free")

    assert active_model_slug() == "provider/default:free"


@pytest.mark.django_db
def test_itera_model_keeps_its_provider_prefix(settings):
    """Requirement: a model id is only ambiguous when its provider is not OpenRouter."""
    from providers.models import LLMModel, Provider

    itera = Provider.objects.get(slug="iteracompute")
    LLMModel.objects.create(provider=itera, slug="Auto", is_active=True)
    settings.ITERACOMPUTE_API_KEY = "itera-key"

    assert active_model_slug() == "iteracompute/Auto"
    assert "Itera Compute" in active_model_label()
    llm = get_llm()
    assert llm.model_name == "iteracompute/Auto"
    assert llm.targets[0].model == "Auto"


@pytest.mark.django_db
def test_database_keys_are_used_before_the_env_key(settings):
    """Requirement: keys added in the admin take precedence over .env."""
    from providers.models import APIKey, LLMModel, Provider

    settings.OPENROUTER_API_KEY = "env-key"
    openrouter = Provider.objects.get(slug="openrouter")
    LLMModel.objects.create(provider=openrouter, slug="picked", is_active=True)
    key = APIKey(provider=openrouter, label="primary", priority=10)
    key.set_secret("stored-key")
    key.save()

    targets = candidate_targets()

    assert [target.api_key for target in targets] == ["stored-key"]
    assert targets[0].key_label == "primary"


@pytest.mark.django_db
def test_keys_are_ordered_by_priority(settings):
    """Requirement: failover follows the priority configured in the admin."""
    from providers.models import APIKey, LLMModel, Provider

    openrouter = Provider.objects.get(slug="openrouter")
    LLMModel.objects.create(provider=openrouter, slug="picked", is_active=True)
    for label, priority in (("backup", 50), ("primary", 10)):
        key = APIKey(provider=openrouter, label=label, priority=priority)
        key.set_secret(f"key-{label}")
        key.save()

    assert [target.key_label for target in candidate_targets()] == [
        "primary",
        "backup",
    ]


def test_proxy_prefers_a_full_url(settings):
    """Requirement: LLM_PROXY wins over the scheme/host/port parts."""
    settings.IN_DOCKER = False
    settings.LLM_PROXY = "http://127.0.0.1:14927"
    settings.LLM_PROXY_HOST = "10.0.0.5"
    settings.LLM_PROXY_PORT = "8080"

    assert proxy_url() == "http://127.0.0.1:14927"


def test_proxy_can_be_changed_by_editing_the_port(settings):
    """Requirement: the proxy port is changeable through .env only."""
    settings.LLM_PROXY = ""
    settings.LLM_PROXY_SCHEME = "http"
    settings.LLM_PROXY_HOST = "127.0.0.1"
    settings.LLM_PROXY_PORT = "14927"
    settings.IN_DOCKER = False

    assert proxy_url() == "http://127.0.0.1:14927"


def test_socks5_proxy_is_supported(settings):
    """Requirement: a SOCKS5 proxy can be configured in .env."""
    settings.IN_DOCKER = False
    settings.LLM_PROXY = "socks5://127.0.0.1:14926"
    settings.LLM_PROXY_HOST = ""
    settings.LLM_PROXY_PORT = ""

    assert proxy_url() == "socks5://127.0.0.1:14926"


def test_loopback_proxy_is_rewritten_inside_docker(settings):
    """Requirement: 127.0.0.1 works unchanged in Docker despite the container."""
    settings.IN_DOCKER = True
    settings.LLM_PROXY = "socks5://127.0.0.1:14926"
    settings.LLM_PROXY_HOST = ""
    settings.LLM_PROXY_PORT = ""

    assert proxy_url() == "socks5://host.docker.internal:14926"


def test_empty_proxy_means_a_direct_connection(settings):
    """Requirement: leaving the proxy variables empty disables the proxy."""
    settings.LLM_PROXY = ""
    settings.LLM_PROXY_HOST = ""
    settings.LLM_PROXY_PORT = ""
    settings.OPENROUTER_PROXY = ""

    assert proxy_url() == ""


def test_unsupported_proxy_scheme_is_rejected(settings):
    """Requirement: only http(s) and SOCKS proxies are accepted from .env."""
    settings.IN_DOCKER = False
    settings.LLM_PROXY = "ftp://127.0.0.1:21"

    with pytest.raises(LLMConfigurationError, match="proxy scheme"):
        proxy_url()


def test_failover_tries_the_next_key_for_a_retryable_error(monkeypatch):
    """Requirement: a rate-limited key does not fail the question if a backup exists."""
    calls = []

    class RateLimited(Exception):
        status_code = 429

    class FakeChat:
        def __init__(self, name, fail=False):
            self.name = name
            self.fail = fail

        def invoke(self, messages, **kwargs):
            calls.append(self.name)
            if self.fail:
                raise RateLimited("429")
            return f"answer from {self.name}"

    monkeypatch.setattr(
        "rag.llm._build_chat",
        lambda target, temperature=None: FakeChat(target.model, target.key_label == "a"),
    )

    result = FailoverChatModel([_target("a"), _target("b")]).invoke("question")

    assert result == "answer from b"
    # The failing key is retried LLM_KEY_ATTEMPTS times before moving on.
    assert calls == ["a", "a", "a", "b"]


def test_transient_error_recovers_on_the_same_key(monkeypatch):
    """Requirement: one 429 or empty reply is retried, not surfaced."""
    from types import SimpleNamespace

    replies = iter(["", "real answer"])

    class FakeChat:
        def invoke(self, messages, **kwargs):
            return SimpleNamespace(content=next(replies))

    monkeypatch.setattr("rag.llm._build_chat", lambda target, temperature=None: FakeChat())

    result = FailoverChatModel([_target("a")]).invoke("question")

    assert result.content == "real answer"


def test_key_problem_skips_to_next_key_without_retrying(monkeypatch):
    """Requirement: a rejected key (401/402/403) is not retried."""
    calls = []

    class Rejected(Exception):
        status_code = 402

    class FakeChat:
        def __init__(self, label):
            self.label = label

        def invoke(self, messages, **kwargs):
            calls.append(self.label)
            if self.label == "a":
                raise Rejected("402")
            return "ok"

    monkeypatch.setattr(
        "rag.llm._build_chat",
        lambda target, temperature=None: FakeChat(target.key_label),
    )

    assert FailoverChatModel([_target("a"), _target("b")]).invoke("q") == "ok"
    assert calls == ["a", "b"]


def test_free_model_detection():
    from rag.llm import is_free_model

    assert is_free_model({"id": "x/y:free"})
    assert is_free_model({"id": "orcarouter/free"})
    assert is_free_model({"id": "a/b", "pricing": {"prompt": "0", "completion": "0.0"}})
    assert not is_free_model({"id": "a/b", "pricing": {"prompt": "0", "completion": "0.1"}})
    assert not is_free_model({"id": "a/b"})


def test_failover_does_not_hide_a_permanent_error(monkeypatch):
    """Requirement: a bad request is reported instead of burning every key."""
    calls = []

    class BadRequest(Exception):
        status_code = 400

    class FakeChat:
        def invoke(self, messages, **kwargs):
            calls.append("called")
            raise BadRequest("400")

    monkeypatch.setattr("rag.llm._build_chat", lambda target, temperature=None: FakeChat())

    with pytest.raises(BadRequest):
        FailoverChatModel([_target("a"), _target("b")]).invoke("question")

    assert calls == ["called"]


def test_rate_limit_message_is_actionable():
    """Requirement: rate limit failures produce a clear message."""
    message = friendly_llm_error(RuntimeError("Error code: 429 - rate limit"))
    assert "rate-limited" in message
    assert "Model Management" in message


def test_timeout_and_auth_messages_are_specific():
    """Requirement: timeouts and bad keys are distinguished."""
    assert "did not answer in time" in friendly_llm_error(RuntimeError("timed out"))
    assert "rejected the API key" in friendly_llm_error(RuntimeError("401 Unauthorized"))
