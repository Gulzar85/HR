from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.api.responses import success


class ApiRootView(APIView):
    """API root: version discovery for Electron / mobile / external clients."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, *args, **kwargs):
        return success(
            {
                "name": "McDonald's Pakistan EMS API",
                "version": request.version,
                "status": "ok",
                "resources": [],  # populated as phases mount their routes
            }
        )
