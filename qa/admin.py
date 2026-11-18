"""Admin UI for the question/answer history."""
import json

from django.contrib import admin, messages
from django.utils.html import format_html

from qa.models import Query
from qa.services import answer_query


@admin.register(Query)
class QueryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "short_question",
        "answer_preview",
        "user",
        "status",
        "model_name",
        "created_at",
    )
    # Both the question and the answer open the read-only change page, where
    # the answer is shown in full instead of the truncated list preview.
    list_display_links = ("short_question", "answer_preview")
    list_filter = ("status", "created_at")
    search_fields = ("question", "answer")
    date_hierarchy = "created_at"
    readonly_fields = (
        "user",
        "answer_display",
        "sources_display",
        "model_name",
        "status",
        "failure_kind",
        "error_message",
        "created_at",
    )
    # `answer` and `sources` are shown through the display methods below, never
    # as editable form inputs: a stored answer is history, not something to edit.
    fields = (
        "question",
        "user",
        "answer_display",
        "sources_display",
        "model_name",
        "status",
        "failure_kind",
        "error_message",
        "created_at",
    )

    def get_readonly_fields(self, request, obj=None):
        # The question can only be typed when the record is created; after
        # that the row is pure history.
        if obj is not None:
            return ("question",) + tuple(self.readonly_fields)
        return self.readonly_fields

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return

        obj.user = request.user  # history belongs to the admin who asked
        answer_query(obj)  # fills + saves the record
        if obj.status == Query.STATUS_ERROR:
            messages.error(request, f"Answering failed: {obj.error_message}")
        else:
            messages.success(request, "Question answered and saved to history.")

    @admin.display(description="Question")
    def short_question(self, obj) -> str:
        text = " ".join((obj.question or "").split())
        return text[:70] + ("…" if len(text) > 70 else "")

    @admin.display(description="Answer")
    def answer_preview(self, obj) -> str:
        text = " ".join((obj.answer or "").split())
        return text[:90] + ("…" if len(text) > 90 else "")

    @admin.display(description="Answer")
    def answer_display(self, obj):
        if obj is None or not obj.answer:
            return "—"
        # Keep the model's line breaks and citations readable on the detail page.
        return format_html(
            "<pre style='white-space:pre-wrap; margin:0'>{}</pre>", obj.answer
        )

    @admin.display(description="Sources")
    def sources_display(self, obj):
        if obj is None or not obj.sources:
            return "—"
        pretty = json.dumps(obj.sources, ensure_ascii=False, indent=2)
        return format_html("<pre style='white-space:pre-wrap'>{}</pre>", pretty)
