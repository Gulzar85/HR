"""Celery application. Redis is the broker; tasks live in apps/*/tasks or apps/jobs."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("ems")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
