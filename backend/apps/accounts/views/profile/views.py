from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, TemplateView

from apps.common.exceptions import ConflictException, NotFoundException, ValidationException
from apps.common.request_context import RequestContext

from ...forms import ProfileForm
from ...services import SessionService, UserService


class ProfileView(LoginRequiredMixin, FormView):
    """Self-service: names, email, appearance. Never roles, permissions, scopes or status."""

    template_name = "accounts/profile/profile.html"
    form_class = ProfileForm
    success_url = reverse_lazy("accounts:profile")

    def get_initial(self):
        u = self.request.user
        return {
            "first_name": u.first_name,
            "last_name": u.last_name,
            "email": u.email,
            "theme_mode": u.preferences.get("theme_mode", "system"),
        }

    def form_valid(self, form):
        d = form.cleaned_data
        try:
            UserService.update_own_profile(
                user=self.request.user,
                ctx=RequestContext.from_request(self.request),
                first_name=d["first_name"],
                last_name=d["last_name"],
                email=d["email"],
                preferences={**self.request.user.preferences, "theme_mode": d["theme_mode"]},
            )
        except (ConflictException, ValidationException) as exc:
            form.add_error(
                "email" if "email" in exc.code or "email" in exc.message else None, exc.message
            )
            return self.form_invalid(form)
        messages.success(self.request, "Profile updated.")
        return super().form_valid(form)


class SessionListView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/profile/sessions.html"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["sessions"] = SessionService.active_sessions(self.request.user)
        data["current_key"] = self.request.session.session_key
        return data


class SessionRevokeView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        try:
            # owner=request.user: a user can only revoke their own sessions (IDOR guard)
            SessionService.revoke_session(
                pk, actor=request.user, owner=request.user, ctx=RequestContext.from_request(request)
            )
            messages.success(request, "Session revoked.")
        except NotFoundException:
            messages.error(request, "Session not found.")
        return redirect("accounts:sessions")
