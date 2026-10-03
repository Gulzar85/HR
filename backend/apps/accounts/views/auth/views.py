from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import FormView

from apps.common.exceptions import ValidationException
from apps.common.request_context import RequestContext

from ...forms import (
    ChangePasswordForm,
    LoginForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
)
from ...services import AuthenticationService, SessionService
from ...services.email_service import send_account_email


class LoginView(auth_views.LoginView):
    template_name = "accounts/auth/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)  # logs in; signal records event + registers session
        if form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(settings.EMS_REMEMBER_ME_SECONDS)
        else:
            self.request.session.set_expiry(0)  # browser-session cookie
        return response


class LogoutView(auth_views.LogoutView):
    """POST-only (CSRF protected) logout."""

    next_page = reverse_lazy("accounts:login")


class PasswordChangeView(LoginRequiredMixin, FormView):
    template_name = "accounts/auth/password_change.html"
    form_class = ChangePasswordForm
    success_url = reverse_lazy("accounts:password_change_done")

    def form_valid(self, form):
        request = self.request
        old_key = request.session.session_key
        try:
            user = AuthenticationService.change_password(
                user=request.user,
                old_password=form.cleaned_data["old_password"],
                new_password=form.cleaned_data["new_password"],
                ctx=RequestContext.from_request(request),
                keep_session_key=old_key,
            )
        except ValidationException as exc:
            for field, msgs in (exc.details or {}).items():
                target = {"new_password": "new_password", "old_password": "old_password"}.get(field)
                for m in msgs if isinstance(msgs, list) else [msgs]:
                    form.add_error(target if target in form.fields else None, m)
            if not exc.details:
                form.add_error(None, exc.message)
            return self.form_invalid(form)
        update_session_auth_hash(request, user)  # keeps *this* session; cycles its key
        SessionService.rotate_current(user, old_key, request.session.session_key)
        messages.success(request, "Your password was changed. Other sessions were signed out.")
        return super().form_valid(form)


class PasswordChangeDoneView(LoginRequiredMixin, auth_views.PasswordChangeDoneView):
    template_name = "accounts/auth/password_change_done.html"


class _ResetRequestForm(PasswordResetRequestForm):
    def save(self, domain_override=None, request=None, **kwargs):  # type: ignore[override]
        """Send our own branded e-mail for each eligible account (active, usable password)."""
        ctx = RequestContext.from_request(request)
        for user in self.get_users(self.cleaned_data["email"]):
            send_account_email("password_reset", user, ctx, with_link=True)


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/auth/password_reset_form.html"
    form_class = _ResetRequestForm
    success_url = reverse_lazy("accounts:password_reset_done")

    def form_valid(self, form):
        # Same response whether or not the address exists (no account enumeration).
        AuthenticationService.record_reset_requested(
            form.cleaned_data["email"], RequestContext.from_request(self.request)
        )
        return super().form_valid(form)


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/auth/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/auth/password_reset_confirm.html"
    form_class = PasswordResetConfirmForm
    success_url = reverse_lazy("accounts:password_reset_complete")

    def form_valid(self, form):
        response = super().form_valid(form)
        AuthenticationService.complete_password_reset(
            self.user, RequestContext.from_request(self.request)
        )
        return response


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/auth/password_reset_complete.html"
