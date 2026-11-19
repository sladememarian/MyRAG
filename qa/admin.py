"""Admin UI for the question/answer history."""
import json

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from qa.models import Query
from qa.services import answer_query


class PostButtonAdmin(admin.ModelAdmin):
    """Adds row buttons that submit a POST, so each click carries a CSRF token."""

    def changelist_view(self, request, extra_context=None):
        # The token is attached to the rows of *this* response. Storing it on
        # the admin instance would be shared between threads and could render
        # another session's token during concurrent requests.
        response = super().changelist_view(request, extra_context)
        context = getattr(response, "context_data", None)
        changelist = context.get("cl") if hasattr(context, "get") else None
        if changelist is not None:
            token = get_token(request)
            for obj in changelist.result_list:
                obj._post_button_token = token
        return response

    def post_button(self, obj, url: str, label: str, title: str = "") -> str:
        token = getattr(obj, "_post_button_token", "")
        if not token:
            return "—"
        return format_html(
            '<form method="post" action="{}" style="margin:0">{}{}</form>',
            url,
            format_html(
                '<input type="hidden" name="csrfmiddlewaretoken" value="{}">', token
            ),
            format_html(
                '<button type="submit" class="button" title="{}">{}</button>',
                title,
                label,
            ),
        )

    def redirect_to_changelist(self):
        opts = self.model._meta
        return HttpResponseRedirect(
            reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
        )


@admin.register(Query)
class QueryAdmin(PostButtonAdmin):
    list_display = (
        "id",
        "short_question",
        "answer_preview",
        "state",
        "user",
        "model_name",
        "created_at",
        "retry_button",
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

    def get_urls(self):
        # Row-level retry must be a POST (it costs an LLM call), so it is an
        # extra admin view rather than a link to the change page.
        custom = [
            path(
                "<path:object_id>/retry/",
                self.admin_site.admin_view(require_POST(self.retry_view)),
                name="qa_query_retry",
            ),
        ]
        return custom + super().get_urls()

    def retry_view(self, request, object_id):
        if not self.has_change_permission(request):
            raise PermissionDenied
        query = get_object_or_404(self.get_queryset(request), pk=object_id)
        answer_query(query)
        if query.status == Query.STATUS_ERROR:
            self.message_user(
                request, f"Retry failed: {query.error_message}", messages.ERROR
            )
        else:
            self.message_user(
                request, "Retry succeeded and the answer was saved.", messages.SUCCESS
            )
        return self.redirect_to_changelist()

    @admin.display(description="Question")
    def short_question(self, obj) -> str:
        text = " ".join((obj.question or "").split())
        return text[:70] + ("…" if len(text) > 70 else "")

    @admin.display(description="Answer")
    def answer_preview(self, obj) -> str:
        text = " ".join((obj.answer or "").split())
        return text[:90] + ("…" if len(text) > 90 else "")

    @admin.display(description="State", ordering="status")
    def state(self, obj):
        """Show the row's current outcome, with the reason when it failed."""
        if obj.status == Query.STATUS_OK:
            return format_html(
                '<span style="color:#1a7f37;font-weight:600">{}</span>',
                "Succeeded",
            )
        reason = obj.get_failure_kind_display() if obj.failure_kind else "Error"
        return format_html(
            '<span style="color:#b42318;font-weight:600">Failed</span>'
            ' <span style="color:#666">({})</span>',
            reason,
        )

    @admin.display(description="Retry")
    def retry_button(self, obj):
        """Offer a one-click re-run for failed questions only."""
        if obj.status != Query.STATUS_ERROR:
            return "—"
        url = reverse("admin:qa_query_retry", args=[obj.pk])
        return self.post_button(obj, url, "Retry", title="Ask this question again")

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
