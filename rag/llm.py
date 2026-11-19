"""Chat-model factory with provider selection, key rotation and proxy support.

The admin stores providers, API keys and models in the database. This module
resolves the active model on every question, builds an OpenAI-compatible client
for the right provider, and rotates through the provider's keys when one of them
is rate-limited, rejected or unreachable. ``OPENROUTER_*`` in ``.env`` remains
the fallback so a fresh checkout works before anything is configured.
"""
import logging
import time
from dataclasses import dataclass, replace
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

import httpx
from django.conf import settings
from django.utils import timezone
from langchain_openai import ChatOpenAI

from providers.constants import (
    API_KEY_ENV,
    BASE_URL_ENV,
    DEFAULT_BASE_URLS,
    DEFAULT_MODELS,
    MODEL_ENV,
    OPENROUTER,
    PROVIDER_NAMES,
)
from rag.errors import LLMConfigurationError

logger = logging.getLogger(__name__)

ALLOWED_PROXY_SCHEMES = {"http", "https", "socks4", "socks5", "socks5h"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}  # nosec B104 - a proxy host, not a bind address


@dataclass(frozen=True)
class LLMTarget:
    """One concrete (provider, model, key) combination to try."""

    provider: str
    model: str
    base_url: str
    api_key: str
    key_label: str = ""
    key_id: int | None = None

    @property
    def slug(self) -> str:
        if self.provider == OPENROUTER:
            return self.model
        return f"{self.provider}/{self.model}"

    @property
    def provider_name(self) -> str:
        return PROVIDER_NAMES.get(self.provider, self.provider.title())


def _strip_endpoint(base_url: str) -> str:
    """Remove /chat/completions or /responses from a configured API root."""
    base_url = (base_url or "").rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if base_url.endswith(suffix):
            logger.warning("Base URL should be the API root; removing '%s'", suffix)
            base_url = base_url[: -len(suffix)]
    return base_url


def _chat_base_url(url: str | None = None) -> str:
    """Return the API root expected by ChatOpenAI."""
    return _strip_endpoint(
        url if url is not None else getattr(settings, "OPENROUTER_BASE_URL", "")
    )


def proxy_url() -> str:
    """Resolve the outbound proxy from settings, rewriting loopback in Docker.

    Priority: ``LLM_PROXY`` (full URL) > ``LLM_PROXY_SCHEME/HOST/PORT`` >
    legacy ``OPENROUTER_PROXY``. Returns "" when no proxy is configured.
    """
    raw = (getattr(settings, "LLM_PROXY", "") or "").strip()
    if not raw:
        host = (getattr(settings, "LLM_PROXY_HOST", "") or "").strip()
        port = str(getattr(settings, "LLM_PROXY_PORT", "") or "").strip()
        if host and port:
            scheme = (getattr(settings, "LLM_PROXY_SCHEME", "") or "http").strip()
            raw = f"{scheme}://{host}:{port}"
    if not raw:
        raw = (getattr(settings, "OPENROUTER_PROXY", "") or "").strip()
    if not raw:
        return ""

    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_PROXY_SCHEMES:
        raise LLMConfigurationError(
            f"Unsupported proxy scheme '{scheme}'. Use http:// or socks5:// in .env."
        )
    host = parsed.hostname
    if not host:
        raise LLMConfigurationError("The configured LLM proxy has no host name.")
    if getattr(settings, "IN_DOCKER", False) and host in LOOPBACK_HOSTS:
        # 127.0.0.1 inside the container is the container itself; the proxy runs
        # on the host. This saves editing the host every time the proxy changes.
        host = "host.docker.internal"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    if parsed.username:
        credentials = parsed.username
        if parsed.password:
            credentials = f"{credentials}:{parsed.password}"
        netloc = f"{credentials}@{netloc}"
    return urlunparse((scheme, netloc, parsed.path, "", parsed.query, ""))


def _env_key(provider_slug: str) -> str:
    env_name = API_KEY_ENV.get(provider_slug, "")
    return getattr(settings, env_name, "") if env_name else ""


