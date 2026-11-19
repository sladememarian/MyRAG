"""Django settings for the Document Question-Answering (RAG) project.

All deployment-specific values are read from environment variables so the same
image works in development, Docker and CI. See .env.example for the full list.
"""
import os
import secrets
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from providers.constants import (
    DEFAULT_BASE_URLS,
    DEFAULT_MODELS,
    ITERACOMPUTE,
    OPENROUTER,
    ORCAROUTER,
    TOKENHARBOR,
)

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name: str, default=None):
    """Return an env var, treating an empty string as 'not set'."""
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def env_bool(name: str, default: bool = False) -> bool:
    return str(env(name, str(default))).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    return int(env(name, default))


def env_float(name: str, default: float) -> float:
    return float(env(name, default))


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in str(env(name, default)).split(",") if item.strip()]


# --------------------------------------------------------------------------- #
# Core security
# --------------------------------------------------------------------------- #
# Production is safe by default: DEBUG is off unless .env enables it, and the
# HTTPS-related flags below switch on automatically when DEBUG is off. The
# development .env.example sets DEBUG=True so local Docker keeps working.
SECRET_KEY_FROM_ENV = env("SECRET_KEY")
SECRET_KEY_IS_EPHEMERAL = not SECRET_KEY_FROM_ENV
SECRET_KEY_IS_INSECURE = SECRET_KEY_IS_EPHEMERAL or len(SECRET_KEY_FROM_ENV or "") < 50
# An ephemeral key keeps local installs running without a hardcoded secret. It
# is not stable across restarts, so `manage.py check --deploy` flags it.
SECRET_KEY = SECRET_KEY_FROM_ENV or secrets.token_urlsafe(50)

DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,web,testserver")

# HTTPS and cookie hardening. Each value can be overridden for deployments
# that terminate TLS somewhere other than Django.
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0 if DEBUG else 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)
if env_bool("TRUST_X_FORWARDED_PROTO", False):
    # Opt-in: only a trusted reverse proxy should be allowed to set this header,
    # otherwise a client could claim its plain-HTTP request was HTTPS.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    # Replaces "django.contrib.admin" only to use our AdminSite subclass,
    # which keeps Questions & Answers first on the admin home page. Model
    # configuration is a separate app, so it gets its own section.
    "config.apps.RAGAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    # Local apps
    "documents",
    "qa",
    "providers.apps.ProvidersConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --------------------------------------------------------------------------- #
