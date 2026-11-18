"""REST serializers for documents."""
from rest_framework import serializers

from documents.models import Document
from documents.validators import validate_docx_file


class DocumentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(validators=[validate_docx_file])

    class Meta:
        model = Document
        fields = (
            "id",
            "title",
            "file",
            "full_text",
            "indexed",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("full_text", "indexed", "created_at", "updated_at")
