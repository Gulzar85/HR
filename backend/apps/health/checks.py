"""Individual health checks. Each returns (ok, detail) and never raises."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection


def check_application() -> tuple[bool, str]:
    return True, "ok"


def check_database() -> tuple[bool, str]:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True, "ok"
    except Exception as exc:
        return False, exc.__class__.__name__


def check_redis() -> tuple[bool, str]:
    try:
        import redis

        redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2).ping()
        return True, "ok"
    except Exception as exc:
        return False, exc.__class__.__name__


def check_celery() -> tuple[bool, str]:
    """Broker reachability (does not require a running worker)."""
    try:
        from config.celery import app

        with app.connection_for_write() as conn:
            conn.ensure_connection(max_retries=1, timeout=2)
        return True, "ok"
    except Exception as exc:
        return False, exc.__class__.__name__


def check_storage() -> tuple[bool, str]:
    name = f"healthcheck/{uuid.uuid4().hex}.tmp"
    try:
        saved = default_storage.save(name, ContentFile(b"ok"))
        default_storage.delete(saved)
        return True, "ok"
    except Exception as exc:
        return False, exc.__class__.__name__


READINESS_CHECKS = {
    "database": check_database,
    "redis": check_redis,
    "celery": check_celery,
    "storage": check_storage,
}