def _env_model(provider_slug: str) -> str:
    env_name = MODEL_ENV.get(provider_slug, "")
    configured = getattr(settings, env_name, "") if env_name else ""
    return configured or DEFAULT_MODELS.get(provider_slug, "")


def _env_base_url(provider_slug: str) -> str:
    env_name = BASE_URL_ENV.get(provider_slug, "")
    configured = getattr(settings, env_name, "") if env_name else ""
    return _strip_endpoint(configured or DEFAULT_BASE_URLS.get(provider_slug, ""))


def _active_row():
    """Return the active LLMModel row, tolerating an unmigrated database."""
    try:
        from providers.models import LLMModel

        return (
            LLMModel.objects.select_related("provider")
            .filter(is_active=True, provider__is_enabled=True)
            .first()
        )
    except Exception:  # noqa: BLE001 - no DB yet, or migrations not applied
        logger.debug("Could not read the selected model; using settings", exc_info=True)
        return None


def _targets_for(provider_slug: str, model: str, base_url: str) -> list[LLMTarget]:
    """Active database keys for a provider, or the .env key as a fallback."""
    targets: list[LLMTarget] = []
    try:
        from providers.models import APIKey

        keys = APIKey.objects.filter(
            provider__slug=provider_slug, is_active=True
        ).order_by("priority", "id")
        for key in keys:
            raw = key.get_secret()
            if not raw:
                logger.warning(
                    "API key %s for %s cannot be decrypted; re-enter it in the admin",
                    key.pk,
                    provider_slug,
                )
                continue
            targets.append(
                LLMTarget(
                    provider=provider_slug,
                    model=model,
                    base_url=base_url,
                    api_key=raw,
                    key_label=key.label or key.masked,
                    key_id=key.pk,
                )
            )
    except Exception:  # noqa: BLE001 - migrations/DB unavailable
        logger.debug("Could not read database API keys", exc_info=True)

    if targets:
        return targets

    env_key = _env_key(provider_slug)
    if env_key:
        return [
            LLMTarget(
                provider=provider_slug,
                model=model,
                base_url=base_url,
                api_key=env_key,
                key_label=f"{API_KEY_ENV.get(provider_slug, 'API key')} (env)",
            )
        ]
    return []


def candidate_targets() -> list[LLMTarget]:
    """Ordered list of (key) attempts for the currently selected model."""
    row = _active_row()
    if row is not None:
        targets = _targets_for(row.provider.slug, row.slug, row.provider.base_url)
        if targets:
            return targets
        raise LLMConfigurationError(
            f"{row.provider.name} has no usable API key. Add one in "
            f"Admin → Model Management → {row.provider.name}."
        )

    # Nothing selected yet: keep the documented .env behaviour.
    targets = _targets_for(
        OPENROUTER, _env_model(OPENROUTER), _env_base_url(OPENROUTER)
    )
    if targets:
        return targets
    raise LLMConfigurationError(
        "OPENROUTER_API_KEY is not set. Add it to .env, or add an API key in "
        "Admin → Model Management."
    )


def active_model_slug() -> str:
    """The model recorded on each Query (provider prefix only when not OpenRouter)."""
    row = _active_row()
    if row is not None:
        return row.qualified_slug
    return _env_model(OPENROUTER)


def active_model_label() -> str:
    """Human-readable description of the current selection for the admin."""
    row = _active_row()
    if row is not None:
        return f"{row.provider.name} — {row}"
    return f"Default from .env — {PROVIDER_NAMES[OPENROUTER]} / {active_model_slug()}"


def _headers(provider_slug: str) -> dict[str, str]:
    if provider_slug != OPENROUTER:
        return {}
    headers = {"X-Title": settings.OPENROUTER_APP_NAME}
    site_url = getattr(settings, "OPENROUTER_SITE_URL", "")
    if site_url:
        headers["HTTP-Referer"] = site_url
    return headers


@lru_cache(maxsize=4)
def _sync_client(proxy: str, timeout: float) -> httpx.Client:
    return httpx.Client(
        proxy=proxy,
        timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)),
    )


