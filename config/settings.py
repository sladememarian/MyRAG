"""Django settings for the Document Question-Answering (RAG) project.

All deployment-specific values are read from environment variables so the same
image works in development, Docker and CI. See .env.example for the full list.
"""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

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
    "django.contrib.admin",
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
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", "ragdb"),
            "USER": env("POSTGRES_USER", "raguser"),
            "PASSWORD": env("POSTGRES_PASSWORD", "ragpass"),
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
# OpenRouter LLM (OpenAI-compatible)
# --------------------------------------------------------------------------- #
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
OPENROUTER_MODEL = env("OPENROUTER_MODEL", "inclusionai/ling-3.2-flash:free")
OPENROUTER_PROXY = env("OPENROUTER_PROXY", "")
OPENROUTER_TIMEOUT = env_int("OPENROUTER_TIMEOUT", 60)
OPENROUTER_MAX_TOKENS = env_int("OPENROUTER_MAX_TOKENS", 800)
OPENROUTER_TEMPERATURE = env_float("OPENROUTER_TEMPERATURE", 0.0)
OPENROUTER_APP_NAME = env("OPENROUTER_APP_NAME", "Document QA RAG")

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
