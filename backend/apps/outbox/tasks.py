from celery import shared_task

from .services import dispatch_pending


@shared_task(name="apps.outbox.tasks.dispatch_outbox")
def dispatch_outbox() -> dict[str, int]:
    return dispatch_pending()
