"""Account e-mails (password reset, activation invite, deactivation notice).

Delivery happens after the surrounding transaction commits. Links/tokens are never logged.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.common.logging import get_logger
from apps.common.request_context import RequestContext
from apps.common.services import after_commit

from ..models import User

logger = get_logger("app")

SUBJECTS = {
    "password_reset": "Reset your password",
    "account_activation": "Activate your account",
    "account_deactivation": "Your account has been deactivated",
}


def build_password_link(user: User, ctx: RequestContext) -> str:
    path = reverse(
        "accounts:password_reset_confirm",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
    base = ctx.base_url or getattr(settings, "EMS_SITE_URL", "")
    return f"{base}{path}"


def _send(template: str, user: User, context: dict[str, Any]) -> None:
    from apps.theme.services import ThemeService

    context = {**context, "user": user, "brand_name": ThemeService.resolve().brand_name}
    subject = SUBJECTS[template]
    message = EmailMultiAlternatives(
        subject=f"[{context['brand_name']}] {subject}",
        body=render_to_string(f"emails/{template}.txt", context),
        to=[user.email],
    )
    message.attach_alternative(render_to_string(f"emails/{template}.html", context), "text/html")
    try:
        message.send()
    except Exception:  # delivery problems must never break the business operation
        logger.exception(
            "account_email_failed", extra={"template": template, "user_id": str(user.pk)}
        )


def send_account_email(
    template: str, user: User, ctx: RequestContext, *, with_link: bool = False
) -> None:
    """Queue an e-mail to be sent when the current transaction commits."""
    context: dict[str, Any] = {}
    if with_link:
        context["link"] = build_password_link(user, ctx)
    after_commit(lambda: _send(template, user, context))
