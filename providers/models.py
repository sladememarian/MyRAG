"""Providers (OpenRouter, Itera Compute), their keys and the selectable models."""
from django.conf import settings
from django.db import models, transaction

from providers import crypto
from providers.constants import (
    API_KEY_ENV,
    BASE_URL_ENV,
    DEFAULT_BASE_URLS,
    DEFAULT_MODELS,
    MODEL_ENV,
    OPENROUTER,
    PROVIDER_CHOICES,
)


class Provider(models.Model):
    """One supported LLM provider.

    Rows are created by a data migration (openrouter and iteracompute) and are
    fixed: the app only knows how to talk to these two APIs, so the admin cannot
    add or delete providers.
    """

    slug = models.CharField(max_length=40, choices=PROVIDER_CHOICES, unique=True)
    name = models.CharField(max_length=100)
    is_enabled = models.BooleanField(
        default=True,
        help_text="Disabled providers are ignored even if one of their models is active.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "provider"
        verbose_name_plural = "providers"

    def __str__(self) -> str:
        return self.name or self.slug

    @property
    def base_url(self) -> str:
        """API root, overridable through the provider's environment variable."""
        env_name = BASE_URL_ENV.get(self.slug, "")
        configured = getattr(settings, env_name, "") if env_name else ""
        return (configured or DEFAULT_BASE_URLS.get(self.slug, "")).rstrip("/")

    @property
    def default_model(self) -> str:
        env_name = MODEL_ENV.get(self.slug, "")
        configured = getattr(settings, env_name, "") if env_name else ""
        return configured or DEFAULT_MODELS.get(self.slug, "")

    @property
    def env_api_key(self) -> str:
        env_name = API_KEY_ENV.get(self.slug, "")
        return getattr(settings, env_name, "") if env_name else ""

    def active_keys(self):
        """Active keys in the order they should be tried."""
        return self.api_keys.filter(is_active=True).order_by("priority", "id")


class APIKey(models.Model):
    """One API key for one provider. The secret is encrypted at rest."""

    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE, related_name="api_keys"
    )
    label = models.CharField(
        max_length=100, blank=True, help_text="Optional name, e.g. 'primary' or 'backup'."
    )
    # Ciphertext, written through set_secret(); never contains the plain key.
    secret = models.TextField(help_text="Encrypted at rest.")
    is_active = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(
        default=100, help_text="Lower numbers are tried first when a key fails."
    )
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_ok = models.BooleanField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["priority", "id"]
        verbose_name = "API key"
        verbose_name_plural = "API keys"

    def __str__(self) -> str:
        # Never include the secret: this string appears in logs and admin pages.
        return f"{self.provider.name}: {self.label or self.masked}"

    def set_secret(self, raw: str) -> None:
        self.secret = crypto.encrypt((raw or "").strip())

    def get_secret(self) -> str:
        return crypto.decrypt(self.secret)

    @property
    def masked(self) -> str:
        raw = self.get_secret()
        if not raw:
            return "unreadable"
        if len(raw) <= 10:
            return "*" * len(raw)
        return f"{raw[:6]}…{raw[-4:]}"


class LLMModel(models.Model):
    """A model id at one provider, e.g. ``inclusionai/ling-3.2-flash:free``.

    Exactly one row may be active across all providers; activating a model
    deactivates the previous one, so the answering pipeline never has to guess.
    When no row is active the project falls back to the OpenRouter values in
    ``.env`` and keeps working before anything is configured in the admin.
    """

    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE, related_name="models"
    )
    slug = models.CharField(
        max_length=200,
        help_text=(
            "Model id exactly as the provider expects it, e.g. "
            "inclusionai/ling-3.2-flash:free (OpenRouter) or Auto (Itera Compute)."
        ),
    )
    label = models.CharField(
        max_length=200, blank=True, help_text="Optional friendly name shown in admin."
    )
    is_active = models.BooleanField(
        default=False, help_text="The active model answers all new questions."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["provider_id", "slug"]
        verbose_name = "model"
        verbose_name_plural = "models"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "slug"], name="unique_model_per_provider"
            ),
            # Database-level guarantee: at most one active model overall.
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="only_one_active_model",
            ),
        ]

    def __str__(self) -> str:
        return self.label or self.qualified_slug

    @property
    def qualified_slug(self) -> str:
        if self.provider.slug == OPENROUTER:
            return self.slug
        return f"{self.provider.slug}/{self.slug}"

    def save(self, *args, **kwargs):
        # Switching is exclusive: activating a model deactivates the others.
        with transaction.atomic():
            if self.is_active:
                type(self).objects.filter(is_active=True).exclude(pk=self.pk).update(
                    is_active=False
                )
            super().save(*args, **kwargs)
