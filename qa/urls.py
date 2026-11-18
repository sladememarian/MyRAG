"""Question/history API routes."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from qa.views import AskView, HistoryViewSet

router = SimpleRouter()
router.register("history", HistoryViewSet, basename="history")

urlpatterns = [
    path("ask/", AskView.as_view(), name="ask"),
    *router.urls,
]
