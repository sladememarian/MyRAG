"""Per-user rate limit for the expensive /api/ask/ endpoint."""
from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class AskRateThrottle(SimpleRateThrottle):
    """Limit questions per authenticated user (ASK_THROTTLE_RATE, e.g. 20/min).

    The rate is read from Django settings on every request so tests and
    deployments can change it without touching code. An empty rate disables
    the throttle.
    """

    scope = "ask"

    def get_rate(self):
        return settings.ASK_THROTTLE_RATE or None

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None  # authentication runs first; anonymous calls get 401
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}
