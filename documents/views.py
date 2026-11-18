"""Document API: the same service functions used by the admin."""
import logging

from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from documents.models import Document
from documents.serializers import DocumentSerializer
from rag.services import delete_document_index, process_document

logger = logging.getLogger(__name__)

PROCESSING_ERROR = (
    "Could not process the document. Check that the file is a valid .docx "
    "and try again."
)
DELETE_ERROR = (
    "The document was not deleted because its search index could not be "
    "updated. Nothing was removed; please try again."
)


class IndexDeleteError(APIException):
    """Returned when Chroma fails so the database row is never orphaned."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = DELETE_ERROR
    default_code = "index_unavailable"


class DocumentViewSet(viewsets.ModelViewSet):
    """List, retrieve, upload, update and delete documents.

    Upload/update trigger extraction + indexing; delete removes the chunks.
    """

    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def perform_create(self, serializer):
        document = serializer.save()
        try:
            process_document(document)
        except Exception as exc:  # noqa: BLE001 - turn pipeline errors into a 400
            logger.exception("Could not process uploaded document %s", document.pk)
            delete_document_index(document.pk, ignore_errors=True)
            document.delete()
            raise serializers.ValidationError({"file": PROCESSING_ERROR}) from exc

    def perform_update(self, serializer):
        document = serializer.save()
        try:
            # Re-index on every update. The pipeline deletes old chunks first,
            # so edits never create duplicates.
            process_document(document)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Could not re-index document %s", document.pk)
            raise serializers.ValidationError({"file": PROCESSING_ERROR}) from exc

    def perform_destroy(self, instance):
        try:
            delete_document_index(instance.pk)
        except Exception as exc:  # noqa: BLE001 - keep the row so a retry works
            logger.exception("Could not delete index for document %s", instance.pk)
            raise IndexDeleteError() from exc
        instance.delete()
