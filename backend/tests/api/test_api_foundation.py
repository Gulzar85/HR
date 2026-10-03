import pytest
from rest_framework.test import APIClient


def test_api_root_version():
    r = APIClient().get("/api/v1/")
    assert r.status_code == 200
    assert r.json()["data"]["version"] == "v1"


def test_unknown_api_version_rejected():
    r = APIClient().get("/api/v2/")
    assert r.status_code == 404


@pytest.mark.django_db
def test_domain_exception_envelope():
    from rest_framework.views import APIView

    from apps.api.exceptions import api_exception_handler
    from apps.common.exceptions import ConflictException

    resp = api_exception_handler(ConflictException("dup", details={"f": 1}), {"view": APIView()})
    assert resp.status_code == 409
    assert resp.data == {"error": {"code": "conflict", "message": "dup", "details": {"f": 1}}}


def test_unauthenticated_protected_endpoint_uses_envelope():
    from django.urls import path
    from rest_framework.response import Response
    from rest_framework.views import APIView

    class Protected(APIView):
        def get(self, request):
            return Response({})

    from django.test import override_settings

    import apps.api.v1.urls as v1

    v1.urlpatterns.append(path("_probe/", Protected.as_view()))
    try:
        r = APIClient().get("/api/v1/_probe/")
    finally:
        v1.urlpatterns.pop()
    assert r.status_code in (401, 403)
    assert "error" in r.json()
    assert override_settings  # imported for clarity of intent
