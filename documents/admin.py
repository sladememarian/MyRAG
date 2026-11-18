"""Admin UI for documents. Indexing logic lives in rag.services."""
from django.contrib import admin, messages

from documents.models import Document
from rag.services import delete_document_index, process_document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "indexed", "created_at", "updated_at")
    list_filter = ("indexed", "created_at")
    search_fields = ("title", "full_text")
    readonly_fields = ("full_text", "indexed", "created_at", "updated_at")
    actions = ("reindex_selected",)
    date_hierarchy = "created_at"

    def save_model(self, request, obj, form, change):
        """Save first (so the file exists on disk), then extract + index."""
        super().save_model(request, obj, form, change)
        try:
            chunks = process_document(obj)
        except Exception as exc:  # noqa: BLE001 - show any ingestion failure to the user
            messages.error(request, f"Could not process “{obj.title}”: {exc}")
            return
        messages.success(request, f"“{obj.title}” indexed into {chunks} chunk(s).")

    def delete_model(self, request, obj):
        """Remove the document's chunks before deleting the row.

        If the vector store cannot be updated, keep the row: deleting it would
        leave chunks that still answer questions with no way to find them.
        """
        try:
            delete_document_index(obj.pk)
        except Exception as exc:  # noqa: BLE001 - report and keep the row
            messages.error(
                request,
                f"“{obj.title}” was not deleted because its search index "
                f"could not be updated: {exc}",
            )
            return
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        """Bulk delete from the admin action menu also cleans the vector store."""
        deleted_ids = []
        for document in queryset:
            try:
                delete_document_index(document.pk)
            except Exception as exc:  # noqa: BLE001 - keep failed rows
                messages.error(
                    request,
                    f"“{document.title}” was not deleted because its search "
                    f"index could not be updated: {exc}",
                )
            else:
                deleted_ids.append(document.pk)
        if deleted_ids:
            super().delete_queryset(request, queryset.filter(pk__in=deleted_ids))

    @admin.action(description="Re-index selected documents")
    def reindex_selected(self, request, queryset):
        succeeded, failed = 0, 0
        for document in queryset:
            try:
                process_document(document)
                succeeded += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                messages.error(request, f"“{document.title}” failed: {exc}")
        level = messages.WARNING if failed else messages.SUCCESS
        self.message_user(
            request,
            f"Re-indexed {succeeded} document(s); {failed} failed.",
            level=level,
        )


admin.site.site_header = "Document QA — Administration"
admin.site.site_title = "Document QA"
admin.site.index_title = "Manage documents, questions and answers"