def _build_chat(
    target: LLMTarget,
    temperature: float | None = None,
    *,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> ChatOpenAI:
    """Build one ChatOpenAI client for a single (provider, model, key)."""
    request_timeout = settings.LLM_TIMEOUT if timeout is None else timeout
    kwargs = {
        "model": target.model,
        "api_key": target.api_key,
        "base_url": _chat_base_url(target.base_url),
        "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
        "timeout": request_timeout,
        "max_tokens": settings.LLM_MAX_TOKENS,
        "max_retries": settings.LLM_MAX_RETRIES if max_retries is None else max_retries,
        "default_headers": _headers(target.provider),
    }
    proxy = proxy_url()
    if proxy:
        # A shared client keeps connections pooled; httpx is thread-safe.
        kwargs["http_client"] = _sync_client(proxy, float(request_timeout))
    return ChatOpenAI(**kwargs)


class EmptyAnswerError(Exception):
    """The provider answered 200 but with no text (common on free models)."""


# Statuses where the same key is worth retrying after a short pause.
TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
# Statuses where this key is unusable (bad key, no credit, blocked region);
# retrying it is pointless, so move straight to the next key.
KEY_STATUS = {401, 402, 403}


def _status(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status


def _is_transient(exc: Exception) -> bool:
    """Worth retrying the same key: network trouble, 429/5xx, empty answer."""
    if isinstance(exc, EmptyAnswerError):
        return True
    try:
        import openai
    except Exception:  # noqa: BLE001 - the SDK is a hard dependency, but stay safe
        return False
    if isinstance(exc, (openai.APIConnectionError, openai.RateLimitError)):
        return True
    return _status(exc) in TRANSIENT_STATUS


def _is_key_problem(exc: Exception) -> bool:
    """This key cannot work right now; another key may."""
    try:
        import openai
    except Exception:  # noqa: BLE001
        return False
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return True
    return _status(exc) in KEY_STATUS


def _has_text(message) -> bool:
    if not hasattr(message, "content"):
        return True
    content = message.content
    if isinstance(content, str):
        return bool(content.strip())
    return bool(content)


class FailoverChatModel:
    """Runnable-compatible wrapper with retry, backoff and key failover.

    For each key: transient errors (429, 5xx, timeouts, empty answers) are
    retried with exponential backoff up to ``LLM_KEY_ATTEMPTS`` times; a key
    problem (401/402/403) skips straight to the next key. Errors that no key can
    fix (400, 404 unknown model) are raised immediately.
    """

    def __init__(self, targets: list[LLMTarget], temperature: float | None = None):
        self.targets = targets
        self.temperature = temperature
        self.model_name = targets[0].slug

    def invoke(self, messages, **kwargs):
        attempts = max(1, int(getattr(settings, "LLM_KEY_ATTEMPTS", 3)))
        backoff = float(getattr(settings, "LLM_RETRY_BACKOFF", 2.0))
        last_error: Exception | None = None

        for target in self.targets:
            for attempt in range(1, attempts + 1):
                try:
                    message = _build_chat(target, self.temperature).invoke(
                        messages, **kwargs
                    )
                    if not _has_text(message):
                        raise EmptyAnswerError(
                            f"{target.slug} returned an empty answer"
                        )
                    return message
                except Exception as exc:  # noqa: BLE001 - classify below
                    last_error = exc
                    if _is_key_problem(exc):
                        logger.warning(
                            "LLM key '%s' for %s rejected (%s); trying the next key",
                            target.key_label,
                            target.provider,
                            type(exc).__name__,
                        )
                        break
                    if not _is_transient(exc):
                        raise
                    if attempt == attempts:
                        logger.warning(
                            "LLM key '%s' for %s still failing after %d attempts (%s)",
                            target.key_label,
                            target.provider,
                            attempts,
                            type(exc).__name__,
                        )
                        break
                    delay = backoff * (2 ** (attempt - 1))
                    logger.info(
                        "Transient LLM error (%s); retry %d/%d in %.1fs",
                        type(exc).__name__,
                        attempt,
                        attempts - 1,
                        delay,
                    )
                    time.sleep(delay)
        raise last_error  # type: ignore[misc]  # targets is never empty


def get_llm(temperature: float | None = None, model: str | None = None):
    """Return a chat model for the selected provider, with key failover."""
    targets = candidate_targets()
    if model:
        targets = [replace(target, model=model) for target in targets]
    return FailoverChatModel(targets, temperature)


def _scrub(text: str, targets: list[LLMTarget]) -> str:
    """Remove any API key material from an error message before storing it."""
    for target in targets:
        if target.api_key:
            text = text.replace(target.api_key, "***")
    return text


def probe_provider(provider) -> tuple[list[dict], str]:
    """Send one tiny request through each active key of a provider.

    Returns ``(results, error)`` where each result reports the key label,
    duration and the (scrubbed) error. Used by the admin's Test button.
    """
    models = list(provider.models.values_list("slug", flat=True))
    model = (
        provider.models.filter(is_active=True).values_list("slug", flat=True).first()
    )
    if model is None:
        model = models[0] if models else provider.default_model
    if not model:
        return [], f"{provider.name} has no model yet. Add one in the form below."

    targets = _targets_for(provider.slug, model, provider.base_url)
    if not targets:
        return [], (
            f"{provider.name} has no usable API key. Add one in the form below, "
            f"or set {API_KEY_ENV.get(provider.slug, 'the API key')} in .env."
        )

    results: list[dict] = []
    for target in targets:
        started = time.monotonic()
        try:
            _build_chat(
                target,
                temperature=0.0,
                timeout=min(settings.LLM_TIMEOUT, 60),
                max_retries=0,
            ).invoke("Reply with the single word OK.")
            ok, error = True, ""
        except Exception as exc:  # noqa: BLE001 - reported to the admin
            ok = False
            error = _scrub(f"{type(exc).__name__}: {exc}", targets)[:300]
        elapsed_ms = int((time.monotonic() - started) * 1000)
        results.append(
            {"label": target.key_label, "ok": ok, "error": error, "ms": elapsed_ms}
        )
        if target.key_id:
            try:
                from providers.models import APIKey

                APIKey.objects.filter(pk=target.key_id).update(
                    last_checked_at=timezone.now(), last_ok=ok, last_error=error
                )
            except Exception:  # noqa: BLE001 - probing must not fail on bookkeeping
                logger.debug("Could not store probe result", exc_info=True)
    return results, ""


def _price(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_free_model(entry: dict) -> bool:
    """True when a /models entry is free: ':free' / '/free' id or zero pricing."""
    model_id = str(entry.get("id", ""))
    if model_id.endswith(":free") or model_id.rsplit("/", 1)[-1] == "free":
        return True
    pricing = entry.get("pricing") or {}
    prompt = _price(pricing.get("prompt"))
    completion = _price(pricing.get("completion"))
    return prompt == 0 and completion == 0


def fetch_free_models(provider) -> tuple[list[dict], str]:
    """List the free models a provider advertises through ``GET /models``.

    Returns ``(models, error)``; each model is ``{"slug", "label"}``. Uses the
    provider's first usable key (OpenRouter also works without one) and the same
    proxy as chat calls. Errors come back as text so the admin can show them.
    """
    keys = _targets_for(provider.slug, "", provider.base_url)
    headers = {"Authorization": f"Bearer {keys[0].api_key}"} if keys else {}
    headers.update(_headers(provider.slug))
    timeout = float(getattr(settings, "LLM_MODELS_TIMEOUT", 120))
    try:
        proxy = proxy_url() or None
        with httpx.Client(proxy=proxy, timeout=timeout) as client:
            response = client.get(f"{provider.base_url}/models", headers=headers)
    except Exception as exc:  # noqa: BLE001 - reported to the admin
        return [], _scrub(f"{type(exc).__name__}: {exc}", keys)[:300]

    if response.status_code != 200:
        return [], _scrub(
            f"HTTP {response.status_code}: {response.text[:250]}", keys
        )
    try:
        entries = response.json().get("data") or []
    except ValueError:
        return [], "The provider returned something that is not JSON."

    found = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id") and is_free_model(entry):
            found.append(
                {"slug": str(entry["id"])[:200], "label": str(entry.get("name") or "")[:200]}
            )
    found.sort(key=lambda item: item["slug"])
    return found, ""
