"""Stored question/answer history."""
from django.conf import settings
from django.db import models


class Query(models.Model):
    """One question asked by a user, with the answer and its sources."""

    STATUS_OK = "ok"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_OK, "OK"),
        (STATUS_ERROR, "Error"),
    ]

    FAILURE_NO_CONTENT = "no_content"
    FAILURE_LLM = "llm"
    FAILURE_OTHER = "other"
    FAILURE_CHOICES = [
        (FAILURE_NO_CONTENT, "No relevant content"),
        (FAILURE_LLM, "Language model error"),
        (FAILURE_OTHER, "Other error"),
    ]

    # Who asked. Nullable because history created before user scoping, and
    # questions created by a deleted user, must not be lost.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="queries",
    )
    question = models.TextField()
    answer = models.TextField(blank=True, default="")
    sources = models.JSONField(default=list, blank=True)
    model_name = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OK)
    failure_kind = models.CharField(
        max_length=20, choices=FAILURE_CHOICES, blank=True, default=""
    )
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Question & Answer"
        verbose_name_plural = "Questions & Answers"

    def __str__(self) -> str:
        short = " ".join(self.question.split())
        return short[:60] + ("…" if len(short) > 60 else "")
