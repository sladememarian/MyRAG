"""Question API: POST /api/ask/ and the read-only history endpoints."""
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from qa.models import Query
from qa.serializers import AskResponseSerializer, AskSerializer, QuerySerializer
from qa.services import run_query
from qa.throttles import AskRateThrottle

# Maps an internal failure kind to an HTTP status for POST /api/ask/.
ERROR_STATUS = {"no_content": 404, "llm": 503, "other": 400}


@extend_schema(
    summary="Ask a question",
    description=(
        "Retrieves relevant document chunks, asks the active LLM, "
        "stores the question/answer in the history and returns the answer with sources."
    ),
    request=AskSerializer,
    responses={200: AskResponseSerializer, 404: AskResponseSerializer, 503: AskResponseSerializer},
)
class AskView(APIView):
    # Each question costs LLM tokens; limit per user (see ASK_THROTTLE_RATE).
    throttle_classes = [AskRateThrottle]

    def post(self, request):
        serializer = AskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        query = run_query(serializer.validated_data["question"], user=request.user)
        payload = {
            "query_id": query.pk,
            "answer": query.answer,
            "sources": query.sources,
            "model_name": query.model_name,
            "status": query.status,
            "created_at": query.created_at,
        }

        if query.status == Query.STATUS_ERROR:
            payload["detail"] = query.error_message
            status_code = ERROR_STATUS.get(query.failure_kind, 400)
            return Response(AskResponseSerializer(payload).data, status=status_code)

        return Response(AskResponseSerializer(payload).data, status=200)


class HistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Paginated list and detail of the current user's questions and answers."""

    # Used by drf-spectacular to type the {id} path parameter; get_queryset()
    # below narrows every real request to the authenticated user.
    queryset = Query.objects.all()
    serializer_class = QuerySerializer
    # PageNumberPagination is configured globally (API_PAGE_SIZE, default 20).

    def get_queryset(self):
        # Each user sees only their own history. Staff still see everything in
        # the Django admin, which is the administration UI.
        return Query.objects.filter(user=self.request.user)


@extend_schema(exclude=True)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """Unauthenticated liveness probe used by humans and containers."""
    return Response({"status": "ok"})
