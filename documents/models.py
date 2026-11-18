"""Document model: one uploaded .docx and its extracted text."""
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from documents.validators import validate_docx_file


class Document(models.Model):
    """An uploaded Word document.

    `full_text` is filled by the ingestion pipeline (`rag.services`) and is
    never edited by hand. `indexed` tells whether chunks for this document are
    currently present in the vector store.
    """

    title = models.CharField(max_length=255)
    file = models.FileField(
        upload_to="documents/%Y/%m/",
        validators=[validate_docx_file],
        help_text="Only .docx files are accepted.",
    )
    full_text = models.TextField(blank=True, default="")
    indexed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Document"
        verbose_name_plural = "Documents"

    def __str__(self) -> str:
        return self.title


# --------------------------------------------------------------------------- #
# File cleanup
#
# Django never deletes FileField files automatically. Without these receivers,
# replaced uploads and deleted documents leave unreachable .docx files in the
# media volume forever.
# --------------------------------------------------------------------------- #
@receiver(pre_save, sender=Document)
def _remember_replaced_file(sender, instance, **kwargs):
    """Store the old file name before a save that may replace it."""
    if not instance.pk:
        return
    old = sender.objects.filter(pk=instance.pk).only("file").first()
    instance._old_file_name = old.file.name if old and old.file else ""


@receiver(post_save, sender=Document)
def _delete_replaced_file(sender, instance, **kwargs):
    """After a successful save, delete the file that was replaced."""
    old_name = getattr(instance, "_old_file_name", "")
    new_name = instance.file.name if instance.file else ""
    if old_name and old_name != new_name:
        instance.file.storage.delete(old_name)
    instance._old_file_name = ""


@receiver(post_delete, sender=Document)
def _delete_file_on_delete(sender, instance, **kwargs):
    """Delete the stored .docx when its database row is deleted."""
    if instance.file:
        instance.file.delete(save=False)
