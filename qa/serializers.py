"""API serializers for asking questions and reading history."""
from rest_framework import serializers

from qa.models import Query


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(
        min_length=3,
        max_length=2000,
        trim_whitespace=True,
        error_messages={"min_length": "Please ask a slightly longer question."},
    )


class AskResponseSerializer(serializers.Serializer):
    query_id = serializers.IntegerField()
    answer = serializers.CharField(allow_blank=True)
    sources = serializers.JSONField()
    model_name = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    detail = serializers.CharField(required=False)


class QuerySerializer(serializers.ModelSerializer):
    class Meta:
        model = Query
        fields = (
            "id",
            "question",
            "answer",
            "sources",
            "model_name",
            "status",
            "failure_kind",
            "error_message",
            "created_at",
        )
        read_only_fields = fields