# Database: PostgreSQL by default, SQLite only for quick local experiments.
# --------------------------------------------------------------------------- #
if env("DB_ENGINE", "postgres") == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DB_PASSWORD = env("POSTGRES_PASSWORD")
    if not DB_PASSWORD:
        raise ImproperlyConfigured(
            "POSTGRES_PASSWORD is not set. Create a .env from .env.example and give "
            "it a strong password, or use DB_ENGINE=sqlite for a throwaway local run."
        )
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", "ragdb"),
            "USER": env("POSTGRES_USER", "raguser"),
            "PASSWORD": DB_PASSWORD,
            "HOST": env("POSTGRES_HOST", "localhost"),
            "PORT": env("POSTGRES_PORT", "5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------- #
# REST API + OpenAPI docs
# --------------------------------------------------------------------------- #
REST_FRAMEWORK = {
    # Session auth makes the browsable API and Swagger "Try it out" work with
    # an admin login; token auth makes curl/scripts easy. Both are enabled.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": env_int("API_PAGE_SIZE", 20),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# Every question costs LLM tokens, so /api/ask/ is rate-limited per user.
# Set an empty value to disable throttling. See qa/throttles.py.
ASK_THROTTLE_RATE = env("ASK_THROTTLE_RATE", "20/min")

SPECTACULAR_SETTINGS = {
    "TITLE": "Document QA (RAG) API",
    "DESCRIPTION": (
        "Upload .docx documents, ask questions and read the question/answer history. "
        "Authenticate with a session (admin login) or a DRF token."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# --------------------------------------------------------------------------- #
# LLM providers (OpenAI-compatible endpoints)
# --------------------------------------------------------------------------- #
# Both providers are configured; the model selected in the admin decides which
# one answers. The values here are fallbacks used before anything is selected.
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = env(
    "OPENROUTER_BASE_URL", DEFAULT_BASE_URLS[OPENROUTER]
).rstrip("/")
OPENROUTER_MODEL = env("OPENROUTER_MODEL", DEFAULT_MODELS[OPENROUTER])
OPENROUTER_APP_NAME = env("OPENROUTER_APP_NAME", "Document QA RAG")
# Optional: OpenRouter uses this only for its public rankings page.
OPENROUTER_SITE_URL = env("OPENROUTER_SITE_URL", "")

ITERACOMPUTE_API_KEY = env("ITERACOMPUTE_API_KEY", "")
ITERACOMPUTE_BASE_URL = env(
    "ITERACOMPUTE_BASE_URL", DEFAULT_BASE_URLS[ITERACOMPUTE]
).rstrip("/")
ITERACOMPUTE_MODEL = env("ITERACOMPUTE_MODEL", DEFAULT_MODELS[ITERACOMPUTE])

TOKENHARBOR_API_KEY = env("TOKENHARBOR_API_KEY", "")
TOKENHARBOR_BASE_URL = env(
    "TOKENHARBOR_BASE_URL", DEFAULT_BASE_URLS[TOKENHARBOR]
).rstrip("/")
TOKENHARBOR_MODEL = env("TOKENHARBOR_MODEL", DEFAULT_MODELS[TOKENHARBOR])

ORCAROUTER_API_KEY = env("ORCAROUTER_API_KEY", "")
ORCAROUTER_BASE_URL = env(
    "ORCAROUTER_BASE_URL", DEFAULT_BASE_URLS[ORCAROUTER]
).rstrip("/")
ORCAROUTER_MODEL = env("ORCAROUTER_MODEL", DEFAULT_MODELS[ORCAROUTER])

# Shared client settings: timeouts and retries are what keep transient provider
# failures from surfacing as failed questions.
LLM_TIMEOUT = env_int("LLM_TIMEOUT", env_int("OPENROUTER_TIMEOUT", 60))
LLM_MAX_TOKENS = env_int("LLM_MAX_TOKENS", env_int("OPENROUTER_MAX_TOKENS", 800))
LLM_TEMPERATURE = env_float("LLM_TEMPERATURE", env_float("OPENROUTER_TEMPERATURE", 0.0))
# The OpenAI client retries 429/5xx/timeouts this many times per request.
LLM_MAX_RETRIES = env_int("LLM_MAX_RETRIES", 3)
# On top of the SDK retries: how many times one key is tried (with backoff) for
# transient failures and empty answers before moving on to the next key.
LLM_KEY_ATTEMPTS = env_int("LLM_KEY_ATTEMPTS", 3)
LLM_RETRY_BACKOFF = env_float("LLM_RETRY_BACKOFF", 2.0)
# Timeout for listing a provider's models (some routers are slow here).
LLM_MODELS_TIMEOUT = env_int("LLM_MODELS_TIMEOUT", 120)

# Proxy for outbound LLM calls. Set either one full URL (LLM_PROXY) or the three
# parts below; changing only the port in .env is the common case. Inside Docker
# a loopback host is rewritten to host.docker.internal automatically.
IN_DOCKER = env_bool("IN_DOCKER", False)
LLM_PROXY = env("LLM_PROXY", "")
LLM_PROXY_SCHEME = env("LLM_PROXY_SCHEME", "http")
LLM_PROXY_HOST = env("LLM_PROXY_HOST", "")
LLM_PROXY_PORT = env("LLM_PROXY_PORT", "")
# Deprecated alias kept so older .env files keep working.
OPENROUTER_PROXY = env("OPENROUTER_PROXY", "")

# Encrypts provider API keys stored by the admin. Empty means "derive from
# SECRET_KEY"; set a separate value if SECRET_KEY rotation is expected.
SECRET_ENCRYPTION_KEY = env("SECRET_ENCRYPTION_KEY", "")

# --------------------------------------------------------------------------- #
# Embeddings, vector store, retrieval and prompting
# --------------------------------------------------------------------------- #
EMBEDDING_BACKEND = env("EMBEDDING_BACKEND", "sentence-transformers")
EMBEDDING_MODEL = env(
    "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
EMBEDDING_DEVICE = env("EMBEDDING_DEVICE", "cpu")
EMBEDDING_FAKE_DIM = env_int("EMBEDDING_FAKE_DIM", 64)
CHROMA_DIR = env("CHROMA_DIR", str(BASE_DIR / "chroma_db"))
CHROMA_COLLECTION = env("CHROMA_COLLECTION", "documents")

CHUNK_SIZE = env_int("CHUNK_SIZE", 800)
CHUNK_OVERLAP = env_int("CHUNK_OVERLAP", 120)

RETRIEVAL_K = env_int("RETRIEVAL_K", 5)
RETRIEVAL_FETCH_K = env_int("RETRIEVAL_FETCH_K", 20)
RETRIEVAL_LAMBDA = env_float("RETRIEVAL_LAMBDA", 0.5)
# Multi-query adds one extra LLM call per question. It is useful for hard
# questions but off by default to keep the free quota and latency low.
RETRIEVAL_USE_MULTI_QUERY = env_bool("RETRIEVAL_USE_MULTI_QUERY", False)
MULTI_QUERY_COUNT = env_int("MULTI_QUERY_COUNT", 3)
# Chunks below this 0..1 relevance score are treated as unrelated. Raise it to
# make unanswerable questions return 404 instead of sending weak context to
# the LLM; lower it if valid questions are rejected.
RETRIEVAL_MIN_SCORE = env_float("RETRIEVAL_MIN_SCORE", 0.2)

CONTEXT_MAX_CHARS = env_int("CONTEXT_MAX_CHARS", 6000)
SNIPPET_CHARS = env_int("SNIPPET_CHARS", 300)
MAX_DOCUMENT_SIZE_MB = env_int("MAX_DOCUMENT_SIZE_MB", 10)

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {asctime} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "loggers": {
        "rag": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    },
}
