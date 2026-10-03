from django.http import JsonResponse
from django.views import View

from . import checks


class LiveView(View):
    """Liveness: process is up. No dependencies are touched."""

    def get(self, request, *args, **kwargs):
        ok, detail = checks.check_application()
        return JsonResponse({"status": "ok" if ok else "fail", "checks": {"application": detail}})


class ReadyView(View):
    """Readiness: dependencies reachable. 503 if any check fails."""

    def get(self, request, *args, **kwargs):
        results = {name: fn() for name, fn in checks.READINESS_CHECKS.items()}
        healthy = all(ok for ok, _ in results.values())
        body = {
            "status": "ok" if healthy else "fail",
            "checks": {name: detail for name, (_, detail) in results.items()},
        }
        return JsonResponse(body, status=200 if healthy else 503)
