"""Encryption of provider API keys at rest.

Keys entered in the admin are stored with Fernet (AES-128-CBC + HMAC), keyed
from ``SECRET_ENCRYPTION_KEY``. When that variable is empty the project's
``SECRET_KEY`` is used, so no extra configuration is required; rotating the
secret therefore requires re-entering the stored keys, which the admin reports
as "unreadable" instead of returning a corrupted value.
"""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

PREFIX = "fernet:"


def _key_material() -> str:
    configured = (
        getattr(settings, "SECRET_ENCRYPTION_KEY", "") or settings.SECRET_KEY or ""
    )
    if not configured:
        raise ImproperlyConfigured(
            "Set SECRET_KEY (or SECRET_ENCRYPTION_KEY) before storing API keys."
        )
    return configured


def _fernet() -> Fernet:
    digest = hashlib.sha256(f"rag-provider-key:{_key_material()}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    """Encrypt a plaintext API key for storage."""
    if not value:
        return ""
    token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return f"{PREFIX}{token}"


def decrypt(value: str) -> str:
    """Return the plaintext key, or "" when it cannot be decrypted."""
    if not value:
        return ""
    if not value.startswith(PREFIX):
        logger.error("Stored API key has an unknown format; re-enter it in the admin.")
        return ""
    try:
        return _fernet().decrypt(value[len(PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        logger.error(
            "Stored API key cannot be decrypted; SECRET_KEY may have changed. "
            "Re-enter the key in the admin."
        )
        return ""
