"""Wire Django auth signals into the identity services."""

from __future__ import annotations

from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.common.request_context import RequestContext

from .models import GroupProfile, LoginEvent, UserSession
from .services.authentication_service import AuthenticationService
from .services.security_events import record_login_event


def _channel(request) -> str:
    return "admin" if request is not None and request.path.startswith("/django-admin/") else "web"


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    if request is None:
        return
    AuthenticationService.record_success(
        user,
        ctx=RequestContext.from_request(request),
        channel=_channel(request),
        session_key=request.session.session_key,
    )


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    identifier = credentials.get("username") or credentials.get("email") or ""
    AuthenticationService.record_failure(
        identifier, ctx=RequestContext.from_request(request), channel=_channel(request)
    )


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user is None or request is None:
        return
    key = request.session.session_key
    UserSession.objects.filter(session_key=key, revoked_at__isnull=True).update(
        revoked_at=timezone.now(), revoked_reason="logout"
    )
    record_login_event(
        LoginEvent.EventType.LOGOUT,
        user=user,
        ctx=RequestContext.from_request(request),
        channel=_channel(request),
        session_key=key,
    )


@receiver(post_save, sender=Group)
def ensure_group_profile(sender, instance, created, **kwargs):
    GroupProfile.objects.get_or_create(group=instance)
