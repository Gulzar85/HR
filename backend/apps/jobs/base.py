"""Celery task conventions.

* Tasks are thin: they load ids, call a service, and return a small JSON result.
* Tasks live in each app's ``tasks.py`` (autodiscovered); queue names are declared here.
* Use ``ems_task`` instead of bare ``shared_task`` so retries/logging are uniform.
"""

from __future__ import annotations

from celery import shared_task

QUEUE_DEFAULT = "default"
QUEUE_NOTIFICATIONS = "notifications"
QUEUE_IMPORTS = "imports"
QUEUE_REPORTS = "reports"
QUEUE_DOCUMENTS = "documents"
QUEUE_DATA_QUALITY = "data_quality"
QUEUE_WORKFLOW = "workflow"
QUEUE_OUTBOX = "outbox"


def ems_task(**options):
    options.setdefault("autoretry_for", (ConnectionError,))
    options.setdefault("retry_backoff", True)
    options.setdefault("max_retries", 5)
    return shared_task(**options)
