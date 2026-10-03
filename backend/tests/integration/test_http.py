from unittest.mock import patch

import pytest
from django.test import Client


@pytest.fixture
def client():
    return Client()


def test_home_renders_with_theme_and_csp(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.content.decode()
    assert "--color-primary" in body
    assert "#DA291C" not in body.split("</style>", 1)[1]  # no hard-coded brand colour in markup
    assert "content-security-policy" in {k.lower() for k in r.headers}
    assert r.headers["X-Frame-Options"] == "DENY"


def test_404_is_class_based_and_clean(client):
    r = client.get("/nope/")
    assert r.status_code == 404
    assert "Traceback" not in r.content.decode()


def test_health_live(client):
    r = client.get("/health/live/")
    assert r.status_code == 200 and r.json()["status"] == "ok"


@pytest.mark.django_db
def test_health_ready_ok_and_degraded(client):
    with patch.dict(
        "apps.health.checks.READINESS_CHECKS",
        {"database": lambda: (True, "ok"), "redis": lambda: (True, "ok")},
        clear=True,
    ):
        assert client.get("/health/ready/").status_code == 200
    with patch.dict(
        "apps.health.checks.READINESS_CHECKS",
        {"database": lambda: (True, "ok"), "redis": lambda: (False, "ConnectionError")},
        clear=True,
    ):
        r = client.get("/health/ready/")
        assert r.status_code == 503 and r.json()["checks"]["redis"] == "ConnectionError"


@pytest.mark.django_db
def test_health_ready_real_database_and_storage(client):
    from apps.health import checks

    assert checks.check_database() == (True, "ok")
    assert checks.check_storage() == (True, "ok")
